from collections.abc import Sequence
from uuid import UUID

from promptune.agents.prompt_editor.agent import (
    IPromptEditorAgent,
)
from promptune.core.exceptions import InvalidInputError, NotFoundError
from promptune.modules.agent.repository import IAgentRepository
from promptune.modules.prompt.repository import IPromptRepository
from promptune.modules.prompt_proposal.model import PromptProposal
from promptune.modules.prompt_proposal.repository import IPromptProposalRepository
from promptune.modules.prompt_proposal.schema import PromptProposalCreate


class PromptProposalService:
    def __init__(
        self,
        repository: IPromptProposalRepository,
        prompt_repository: IPromptRepository,
        agent_repository: IAgentRepository,
        prompt_editor_agent: IPromptEditorAgent,
    ) -> None:
        self.repository = repository
        self.prompt_repository = prompt_repository
        self.agent_repository = agent_repository
        self.prompt_editor_agent = prompt_editor_agent

    async def list_by_agent(
        self, agent_id: UUID, page: int, size: int
    ) -> Sequence[PromptProposal]:
        if page < 1 or size < 1:
            raise InvalidInputError("page and size must be positive integers")
        return await self.repository.list_by_agent(agent_id, page, size)

    async def get_by_id(self, prompt_proposal_id: UUID) -> PromptProposal:
        prompt_proposal = await self.repository.get_by_id(prompt_proposal_id)
        if prompt_proposal is None:
            raise NotFoundError(
                f"Prompt proposal not found with id: {prompt_proposal_id}"
            )
        return prompt_proposal

    async def create(self, data: PromptProposalCreate) -> PromptProposal:
        change_request = data.change_request.strip()
        if not change_request:
            raise InvalidInputError("change_request must not be blank")

        prompt = await self.prompt_repository.get_prompt_by_id(data.source_prompt_id)
        if prompt is None:
            raise NotFoundError(f"Prompt not found with id: {data.source_prompt_id}")
        agent = await self.agent_repository.get_agent_by_id(prompt.agent_id)
        if agent is None:
            raise NotFoundError(f"Agent not found with id: {prompt.agent_id}")

        draft = await self.prompt_editor_agent.respond(
            prompt.content, prompt.description, agent.context, change_request
        )
        if not draft.proposed_content.strip():
            raise InvalidInputError("Generated prompt proposal content must not be blank")
        prompt_proposal = await self.repository.create(prompt.id, change_request, draft)
        if prompt_proposal is None:
            raise NotFoundError(f"Prompt not found with id: {data.source_prompt_id}")
        return prompt_proposal

    async def approve(self, prompt_proposal_id: UUID) -> PromptProposal:
        prompt_proposal = await self.repository.approve(prompt_proposal_id)
        if prompt_proposal is None:
            raise NotFoundError(
                f"Prompt proposal not found with id: {prompt_proposal_id}"
            )
        return prompt_proposal

    async def discard(self, prompt_proposal_id: UUID) -> PromptProposal:
        prompt_proposal = await self.repository.discard(prompt_proposal_id)
        if prompt_proposal is None:
            raise NotFoundError(
                f"Prompt proposal not found with id: {prompt_proposal_id}"
            )
        return prompt_proposal
