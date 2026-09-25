from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from promptune.models.prompt import Prompt
from promptune.repositories.prompt import IPromptRepository
from tests.unit.agent.in_memory_repository import InMemoryAgentRepository


class InMemoryPromptRepository(IPromptRepository):
    def __init__(self, agents: InMemoryAgentRepository) -> None:
        self.agents = agents
        self.prompts: dict[UUID, Prompt] = {}

    async def get_prompts_by_agent(
        self, agent_id: UUID, page: int, size: int
    ) -> Sequence[Prompt]:
        if await self.agents.get_agent_by_id(agent_id) is None:
            return []
        prompts = [
            prompt for prompt in self.prompts.values() if prompt.agent_id == agent_id
        ]
        prompts.sort(key=lambda prompt: (prompt.created_at, prompt.id), reverse=True)
        return prompts[(page - 1) * size : page * size]

    async def get_prompt_by_id(self, prompt_id: UUID) -> Prompt | None:
        prompt = self.prompts.get(prompt_id)
        if prompt is None or await self.agents.get_agent_by_id(prompt.agent_id) is None:
            return None
        return prompt

    async def get_current_prompt_by_agent(self, agent_id: UUID) -> Prompt | None:
        if await self.agents.get_agent_by_id(agent_id) is None:
            return None
        prompts = [
            prompt for prompt in self.prompts.values() if prompt.agent_id == agent_id
        ]
        return max(prompts, key=lambda prompt: prompt.version, default=None)

    async def add_prompt(self, data: dict[str, Any]) -> Prompt | None:
        agent_id = data["agent_id"]
        if await self.agents.get_agent_by_id(agent_id) is None:
            return None
        version = 1 + max(
            (
                prompt.version
                for prompt in self.prompts.values()
                if prompt.agent_id == agent_id
            ),
            default=0,
        )
        now = datetime.now(UTC)
        prompt = Prompt(
            id=uuid4(),
            created_at=now,
            updated_at=now,
            agent_id=agent_id,
            content=data["content"],
            description=data.get("description") or f"v{version}",
            version=version,
        )
        self.prompts[prompt.id] = prompt
        return prompt
