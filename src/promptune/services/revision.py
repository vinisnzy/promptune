from collections.abc import Sequence
from uuid import UUID

from promptune.agents.prompt_revision.agent import (
    IPromptRevisionAgent,
)
from promptune.core.exceptions import InvalidInputError, NotFoundError
from promptune.models.revision import Revision
from promptune.repositories.agent import IAgentRepository
from promptune.repositories.prompt import IPromptRepository
from promptune.repositories.revision import IRevisionRepository
from promptune.schemas.revision import RevisionCreate


class RevisionService:
    def __init__(
        self,
        repository: IRevisionRepository,
        prompt_repository: IPromptRepository,
        agent_repository: IAgentRepository,
        prompt_revision_agent: IPromptRevisionAgent,
    ) -> None:
        self.repository = repository
        self.prompt_repository = prompt_repository
        self.agent_repository = agent_repository
        self.prompt_revision_agent = prompt_revision_agent

    async def list_by_agent(
        self, agent_id: UUID, page: int, size: int
    ) -> Sequence[Revision]:
        if page < 1 or size < 1:
            raise InvalidInputError("page and size must be positive integers")
        return await self.repository.list_by_agent(agent_id, page, size)

    async def get_by_id(self, revision_id: UUID) -> Revision:
        revision = await self.repository.get_by_id(revision_id)
        if revision is None:
            raise NotFoundError(f"Revision not found with id: {revision_id}")
        return revision

    async def create(self, data: RevisionCreate) -> Revision:
        change_request = data.change_request.strip()
        if not change_request:
            raise InvalidInputError("change_request must not be blank")

        prompt = await self.prompt_repository.get_prompt_by_id(data.source_prompt_id)
        if prompt is None:
            raise NotFoundError(f"Prompt not found with id: {data.source_prompt_id}")
        agent = await self.agent_repository.get_agent_by_id(prompt.agent_id)
        if agent is None:
            raise NotFoundError(f"Agent not found with id: {prompt.agent_id}")

        draft = await self.prompt_revision_agent.generate(
            prompt.content, prompt.description, agent.context, change_request
        )
        if not draft.proposed_content.strip():
            raise InvalidInputError("Generated revision content must not be blank")
        revision = await self.repository.create(prompt.id, change_request, draft)
        if revision is None:
            raise NotFoundError(f"Prompt not found with id: {data.source_prompt_id}")
        return revision

    async def approve(self, revision_id: UUID) -> Revision:
        revision = await self.repository.approve(revision_id)
        if revision is None:
            raise NotFoundError(f"Revision not found with id: {revision_id}")
        return revision

    async def discard(self, revision_id: UUID) -> Revision:
        revision = await self.repository.discard(revision_id)
        if revision is None:
            raise NotFoundError(f"Revision not found with id: {revision_id}")
        return revision
