from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from promptune.core.exceptions import ConflictError
from promptune.modules.agent.model import Agent
from promptune.modules.prompt.model import Prompt
from promptune.modules.prompt.repository import create_next_prompt
from promptune.modules.prompt_proposal.model import (
    PromptProposal,
    PromptProposalStatus,
)
from promptune.modules.prompt_proposal.schema import PromptProposalDraft


class IPromptProposalRepository(ABC):
    @abstractmethod
    async def list_by_agent(
        self, agent_id: UUID, page: int, size: int
    ) -> Sequence[PromptProposal]: ...

    @abstractmethod
    async def get_by_id(
        self, prompt_proposal_id: UUID
    ) -> PromptProposal | None: ...

    @abstractmethod
    async def create(
        self,
        source_prompt_id: UUID,
        change_request: str,
        draft: PromptProposalDraft,
    ) -> PromptProposal | None: ...

    @abstractmethod
    async def approve(self, prompt_proposal_id: UUID) -> PromptProposal | None: ...

    @abstractmethod
    async def discard(self, prompt_proposal_id: UUID) -> PromptProposal | None: ...


class PromptProposalRepository(IPromptProposalRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_agent(
        self, agent_id: UUID, page: int, size: int
    ) -> Sequence[PromptProposal]:
        stmt = (
            select(PromptProposal)
            .join(Agent, PromptProposal.agent_id == Agent.id)
            .where(PromptProposal.agent_id == agent_id, Agent.deleted_at.is_(None))
            .order_by(PromptProposal.created_at.desc(), PromptProposal.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def get_by_id(self, prompt_proposal_id: UUID) -> PromptProposal | None:
        stmt = (
            select(PromptProposal)
            .join(Agent, PromptProposal.agent_id == Agent.id)
            .where(
                PromptProposal.id == prompt_proposal_id,
                Agent.deleted_at.is_(None),
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create(
        self,
        source_prompt_id: UUID,
        change_request: str,
        draft: PromptProposalDraft,
    ) -> PromptProposal | None:
        stmt = (
            select(Prompt)
            .join(Agent)
            .where(Prompt.id == source_prompt_id, Agent.deleted_at.is_(None))
        )
        source = (await self.session.execute(stmt)).scalar_one_or_none()
        if source is None:
            return None

        prompt_proposal = PromptProposal(
            agent_id=source.agent_id,
            source_prompt_id=source.id,
            change_request=change_request,
            proposed_content=draft.proposed_content,
            proposed_description=draft.proposed_description,
            summary=draft.summary,
            questions=draft.questions,
            warnings=draft.warnings,
            status=PromptProposalStatus.PENDING,
        )
        self.session.add(prompt_proposal)
        await self.session.commit()
        await self.session.refresh(prompt_proposal)
        return prompt_proposal

    async def approve(self, prompt_proposal_id: UUID) -> PromptProposal | None:
        stmt = (
            select(PromptProposal)
            .where(PromptProposal.id == prompt_proposal_id)
            .with_for_update()
        )
        prompt_proposal = (await self.session.execute(stmt)).scalar_one_or_none()
        if prompt_proposal is None:
            return None

        agent_stmt = (
            select(Agent)
            .where(
                Agent.id == prompt_proposal.agent_id, Agent.deleted_at.is_(None)
            )
            .with_for_update()
        )
        agent = (await self.session.execute(agent_stmt)).scalar_one_or_none()
        if agent is None:
            return None
        if prompt_proposal.status != PromptProposalStatus.PENDING:
            raise ConflictError("Prompt proposal is already finalized")

        prompt = await create_next_prompt(
            self.session,
            agent.id,
            prompt_proposal.proposed_content,
            prompt_proposal.proposed_description,
        )
        prompt_proposal.approved_prompt_id = prompt.id
        prompt_proposal.status = PromptProposalStatus.APPROVED
        await self.session.commit()
        await self.session.refresh(prompt_proposal)
        return prompt_proposal

    async def discard(self, prompt_proposal_id: UUID) -> PromptProposal | None:
        stmt = (
            select(PromptProposal)
            .where(PromptProposal.id == prompt_proposal_id)
            .with_for_update()
        )
        prompt_proposal = (await self.session.execute(stmt)).scalar_one_or_none()
        if prompt_proposal is None:
            return None

        agent_stmt = select(Agent.id).where(
            Agent.id == prompt_proposal.agent_id, Agent.deleted_at.is_(None)
        )
        if (await self.session.execute(agent_stmt)).scalar_one_or_none() is None:
            return None
        if prompt_proposal.status != PromptProposalStatus.PENDING:
            raise ConflictError("Prompt proposal is already finalized")

        prompt_proposal.status = PromptProposalStatus.DISCARDED
        await self.session.commit()
        await self.session.refresh(prompt_proposal)
        return prompt_proposal
