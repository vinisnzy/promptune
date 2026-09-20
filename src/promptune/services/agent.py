import logging
from collections.abc import Sequence
from uuid import UUID

from promptune.core.exceptions import InvalidInputError, NotFoundError
from promptune.models.agent import Agent
from promptune.repositories.agent import IAgentRepository
from promptune.schemas.agent import AgentCreate, AgentUpdate

logger = logging.getLogger(__name__)


class AgentService:
    def __init__(self, repository: IAgentRepository) -> None:
        self.repository = repository

    async def get_all_agents(
        self, page: int, size: int, query: str | None = None
    ) -> Sequence[Agent]:
        if page < 1 or size < 1:
            raise InvalidInputError("page and size must be positive integers")

        query = query.strip() if query else None
        return await self.repository.get_all_agents(page, size, query or None)

    async def get_agent_by_id(self, agent_id: UUID) -> Agent:
        agent = await self.repository.get_agent_by_id(agent_id)
        if agent is None:
            logger.warning("Agent not found", extra={"agent_id": str(agent_id)})
            raise NotFoundError(f"Agent not found with id: {agent_id}")
        return agent

    async def add_agent(self, data: AgentCreate) -> Agent:
        agent = await self.repository.add_agent(data.model_dump())
        logger.info("Agent created", extra={"agent_id": str(agent.id)})
        return agent

    async def update_agent(self, agent_id: UUID, data: AgentUpdate) -> Agent:
        agent = await self.repository.update_agent(
            agent_id, data.model_dump(exclude_unset=True)
        )
        if agent is None:
            logger.warning(
                "Agent not found for update", extra={"agent_id": str(agent_id)}
            )
            raise NotFoundError(f"Agent not found with id: {agent_id}")

        logger.info("Agent updated", extra={"agent_id": str(agent_id)})
        return agent

    async def delete_agent(self, agent_id: UUID) -> None:
        deleted = await self.repository.delete_agent(agent_id)
        if not deleted:
            logger.warning(
                "Agent not found for deletion", extra={"agent_id": str(agent_id)}
            )
            raise NotFoundError(f"Agent not found with id: {agent_id}")

        logger.info("Agent deleted", extra={"agent_id": str(agent_id)})
