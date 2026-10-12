from collections.abc import Sequence
from uuid import UUID

from promptune.core.exceptions import InvalidInputError, NotFoundError
from promptune.modules.session.model import Session, SessionStatus
from promptune.modules.session.repository import ISessionRepository
from promptune.modules.session.schema import SessionCreate


class SessionService:
    def __init__(self, repository: ISessionRepository) -> None:
        self.repository = repository

    async def list_sessions(
        self,
        user_id: UUID,
        page: int,
        size: int,
        agent_id: UUID | None = None,
        status: SessionStatus | None = None,
    ) -> Sequence[Session]:
        if page < 1 or size < 1:
            raise InvalidInputError("page and size must be positive integers")
        if status is not None:
            try:
                status = SessionStatus(status)
            except ValueError as error:
                raise InvalidInputError("Invalid session status") from error
        return await self.repository.list_by_user(
            user_id, page, size, agent_id=agent_id, status=status
        )

    async def get_session_by_id(self, session_id: UUID, user_id: UUID) -> Session:
        conversation = await self.repository.get_by_id(session_id, user_id)
        if conversation is None:
            raise NotFoundError(f"Session not found with id: {session_id}")
        return conversation

    async def create_session(self, user_id: UUID, data: SessionCreate) -> Session:
        return await self.repository.create(
            user_id=user_id,
            agent_id=data.agent_id,
            base_prompt_id=data.base_prompt_id,
        )

    async def complete_session(self, session_id: UUID, user_id: UUID) -> Session:
        conversation = await self.repository.complete(session_id, user_id)
        if conversation is None:
            raise NotFoundError(f"Session not found with id: {session_id}")
        return conversation

    async def delete_session(self, session_id: UUID, user_id: UUID) -> None:
        if not await self.repository.delete(session_id, user_id):
            raise NotFoundError(f"Session not found with id: {session_id}")
