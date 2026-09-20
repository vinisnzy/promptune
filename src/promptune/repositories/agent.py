from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from promptune.models.agent import Agent


class IAgentRepository(ABC):
    @abstractmethod
    async def get_all_agents(self, page: int, size: int) -> Sequence[Agent]:
        pass

    @abstractmethod
    async def get_agent_by_id(self, agent_id: UUID) -> Agent | None:
        pass

    @abstractmethod
    async def add_agent(self, data: dict[str, Any]) -> Agent:
        pass

    @abstractmethod
    async def update_agent(self, agent_id: UUID, data: dict[str, Any]) -> Agent | None:
        pass

    @abstractmethod
    async def delete_agent(self, agent_id: UUID) -> bool:
        pass


class AgentRepository(IAgentRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_all_agents(self, page: int, size: int) -> Sequence[Agent]:
        offset = (page - 1) * size
        stmt = (
            select(Agent)
            .where(Agent.deleted_at.is_(None))
            .order_by(Agent.created_at.desc(), Agent.id.desc())
            .offset(offset)
            .limit(size)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_agent_by_id(self, agent_id: UUID) -> Agent | None:
        stmt = select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_agent(self, data: dict[str, Any]) -> Agent:
        agent = Agent(**data)
        self.session.add(agent)
        await self.session.commit()
        await self.session.refresh(agent)
        return agent

    async def update_agent(self, agent_id: UUID, data: dict[str, Any]) -> Agent | None:
        agent = await self.get_agent_by_id(agent_id)
        if agent is None:
            return None

        for field, value in data.items():
            setattr(agent, field, value)
        if data:
            await self.session.commit()
            await self.session.refresh(agent)
        return agent

    async def delete_agent(self, agent_id: UUID) -> bool:
        agent = await self.get_agent_by_id(agent_id)
        if agent is None:
            return False

        agent.deleted_at = datetime.now(UTC)
        await self.session.commit()
        return True
