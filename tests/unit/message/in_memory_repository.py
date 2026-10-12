from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from promptune.core.exceptions import ConflictError, InvalidInputError, NotFoundError
from promptune.modules.message.model import Message, MessageRole
from promptune.modules.message.repository import IMessageRepository
from promptune.modules.session.model import SessionStatus
from tests.unit.session.in_memory_repository import InMemorySessionRepository


class InMemoryMessageRepository(IMessageRepository):
    def __init__(self, sessions: InMemorySessionRepository) -> None:
        self.sessions = sessions
        self.messages: dict[UUID, Message] = {}
        self.proposal_sessions: dict[UUID, UUID] = {}

    async def create(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        role: MessageRole,
        content: str,
        reply_to_id: UUID | None = None,
        base_proposal_id: UUID | None = None,
        questions: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> Message:
        conversation = await self.sessions.get_by_id(session_id, user_id)
        if conversation is None:
            raise InvalidInputError("Session does not exist")
        if conversation.status != SessionStatus.ACTIVE:
            raise ConflictError("Session is completed")
        if role not in (MessageRole.USER, MessageRole.ASSISTANT):
            raise InvalidInputError("Invalid message role")
        if reply_to_id is not None:
            reply = self.messages.get(reply_to_id)
            if reply is None or reply.session_id != session_id:
                raise InvalidInputError("Reply target must belong to this session")
        if (
            base_proposal_id is not None
            and self.proposal_sessions.get(base_proposal_id) != session_id
        ):
            raise InvalidInputError("Base proposal must belong to this session")
        now = datetime.now(UTC)
        message = Message(
            id=uuid4(),
            session_id=session_id,
            role=role,
            content=content,
            reply_to_id=reply_to_id,
            base_proposal_id=base_proposal_id,
            questions=list(questions or []),
            warnings=list(warnings or []),
            created_at=now,
            updated_at=now,
        )
        self.messages[message.id] = message
        return message

    async def get_by_id(
        self, message_id: UUID, session_id: UUID, user_id: UUID
    ) -> Message | None:
        if await self.sessions.get_by_id(session_id, user_id) is None:
            return None
        message = self.messages.get(message_id)
        if message is None or message.session_id != session_id:
            return None
        return message

    async def list_by_session(
        self, session_id: UUID, user_id: UUID, page: int, size: int
    ) -> Sequence[Message]:
        if await self.sessions.get_by_id(session_id, user_id) is None:
            return []
        messages = [
            message
            for message in self.messages.values()
            if message.session_id == session_id
        ]
        messages.sort(key=lambda message: (message.created_at, message.id))
        return messages[(page - 1) * size : page * size]

    async def list_before_for_editing(
        self, session_id: UUID, message_id: UUID, user_id: UUID
    ) -> Sequence[Message]:
        current = await self.get_by_id(message_id, session_id, user_id)
        if current is None:
            raise NotFoundError("Message does not exist in this session")
        return [
            message
            for message in await self.list_by_session(
                session_id, user_id, 1, len(self.messages) or 1
            )
            if (message.created_at, message.id) < (current.created_at, current.id)
        ]

    def add_proposal(self, proposal_id: UUID, session_id: UUID) -> None:
        self.proposal_sessions[proposal_id] = session_id
