from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from promptune.modules.session.model import Session, SessionStatus
from promptune.modules.session.repository import ISessionRepository


class InMemorySessionRepository(ISessionRepository):
    def __init__(self) -> None:
        self.sessions: dict[UUID, Session] = {}

    async def list_by_user(
        self,
        user_id: UUID,
        page: int,
        size: int,
        agent_id: UUID | None = None,
        status: SessionStatus | None = None,
    ) -> Sequence[Session]:
        conversations = [
            conversation
            for conversation in self.sessions.values()
            if conversation.user_id == user_id
            and conversation.deleted_at is None
            and (agent_id is None or conversation.agent_id == agent_id)
            and (status is None or conversation.status == status)
        ]
        conversations.sort(
            key=lambda conversation: (conversation.created_at, conversation.id),
            reverse=True,
        )
        return conversations[(page - 1) * size : page * size]

    async def get_by_id(self, session_id: UUID, user_id: UUID) -> Session | None:
        conversation = self.sessions.get(session_id)
        if (
            conversation is None
            or conversation.user_id != user_id
            or conversation.deleted_at is not None
        ):
            return None
        return conversation

    async def create(
        self, *, user_id: UUID, agent_id: UUID, base_prompt_id: UUID
    ) -> Session:
        now = datetime.now(UTC)
        conversation = Session(
            id=uuid4(),
            user_id=user_id,
            agent_id=agent_id,
            base_prompt_id=base_prompt_id,
            status=SessionStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        self.sessions[conversation.id] = conversation
        return conversation

    async def complete(self, session_id: UUID, user_id: UUID) -> Session | None:
        conversation = await self.get_by_id(session_id, user_id)
        if conversation is None:
            return None
        conversation.status = SessionStatus.COMPLETED
        conversation.updated_at = datetime.now(UTC)
        return conversation

    async def delete(self, session_id: UUID, user_id: UUID) -> bool:
        conversation = await self.get_by_id(session_id, user_id)
        if conversation is None:
            return False
        now = datetime.now(UTC)
        conversation.deleted_at = now
        conversation.updated_at = now
        return True
