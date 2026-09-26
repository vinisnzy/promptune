from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from promptune.core.exceptions import ConflictError
from promptune.models.agent import Agent
from promptune.models.prompt import Prompt
from promptune.models.revision import Revision, RevisionStatus
from promptune.repositories.prompt import create_next_prompt
from promptune.schemas.revision import RevisionDraft


class IRevisionRepository(ABC):
    @abstractmethod
    async def list_by_agent(
        self, agent_id: UUID, page: int, size: int
    ) -> Sequence[Revision]: ...

    @abstractmethod
    async def get_by_id(self, revision_id: UUID) -> Revision | None: ...

    @abstractmethod
    async def create(
        self, source_prompt_id: UUID, change_request: str, draft: RevisionDraft
    ) -> Revision | None: ...

    @abstractmethod
    async def approve(self, revision_id: UUID) -> Revision | None: ...

    @abstractmethod
    async def discard(self, revision_id: UUID) -> Revision | None: ...


class RevisionRepository(IRevisionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_agent(
        self, agent_id: UUID, page: int, size: int
    ) -> Sequence[Revision]:
        stmt = (
            select(Revision)
            .join(Agent, Revision.agent_id == Agent.id)
            .where(Revision.agent_id == agent_id, Agent.deleted_at.is_(None))
            .order_by(Revision.created_at.desc(), Revision.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def get_by_id(self, revision_id: UUID) -> Revision | None:
        stmt = (
            select(Revision)
            .join(Agent, Revision.agent_id == Agent.id)
            .where(Revision.id == revision_id, Agent.deleted_at.is_(None))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create(
        self, source_prompt_id: UUID, change_request: str, draft: RevisionDraft
    ) -> Revision | None:
        stmt = (
            select(Prompt)
            .join(Agent)
            .where(Prompt.id == source_prompt_id, Agent.deleted_at.is_(None))
        )
        source = (await self.session.execute(stmt)).scalar_one_or_none()
        if source is None:
            return None

        revision = Revision(
            agent_id=source.agent_id,
            source_prompt_id=source.id,
            change_request=change_request,
            proposed_content=draft.proposed_content,
            proposed_description=draft.proposed_description,
            summary=draft.summary,
            questions=draft.questions,
            warnings=draft.warnings,
            status=RevisionStatus.PENDING,
        )
        self.session.add(revision)
        await self.session.commit()
        await self.session.refresh(revision)
        return revision

    async def approve(self, revision_id: UUID) -> Revision | None:
        stmt = select(Revision).where(Revision.id == revision_id).with_for_update()
        revision = (await self.session.execute(stmt)).scalar_one_or_none()
        if revision is None:
            return None

        agent_stmt = (
            select(Agent)
            .where(Agent.id == revision.agent_id, Agent.deleted_at.is_(None))
            .with_for_update()
        )
        agent = (await self.session.execute(agent_stmt)).scalar_one_or_none()
        if agent is None:
            return None
        if revision.status != RevisionStatus.PENDING:
            raise ConflictError("Revision is already finalized")

        prompt = await create_next_prompt(
            self.session,
            agent.id,
            revision.proposed_content,
            revision.proposed_description,
        )
        revision.approved_prompt_id = prompt.id
        revision.status = RevisionStatus.APPROVED
        await self.session.commit()
        await self.session.refresh(revision)
        return revision

    async def discard(self, revision_id: UUID) -> Revision | None:
        stmt = select(Revision).where(Revision.id == revision_id).with_for_update()
        revision = (await self.session.execute(stmt)).scalar_one_or_none()
        if revision is None:
            return None

        agent_stmt = select(Agent.id).where(
            Agent.id == revision.agent_id, Agent.deleted_at.is_(None)
        )
        if (await self.session.execute(agent_stmt)).scalar_one_or_none() is None:
            return None
        if revision.status != RevisionStatus.PENDING:
            raise ConflictError("Revision is already finalized")

        revision.status = RevisionStatus.DISCARDED
        await self.session.commit()
        await self.session.refresh(revision)
        return revision
