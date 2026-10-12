import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from promptune.agents.prompt_editor.agent import IPromptEditorAgent
from promptune.agents.prompt_editor.context import EditorContext, prepare_editor_context
from promptune.agents.prompt_editor.schema import PromptEditorResponse
from promptune.core.exceptions import InvalidInputError
from promptune.modules.agent_run.repository import AgentRunRepository
from promptune.modules.message.model import MessageRole
from promptune.modules.message.repository import MessageRepository
from promptune.modules.prompt_proposal.repository import PromptProposalRepository

logger = logging.getLogger(__name__)

TRANSIENT_ERROR_NAMES = {
    "APIConnectionError",
    "APITimeoutError",
    "InternalServerError",
    "RateLimitError",
    "ServiceUnavailableError",
}


class AgentRunProcessor:
    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        prompt_editor_agent: IPromptEditorAgent,
        *,
        lease_seconds: int = 120,
        heartbeat_seconds: int = 30,
        max_attempts: int = 3,
    ) -> None:
        self.session_maker = session_maker
        self.prompt_editor_agent = prompt_editor_agent
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.max_attempts = max_attempts

    async def process_next(self) -> bool:
        claim = await self._claim_next()
        if claim is None:
            return False
        run_id, lease_token = claim
        stop_heartbeat = asyncio.Event()
        heartbeat = asyncio.create_task(
            self._heartbeat(run_id, lease_token, stop_heartbeat)
        )
        try:
            context = await self._load_context(run_id, lease_token)
            response = await self.prompt_editor_agent.respond(
                agent_context=context.agent_context,
                messages=context.messages,
                base_prompt_content=context.base_prompt_content,
            )
            _validate_response(response)
            await self._complete(run_id, lease_token, response)
        except Exception as error:
            logger.exception(
                "Agent run processing failed",
                extra={"event": "agent_run_failed", "run_id": str(run_id)},
            )
            await self._handle_error(run_id, lease_token, error)
        finally:
            stop_heartbeat.set()
            await asyncio.gather(heartbeat, return_exceptions=True)
        return True

    async def _claim_next(self) -> tuple[UUID, UUID] | None:
        async with self.session_maker() as session:
            repository = AgentRunRepository(session)
            now = datetime.now(UTC)
            await repository.recover_expired(now=now, max_attempts=self.max_attempts)
            run = await repository.claim_next(now=now, lease_seconds=self.lease_seconds)
            await session.commit()
            if run is None or run.lease_token is None:
                return None
            return run.id, run.lease_token

    async def _load_context(self, run_id: UUID, lease_token: UUID) -> EditorContext:
        async with self.session_maker() as session:
            runs = AgentRunRepository(session)
            run = await runs.get_claimed(run_id, lease_token)
            if run is None:
                raise InvalidInputError("Agent run claim is no longer valid")
            history = await MessageRepository(session).list_before_for_editing(
                run.session_id,
                run.user_message_id,
                run.session.user_id,
            )
            return prepare_editor_context(run.session, run.user_message, history)

    async def _complete(
        self,
        run_id: UUID,
        lease_token: UUID,
        response: PromptEditorResponse,
    ) -> None:
        async with self.session_maker() as session:
            runs = AgentRunRepository(session)
            run = await runs.lock_claimed(run_id, lease_token)
            if run is None:
                raise InvalidInputError("Agent run claim is no longer valid")
            loaded = await runs.get_claimed(run_id, lease_token)
            if loaded is None:
                raise InvalidInputError("Agent run claim is no longer valid")
            user_message = loaded.user_message
            conversation = loaded.session
            assistant = await MessageRepository(session).create(
                session_id=conversation.id,
                user_id=conversation.user_id,
                role=MessageRole.ASSISTANT,
                content=response.message.strip(),
                reply_to_id=user_message.id,
                questions=response.questions,
                warnings=response.warnings,
            )
            if response.proposal is not None:
                await PromptProposalRepository(session).create_for_message(
                    message_id=assistant.id,
                    agent_id=conversation.agent_id,
                    source_prompt_id=conversation.base_prompt_id,
                    change_request=user_message.content,
                    output=response.proposal,
                    questions=response.questions,
                    warnings=response.warnings,
                )
            await runs.mark_completed(run, assistant.id, now=datetime.now(UTC))
            await session.commit()

    async def _handle_error(
        self, run_id: UUID, lease_token: UUID, error: Exception
    ) -> None:
        transient = _is_transient(error)
        code, message = _safe_error(error, transient)
        async with self.session_maker() as session:
            repository = AgentRunRepository(session)
            run = await repository.lock_claimed(run_id, lease_token)
            if run is None:
                return
            await repository.mark_error(
                run,
                code=code,
                message=message,
                retry=transient and run.attempt_count < self.max_attempts,
                now=datetime.now(UTC),
            )
            await session.commit()

    async def _heartbeat(
        self, run_id: UUID, lease_token: UUID, stop: asyncio.Event
    ) -> None:
        if self.heartbeat_seconds <= 0:
            return
        while True:
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.heartbeat_seconds)
                return
            except TimeoutError:
                async with self.session_maker() as session:
                    renewed = await AgentRunRepository(session).heartbeat(
                        run_id,
                        lease_token,
                        now=datetime.now(UTC),
                        lease_seconds=self.lease_seconds,
                    )
                    await session.commit()
                    if not renewed:
                        return


def _is_transient(error: Exception) -> bool:
    return isinstance(error, (ConnectionError, TimeoutError)) or type(
        error
    ).__name__ in TRANSIENT_ERROR_NAMES


def _safe_error(error: Exception, transient: bool) -> tuple[str, str]:
    if transient:
        return "provider_unavailable", "The language model is temporarily unavailable"
    if isinstance(error, InvalidInputError):
        return (
            "invalid_agent_response",
            "The language model returned an invalid response",
        )
    return "processing_failed", "The agent run could not be completed"


def _validate_response(response: PromptEditorResponse) -> None:
    if not response.message.strip():
        raise InvalidInputError("Agent response message must not be blank")
    if response.proposal is not None and not response.proposal.proposed_content.strip():
        raise InvalidInputError("Agent proposal content must not be blank")
