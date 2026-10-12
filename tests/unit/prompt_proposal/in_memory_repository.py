from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from promptune.agents.prompt_editor.schema import PromptProposalOutput
from promptune.core.exceptions import ConflictError, InvalidInputError
from promptune.modules.prompt_proposal.model import PromptProposal, PromptProposalStatus
from promptune.modules.prompt_proposal.repository import IPromptProposalRepository


class InMemoryPromptProposalRepository(IPromptProposalRepository):
    def __init__(self) -> None:
        self.proposals: dict[UUID, PromptProposal] = {}
        self.owners: dict[UUID, UUID] = {}
        self.message_owners: dict[UUID, UUID] = {}

    async def list_by_agent(
        self, agent_id: UUID, user_id: UUID, page: int, size: int
    ) -> Sequence[PromptProposal]:
        items = [
            proposal
            for proposal in self.proposals.values()
            if proposal.agent_id == agent_id and self.owners[proposal.id] == user_id
        ]
        items.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        return items[(page - 1) * size : page * size]

    async def get_by_id(
        self, prompt_proposal_id: UUID, user_id: UUID
    ) -> PromptProposal | None:
        proposal = self.proposals.get(prompt_proposal_id)
        if proposal is None or self.owners[prompt_proposal_id] != user_id:
            return None
        return proposal

    async def create_for_message(
        self,
        *,
        message_id: UUID,
        agent_id: UUID,
        source_prompt_id: UUID,
        change_request: str,
        output: PromptProposalOutput,
        questions: list[str],
        warnings: list[str],
    ) -> PromptProposal:
        user_id = self.message_owners.get(message_id)
        if user_id is None:
            raise InvalidInputError("Proposal message does not exist")
        now = datetime.now(UTC)
        proposal = PromptProposal(
            id=uuid4(),
            message_id=message_id,
            agent_id=agent_id,
            source_prompt_id=source_prompt_id,
            change_request=change_request,
            proposed_content=output.proposed_content,
            proposed_description=output.proposed_description,
            summary=output.summary,
            questions=list(questions),
            warnings=list(warnings),
            status=PromptProposalStatus.PENDING,
            approved_prompt_id=None,
            created_at=now,
            updated_at=now,
        )
        self.proposals[proposal.id] = proposal
        self.owners[proposal.id] = user_id
        return proposal

    async def approve(
        self, prompt_proposal_id: UUID, user_id: UUID
    ) -> PromptProposal | None:
        proposal = await self.get_by_id(prompt_proposal_id, user_id)
        if proposal is None:
            return None
        if proposal.status != PromptProposalStatus.PENDING:
            raise ConflictError("Prompt proposal is already finalized")
        proposal.status = PromptProposalStatus.APPROVED
        proposal.approved_prompt_id = uuid4()
        return proposal

    async def discard(
        self, prompt_proposal_id: UUID, user_id: UUID
    ) -> PromptProposal | None:
        proposal = await self.get_by_id(prompt_proposal_id, user_id)
        if proposal is None:
            return None
        if proposal.status != PromptProposalStatus.PENDING:
            raise ConflictError("Prompt proposal is already finalized")
        proposal.status = PromptProposalStatus.DISCARDED
        return proposal

    def add(self, *, user_id: UUID, agent_id: UUID | None = None) -> PromptProposal:
        now = datetime.now(UTC)
        proposal = PromptProposal(
            id=uuid4(),
            message_id=uuid4(),
            agent_id=agent_id or uuid4(),
            source_prompt_id=uuid4(),
            change_request="Improve greeting",
            proposed_content="# Improved",
            proposed_description="Improved greeting",
            summary=["Updated greeting"],
            questions=[],
            warnings=[],
            status=PromptProposalStatus.PENDING,
            approved_prompt_id=None,
            created_at=now,
            updated_at=now,
        )
        self.proposals[proposal.id] = proposal
        self.owners[proposal.id] = user_id
        return proposal

    def add_message(self, *, message_id: UUID, user_id: UUID) -> None:
        self.message_owners[message_id] = user_id
