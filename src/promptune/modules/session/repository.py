from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from promptune.core.exceptions import InvalidInputError
from promptune.modules.agent.model import Agent
from promptune.modules.auth.models.user import User
from promptune.modules.prompt.model import Prompt
from promptune.modules.session.model import Session, SessionStatus


def _check_page(page: int, size: int) -> None:
    if page < 1 or size < 1:
        raise InvalidInputError("page and size must be positive")


class ISessionRepository(ABC):
    @abstractmethod
    async def list_by_user(
        self,
        user_id: UUID,
        page: int,
        size: int,
        agent_id: UUID | None = None,
        status: SessionStatus | None = None,
    ) -> Sequence[Session]: ...

    @abstractmethod
    async def get_by_id(self, session_id: UUID, user_id: UUID) -> Session | None: ...

    @abstractmethod
    async def create(
        self, *, user_id: UUID, agent_id: UUID, base_prompt_id: UUID
    ) -> Session: ...

    @abstractmethod
    async def complete(self, session_id: UUID, user_id: UUID) -> Session | None: ...


class SessionRepository(ISessionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_user(
        self,
        user_id: UUID,
        page: int,
        size: int,
        agent_id: UUID | None = None,
        status: SessionStatus | None = None,
    ) -> Sequence[Session]:
        _check_page(page, size)
        stmt = (
            select(Session)
            .join(Agent, Session.agent_id == Agent.id)
            .where(Session.user_id == user_id, Agent.deleted_at.is_(None))
        )
        if agent_id is not None:
            stmt = stmt.where(Session.agent_id == agent_id)
        if status is not None:
            stmt = stmt.where(Session.status == status)
        stmt = (
            stmt.order_by(Session.created_at.desc(), Session.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def get_by_id(self, session_id: UUID, user_id: UUID) -> Session | None:
        stmt = (
            select(Session)
            .join(Agent, Session.agent_id == Agent.id)
            .where(
                Session.id == session_id,
                Session.user_id == user_id,
                Agent.deleted_at.is_(None),
            )
            .options(selectinload(Session.agent), selectinload(Session.base_prompt))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create(
        self, *, user_id: UUID, agent_id: UUID, base_prompt_id: UUID
    ) -> Session:
        agent_stmt = select(Agent.id).where(
            Agent.id == agent_id, Agent.deleted_at.is_(None)
        )
        prompt_stmt = select(Prompt.id).where(
            Prompt.id == base_prompt_id, Prompt.agent_id == agent_id
        )
        user_stmt = select(User.id).where(User.id == user_id, User.deleted_at.is_(None))
        if (
            (await self.session.execute(agent_stmt)).scalar_one_or_none() is None
            or (await self.session.execute(prompt_stmt)).scalar_one_or_none() is None
            or (await self.session.execute(user_stmt)).scalar_one_or_none() is None
        ):
            raise InvalidInputError("Invalid user, agent, or base prompt")
        conversation = Session(
            user_id=user_id,
            agent_id=agent_id,
            base_prompt_id=base_prompt_id,
            status=SessionStatus.ACTIVE,
        )
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def complete(self, session_id: UUID, user_id: UUID) -> Session | None:
        stmt = (
            select(Session)
            .join(Agent, Session.agent_id == Agent.id)
            .where(
                Session.id == session_id,
                Session.user_id == user_id,
                Agent.deleted_at.is_(None),
            )
            .with_for_update(of=Session)
        )
        conversation = (await self.session.execute(stmt)).scalar_one_or_none()
        if conversation is None:
            return None
        if conversation.status != SessionStatus.COMPLETED:
            conversation.status = SessionStatus.COMPLETED
            await self.session.flush()
        return conversation
