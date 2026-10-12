from collections.abc import Sequence
from uuid import UUID

from promptune.core.exceptions import InvalidInputError, NotFoundError
from promptune.modules.prompt_proposal.model import PromptProposal
from promptune.modules.prompt_proposal.repository import IPromptProposalRepository


class PromptProposalService:
    def __init__(self, repository: IPromptProposalRepository) -> None:
        self.repository = repository

    async def list_by_agent(
        self, agent_id: UUID, user_id: UUID, page: int, size: int
    ) -> Sequence[PromptProposal]:
        if page < 1 or size < 1:
            raise InvalidInputError("page and size must be positive integers")
        return await self.repository.list_by_agent(agent_id, user_id, page, size)

    async def get_by_id(
        self, prompt_proposal_id: UUID, user_id: UUID
    ) -> PromptProposal:
        proposal = await self.repository.get_by_id(prompt_proposal_id, user_id)
        if proposal is None:
            raise NotFoundError(
                f"Prompt proposal not found with id: {prompt_proposal_id}"
            )
        return proposal

    async def approve(self, prompt_proposal_id: UUID, user_id: UUID) -> PromptProposal:
        proposal = await self.repository.approve(prompt_proposal_id, user_id)
        if proposal is None:
            raise NotFoundError(
                f"Prompt proposal not found with id: {prompt_proposal_id}"
            )
        return proposal

    async def discard(self, prompt_proposal_id: UUID, user_id: UUID) -> PromptProposal:
        proposal = await self.repository.discard(prompt_proposal_id, user_id)
        if proposal is None:
            raise NotFoundError(
                f"Prompt proposal not found with id: {prompt_proposal_id}"
            )
        return proposal
