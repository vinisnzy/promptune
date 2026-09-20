from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from promptune.models.agent import Agent
from promptune.models.prompt import Prompt


class IPromptRepository(ABC):
    @abstractmethod
    async def get_prompts_by_agent(
        self, agent_id: UUID, page: int, size: int
    ) -> Sequence[Prompt]:
        pass

    @abstractmethod
    async def get_prompt_by_id(self, prompt_id: UUID) -> Prompt | None:
        pass

    @abstractmethod
    async def get_current_prompt_by_agent(self, agent_id: UUID) -> Prompt | None:
        pass

    @abstractmethod
    async def add_prompt(self, data: dict[str, Any]) -> Prompt | None:
        pass


class PromptRepository(IPromptRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_prompts_by_agent(
        self, agent_id: UUID, page: int, size: int
    ) -> Sequence[Prompt]:
        offset = (page - 1) * size
        stmt = (
            select(Prompt)
            .join(Agent)
            .where(Prompt.agent_id == agent_id, Agent.deleted_at.is_(None))
            .order_by(Prompt.created_at.desc(), Prompt.id.desc())
            .offset(offset)
            .limit(size)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_prompt_by_id(self, prompt_id: UUID) -> Prompt | None:
        stmt = (
            select(Prompt)
            .join(Agent)
            .where(Prompt.id == prompt_id, Agent.deleted_at.is_(None))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_current_prompt_by_agent(self, agent_id: UUID) -> Prompt | None:
        stmt = (
            select(Prompt)
            .join(Agent)
            .where(Prompt.agent_id == agent_id, Agent.deleted_at.is_(None))
            .order_by(Prompt.version.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_prompt(self, data: dict[str, Any]) -> Prompt | None:
        agent_id = data["agent_id"]
        agent_stmt = (
            select(Agent)
            .where(Agent.id == agent_id, Agent.deleted_at.is_(None))
            .with_for_update()
        )
        agent = (await self.session.execute(agent_stmt)).scalar_one_or_none()
        if agent is None:
            return None

        version_stmt = select(func.max(Prompt.version)).where(
            Prompt.agent_id == agent_id
        )
        current_version = (await self.session.execute(version_stmt)).scalar_one()
        version = (current_version or 0) + 1
        prompt = Prompt(
            agent_id=agent_id,
            content=data["content"],
            description=data.get("description") or f"v{version}",
            version=version,
        )
        self.session.add(prompt)
        await self.session.commit()
        await self.session.refresh(prompt)
        return prompt
