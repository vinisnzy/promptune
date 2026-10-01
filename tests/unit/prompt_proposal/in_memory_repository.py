from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from promptune.core.exceptions import ConflictError
from promptune.modules.prompt_proposal.model import (
    PromptProposal,
    PromptProposalStatus,
)
from promptune.modules.prompt_proposal.repository import IPromptProposalRepository
from promptune.modules.prompt_proposal.schema import PromptProposalDraft
from tests.unit.agent.in_memory_repository import InMemoryAgentRepository
from tests.unit.prompt.in_memory_repository import InMemoryPromptRepository


class InMemoryPromptProposalRepository(IPromptProposalRepository):
    def __init__(
        self,
        agents: InMemoryAgentRepository,
        prompts: InMemoryPromptRepository,
    ) -> None:
        self.agents = agents
        self.prompts = prompts
        self.prompt_proposals: dict[UUID, PromptProposal] = {}

    async def list_by_agent(
        self, agent_id: UUID, page: int, size: int
    ) -> Sequence[PromptProposal]:
        if await self.agents.get_agent_by_id(agent_id) is None:
            return []
        prompt_proposals = [
            prompt_proposal
            for prompt_proposal in self.prompt_proposals.values()
            if prompt_proposal.agent_id == agent_id
        ]
        prompt_proposals.sort(
            key=lambda prompt_proposal: (
                prompt_proposal.created_at,
                prompt_proposal.id,
            ),
            reverse=True,
        )
        return prompt_proposals[(page - 1) * size : page * size]

    async def get_by_id(self, prompt_proposal_id: UUID) -> PromptProposal | None:
        prompt_proposal = self.prompt_proposals.get(prompt_proposal_id)
        if (
            prompt_proposal is None
            or await self.agents.get_agent_by_id(prompt_proposal.agent_id) is None
        ):
            return None
        return prompt_proposal

    async def create(
        self,
        source_prompt_id: UUID,
        change_request: str,
        draft: PromptProposalDraft,
    ) -> PromptProposal | None:
        source = await self.prompts.get_prompt_by_id(source_prompt_id)
        if source is None:
            return None
        now = datetime.now(UTC)
        prompt_proposal = PromptProposal(
            id=uuid4(),
            created_at=now,
            updated_at=now,
            agent_id=source.agent_id,
            source_prompt_id=source.id,
            change_request=change_request,
            proposed_content=draft.proposed_content,
            proposed_description=draft.proposed_description,
            summary=draft.summary,
            questions=draft.questions,
            warnings=draft.warnings,
            status=PromptProposalStatus.PENDING,
            approved_prompt_id=None,
        )
        self.prompt_proposals[prompt_proposal.id] = prompt_proposal
        return prompt_proposal

    async def approve(self, prompt_proposal_id: UUID) -> PromptProposal | None:
        prompt_proposal = await self.get_by_id(prompt_proposal_id)
        if prompt_proposal is None:
            return None
        if prompt_proposal.status != PromptProposalStatus.PENDING:
            raise ConflictError("Prompt proposal is already finalized")
        prompt = await self.prompts.add_prompt(
            {
                "agent_id": prompt_proposal.agent_id,
                "content": prompt_proposal.proposed_content,
                "description": prompt_proposal.proposed_description,
            }
        )
        if prompt is None:
            return None
        prompt_proposal.approved_prompt_id = prompt.id
        prompt_proposal.status = PromptProposalStatus.APPROVED
        prompt_proposal.updated_at = datetime.now(UTC)
        return prompt_proposal

    async def discard(self, prompt_proposal_id: UUID) -> PromptProposal | None:
        prompt_proposal = await self.get_by_id(prompt_proposal_id)
        if prompt_proposal is None:
            return None
        if prompt_proposal.status != PromptProposalStatus.PENDING:
            raise ConflictError("Prompt proposal is already finalized")
        prompt_proposal.status = PromptProposalStatus.DISCARDED
        prompt_proposal.updated_at = datetime.now(UTC)
        return prompt_proposal
