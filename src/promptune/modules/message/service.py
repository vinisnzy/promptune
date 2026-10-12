from collections.abc import Sequence
from uuid import UUID

from promptune.core.exceptions import ConflictError, InvalidInputError, NotFoundError
from promptune.modules.message.model import Message, MessageRole
from promptune.modules.message.repository import IMessageRepository
from promptune.modules.message.schema import MessageSend
from promptune.modules.session.model import Session, SessionStatus
from promptune.modules.session.repository import ISessionRepository


class MessageService:
    def __init__(
        self,
        repository: IMessageRepository,
        session_repository: ISessionRepository,
    ) -> None:
        self.repository = repository
        self.session_repository = session_repository

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
    ) -> Message:
        content = data.content.strip()
        if not content:
            raise InvalidInputError("content must not be blank")
        conversation = await self._get_session(session_id, user_id)
        if conversation.status != SessionStatus.ACTIVE:
            raise ConflictError("Session is not active")
        return await self.repository.create(
            session_id=session_id,
            user_id=user_id,
            role=MessageRole.USER,
            content=content,
            base_proposal_id=data.base_proposal_id,
        )

    async def _get_session(self, session_id: UUID, user_id: UUID) -> Session:
        conversation = await self.session_repository.get_by_id(session_id, user_id)
        if conversation is None:
            raise NotFoundError(f"Session not found with id: {session_id}")
        return conversation
