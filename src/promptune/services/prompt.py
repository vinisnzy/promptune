import logging
from collections.abc import Sequence
from uuid import UUID

from promptune.core.exceptions import InvalidInputError, NotFoundError
from promptune.models.prompt import Prompt
from promptune.repositories.prompt import IPromptRepository
from promptune.schemas.prompt import PromptCreate

logger = logging.getLogger(__name__)


class PromptService:
    def __init__(self, repository: IPromptRepository) -> None:
        self.repository = repository

    async def get_prompts_by_agent(
        self, agent_id: UUID, page: int, size: int
    ) -> Sequence[Prompt]:
        if page < 1 or size < 1:
            raise InvalidInputError("page and size must be positive integers")

        return await self.repository.get_prompts_by_agent(agent_id, page, size)

    async def get_prompt_by_id(self, prompt_id: UUID) -> Prompt:
        prompt = await self.repository.get_prompt_by_id(prompt_id)
        if prompt is None:
            logger.warning("Prompt not found", extra={"prompt_id": str(prompt_id)})
            raise NotFoundError(f"Prompt not found with id: {prompt_id}")
        return prompt

    async def get_current_prompt_by_agent(self, agent_id: UUID) -> Prompt:
        prompt = await self.repository.get_current_prompt_by_agent(agent_id)
        if prompt is None:
            logger.warning(
                "Current prompt not found", extra={"agent_id": str(agent_id)}
            )
            raise NotFoundError(f"Current prompt not found for agent: {agent_id}")
        return prompt

    async def add_prompt(self, data: PromptCreate) -> Prompt:
        prompt = await self.repository.add_prompt(data.model_dump())
        if prompt is None:
            logger.warning(
                "Agent not found for prompt creation",
                extra={"agent_id": str(data.agent_id)},
            )
            raise NotFoundError(f"Agent not found with id: {data.agent_id}")

        logger.info(
            "Prompt created",
            extra={
                "prompt_id": str(prompt.id),
                "agent_id": str(prompt.agent_id),
                "version": prompt.version,
            },
        )
        return prompt
