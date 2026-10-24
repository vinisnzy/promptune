from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from promptune.core.exceptions import ConflictError, InvalidInputError, NotFoundError
from promptune.modules.agent_run.model import AgentRun
from promptune.modules.agent_run.queue import IRunPublisher, QueueUnavailableError
from promptune.modules.agent_run.repository import IAgentRunRepository
from promptune.modules.message.model import Message, MessageRole
from promptune.modules.message.repository import IMessageRepository
from promptune.modules.message.schema import MessageSend
from promptune.modules.session.model import Session, SessionStatus
from promptune.modules.session.repository import ISessionRepository


@dataclass(frozen=True)
class MessageDispatch:
    message: Message
    run: AgentRun


class MessageService:
    def __init__(
        self,
        repository: IMessageRepository,
        session_repository: ISessionRepository,
        agent_run_repository: IAgentRunRepository,
        publisher: IRunPublisher,
        commit: Callable[[], Awaitable[None]],
    ) -> None:
        self.repository = repository
        self.session_repository = session_repository
        self.agent_run_repository = agent_run_repository
        self.publisher = publisher
        self.commit = commit

    async def list_messages(
        self, session_id: UUID, user_id: UUID, page: int, size: int
    ) -> Sequence[Message]:
        if page < 1 or size < 1:
            raise InvalidInputError("page and size must be positive integers")
        await self._get_session(session_id, user_id)
        return await self.repository.list_by_session(session_id, user_id, page, size)

    async def get_message_by_id(
        self, message_id: UUID, session_id: UUID, user_id: UUID
    ) -> Message:
        message = await self.repository.get_by_id(message_id, session_id, user_id)
        if message is None:
            raise NotFoundError(f"Message not found with id: {message_id}")
        return message

    async def send_message(
        self, session_id: UUID, user_id: UUID, data: MessageSend
    ) -> MessageDispatch:
        content = data.content.strip()
        if not content:
            raise InvalidInputError("content must not be blank")
        conversation = await self._get_session(session_id, user_id)
        if conversation.status != SessionStatus.ACTIVE:
            raise ConflictError("Session is not active")
        message = await self.repository.create(
            session_id=session_id,
            user_id=user_id,
            role=MessageRole.USER,
            content=content,
            base_proposal_id=data.base_proposal_id,
        )
        try:
            run = await self.agent_run_repository.create(
                session_id=session_id, user_message_id=message.id
            )
        except IntegrityError as error:
            raise ConflictError("Session already has an active agent run") from error
        # The worker can only find the run once it is committed, so publish after.
        await self.commit()
        try:
            await self.publisher.publish_run(run.id)
        except QueueUnavailableError:
            # Release the one-active-run-per-session slot so the user can resend.
            await self.agent_run_repository.mark_failed(
                run.id,
                code="queue_unavailable",
                message="The processing queue is temporarily unavailable",
                now=datetime.now(UTC),
            )
            await self.commit()
            raise
        return MessageDispatch(message=message, run=run)

    async def _get_session(self, session_id: UUID, user_id: UUID) -> Session:
        conversation = await self.session_repository.get_by_id(session_id, user_id)
        if conversation is None:
            raise NotFoundError(f"Session not found with id: {session_id}")
        return conversation
