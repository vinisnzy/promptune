from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from promptune.agents.prompt_editor.schema import PromptProposalOutput
from promptune.core.exceptions import ConflictError, InvalidInputError
from promptune.modules.agent.model import Agent
from promptune.modules.message.model import Message, MessageRole
from promptune.modules.prompt.repository import create_next_prompt
from promptune.modules.prompt_proposal.model import PromptProposal, PromptProposalStatus
from promptune.modules.session.model import Session


class IPromptProposalRepository(ABC):
    @abstractmethod
    async def list_by_agent(
        self, agent_id: UUID, user_id: UUID, page: int, size: int
    ) -> Sequence[PromptProposal]: ...

    @abstractmethod
    async def get_by_id(
        self, prompt_proposal_id: UUID, user_id: UUID
    ) -> PromptProposal | None: ...

    @abstractmethod
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
    ) -> PromptProposal: ...

    @abstractmethod
    async def approve(
        self, prompt_proposal_id: UUID, user_id: UUID
    ) -> PromptProposal | None: ...

    @abstractmethod
    async def discard(
        self, prompt_proposal_id: UUID, user_id: UUID
    ) -> PromptProposal | None: ...


class PromptProposalRepository(IPromptProposalRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _owned(self, user_id: UUID):
        return (
            select(PromptProposal)
            .join(Message, PromptProposal.message_id == Message.id)
            .join(Session, Message.session_id == Session.id)
            .join(Agent, Session.agent_id == Agent.id)
            .where(
                Session.user_id == user_id,
                Session.deleted_at.is_(None),
                Agent.deleted_at.is_(None),
            )
        )

    async def list_by_agent(
        self, agent_id: UUID, user_id: UUID, page: int, size: int
    ) -> Sequence[PromptProposal]:
        stmt = (
            self._owned(user_id)
            .where(PromptProposal.agent_id == agent_id)
            .order_by(PromptProposal.created_at.desc(), PromptProposal.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def get_by_id(
        self, prompt_proposal_id: UUID, user_id: UUID
    ) -> PromptProposal | None:
        stmt = self._owned(user_id).where(PromptProposal.id == prompt_proposal_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

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
        message_stmt = (
            select(Message.id)
            .join(Session, Message.session_id == Session.id)
            .where(
                Message.id == message_id,
                Message.role == MessageRole.ASSISTANT,
                Session.agent_id == agent_id,
                Session.base_prompt_id == source_prompt_id,
            )
        )
        if (await self.session.execute(message_stmt)).scalar_one_or_none() is None:
            raise InvalidInputError(
                "Proposal message and source prompt must belong to the same session"
            )
        proposal = PromptProposal(
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
        )
        self.session.add(proposal)
        await self.session.flush()
        return proposal

    async def approve(
        self, prompt_proposal_id: UUID, user_id: UUID
    ) -> PromptProposal | None:
        stmt = (
            self._owned(user_id)
            .where(PromptProposal.id == prompt_proposal_id)
            .with_for_update(of=PromptProposal)
        )
        proposal = (await self.session.execute(stmt)).scalar_one_or_none()
        if proposal is None:
            return None
        if proposal.status != PromptProposalStatus.PENDING:
            raise ConflictError("Prompt proposal is already finalized")
        agent_stmt = (
            select(Agent)
            .where(Agent.id == proposal.agent_id, Agent.deleted_at.is_(None))
            .with_for_update()
        )
        agent = (await self.session.execute(agent_stmt)).scalar_one_or_none()
        if agent is None:
            return None
        prompt = await create_next_prompt(
            self.session,
            agent.id,
            proposal.proposed_content,
            proposal.proposed_description,
        )
        proposal.approved_prompt_id = prompt.id
        proposal.status = PromptProposalStatus.APPROVED
        await self.session.flush()
        return proposal

    async def discard(
        self, prompt_proposal_id: UUID, user_id: UUID
    ) -> PromptProposal | None:
        stmt = (
            self._owned(user_id)
            .where(PromptProposal.id == prompt_proposal_id)
            .with_for_update(of=PromptProposal)
        )
        proposal = (await self.session.execute(stmt)).scalar_one_or_none()
        if proposal is None:
            return None
        if proposal.status != PromptProposalStatus.PENDING:
            raise ConflictError("Prompt proposal is already finalized")
        proposal.status = PromptProposalStatus.DISCARDED
        await self.session.flush()
        return proposal
