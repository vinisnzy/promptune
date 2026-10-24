import asyncio
import logging
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from promptune.agents.prompt_editor.agent import IPromptEditorAgent
from promptune.agents.prompt_editor.context import EditorContext, prepare_editor_context
from promptune.agents.prompt_editor.schema import PromptEditorResponse
from promptune.core.exceptions import InvalidInputError
from promptune.modules.agent_run.queue import IRunPublisher, QueueUnavailableError
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


class ProcessResult(StrEnum):
    ACK = "ack"
    NACK_REQUEUE = "nack_requeue"


class AgentRunProcessor:
    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        prompt_editor_agent: IPromptEditorAgent,
        publisher: IRunPublisher,
        *,
        max_attempts: int = 3,
        timeout_seconds: float = 90,
    ) -> None:
        self.session_maker = session_maker
        self.prompt_editor_agent = prompt_editor_agent
        self.publisher = publisher
        self.max_attempts = max_attempts
        self.timeout_seconds = timeout_seconds

    async def process(self, run_id: UUID) -> ProcessResult:
        try:
            return await self._process(run_id)
        except SQLAlchemyError:
            logger.exception(
                "Agent run database failure",
                extra={"event": "agent_run_database_failed", "run_id": str(run_id)},
            )
            return ProcessResult.NACK_REQUEUE

    async def _process(self, run_id: UUID) -> ProcessResult:
        attempt = await self._claim(run_id)
        if attempt is None:
            logger.info(
                "Agent run is not claimable, skipping",
                extra={"event": "agent_run_skipped", "run_id": str(run_id)},
            )
            return ProcessResult.ACK
        if attempt > self.max_attempts:
            await self._fail(
                run_id,
                attempt,
                code="run_timeout",
                message="The run exceeded the retry limit",
            )
            return ProcessResult.ACK
        try:
            async with asyncio.timeout(self.timeout_seconds):
                context = await self._load_context(run_id)
                response = await self.prompt_editor_agent.respond(
                    agent_context=context.agent_context,
                    messages=context.messages,
                    base_prompt_content=context.base_prompt_content,
                )
            _validate_response(response)
            if not await self._complete(run_id, attempt, response):
                logger.warning(
                    "Agent run was taken over by another attempt, discarding result",
                    extra={"event": "agent_run_fenced", "run_id": str(run_id)},
                )
        except SQLAlchemyError:
            raise
        except Exception as error:
            logger.exception(
                "Agent run processing failed",
                extra={"event": "agent_run_failed", "run_id": str(run_id)},
            )
            await self._handle_error(run_id, attempt, error)
        return ProcessResult.ACK

    async def _claim(self, run_id: UUID) -> int | None:
        async with self.session_maker() as session:
            attempt = await AgentRunRepository(session).claim_by_id(
                run_id, now=datetime.now(UTC)
            )
            await session.commit()
            return attempt

    async def _load_context(self, run_id: UUID) -> EditorContext:
        async with self.session_maker() as session:
            run = await AgentRunRepository(session).get_for_processing(run_id)
            if run is None:
                raise InvalidInputError("Agent run no longer exists")
            history = await MessageRepository(session).list_before_for_editing(
                run.session_id,
                run.user_message_id,
                run.session.user_id,
            )
            return prepare_editor_context(run.session, run.user_message, history)

    async def _complete(
        self, run_id: UUID, attempt: int, response: PromptEditorResponse
    ) -> bool:
        async with self.session_maker() as session:
            runs = AgentRunRepository(session)
            loaded = await runs.get_for_processing(run_id)
            if loaded is None:
                raise InvalidInputError("Agent run no longer exists")
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
            completed = await runs.mark_completed(
                run_id, attempt, assistant.id, now=datetime.now(UTC)
            )
            if completed:
                await session.commit()
            else:
                await session.rollback()
            return completed

    async def _fail(self, run_id: UUID, attempt: int, *, code: str, message: str) -> bool:
        async with self.session_maker() as session:
            failed = await AgentRunRepository(session).mark_error(
                run_id,
                attempt,
                code=code,
                message=message,
                retry=False,
                now=datetime.now(UTC),
            )
            await session.commit()
            return failed

    async def _handle_error(self, run_id: UUID, attempt: int, error: Exception) -> None:
        transient = _is_transient(error)
        code, message = _safe_error(error, transient)
        retry = transient and attempt < self.max_attempts
        async with self.session_maker() as session:
            changed = await AgentRunRepository(session).mark_error(
                run_id,
                attempt,
                code=code,
                message=message,
                retry=retry,
                now=datetime.now(UTC),
            )
            await session.commit()
        if not changed or not retry:
            return
        try:
            await self.publisher.publish_retry(run_id)
        except QueueUnavailableError:
            async with self.session_maker() as session:
                await AgentRunRepository(session).mark_failed(
                    run_id,
                    code="queue_unavailable",
                    message="The processing queue is temporarily unavailable",
                    now=datetime.now(UTC),
                )
                await session.commit()


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
