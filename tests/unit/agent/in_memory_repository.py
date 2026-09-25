from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from promptune.models.agent import Agent
from promptune.repositories.agent import IAgentRepository


class InMemoryAgentRepository(IAgentRepository):
    def __init__(self) -> None:
        self.agents: dict[UUID, Agent] = {}

    async def get_all_agents(
        self, page: int, size: int, query: str | None = None
    ) -> Sequence[Agent]:
        agents = [agent for agent in self.agents.values() if agent.deleted_at is None]
        agents.sort(key=lambda agent: (agent.created_at, agent.id), reverse=True)
        if query:
            term = query.casefold()
            agents = [
                agent
                for agent in agents
                if term in agent.name.casefold()
                or term in (agent.description or "").casefold()
            ]
            agents.sort(key=lambda agent: not agent.name.casefold().startswith(term))
        return agents[(page - 1) * size : page * size]

    async def get_agent_by_id(self, agent_id: UUID) -> Agent | None:
        agent = self.agents.get(agent_id)
        return agent if agent is not None and agent.deleted_at is None else None

    async def add_agent(self, data: dict[str, Any]) -> Agent:
        now = datetime.now(UTC)
        agent = Agent(id=uuid4(), created_at=now, updated_at=now, **data)
        self.agents[agent.id] = agent
        return agent

    async def update_agent(self, agent_id: UUID, data: dict[str, Any]) -> Agent | None:
        agent = await self.get_agent_by_id(agent_id)
        if agent is None:
            return None
        for field, value in data.items():
            setattr(agent, field, value)
        if data:
            agent.updated_at = datetime.now(UTC)
        return agent

    async def delete_agent(self, agent_id: UUID) -> bool:
        agent = await self.get_agent_by_id(agent_id)
        if agent is None:
            return False
        agent.deleted_at = datetime.now(UTC)
        return True
