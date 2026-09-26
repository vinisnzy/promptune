from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from promptune.core.exceptions import ConflictError
from promptune.models.revision import Revision, RevisionStatus
from promptune.repositories.revision import IRevisionRepository
from promptune.schemas.revision import RevisionDraft
from tests.unit.agent.in_memory_repository import InMemoryAgentRepository
from tests.unit.prompt.in_memory_repository import InMemoryPromptRepository


class InMemoryRevisionRepository(IRevisionRepository):
    def __init__(
        self,
        agents: InMemoryAgentRepository,
        prompts: InMemoryPromptRepository,
    ) -> None:
        self.agents = agents
        self.prompts = prompts
        self.revisions: dict[UUID, Revision] = {}

    async def list_by_agent(
        self, agent_id: UUID, page: int, size: int
    ) -> Sequence[Revision]:
        if await self.agents.get_agent_by_id(agent_id) is None:
            return []
        revisions = [
            revision
            for revision in self.revisions.values()
            if revision.agent_id == agent_id
        ]
        revisions.sort(
            key=lambda revision: (revision.created_at, revision.id), reverse=True
        )
        return revisions[(page - 1) * size : page * size]

    async def get_by_id(self, revision_id: UUID) -> Revision | None:
        revision = self.revisions.get(revision_id)
        if (
            revision is None
            or await self.agents.get_agent_by_id(revision.agent_id) is None
        ):
            return None
        return revision

    async def create(
        self, source_prompt_id: UUID, change_request: str, draft: RevisionDraft
    ) -> Revision | None:
        source = await self.prompts.get_prompt_by_id(source_prompt_id)
        if source is None:
            return None
        now = datetime.now(UTC)
        revision = Revision(
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
            status=RevisionStatus.PENDING,
            approved_prompt_id=None,
        )
        self.revisions[revision.id] = revision
        return revision

    async def approve(self, revision_id: UUID) -> Revision | None:
        revision = await self.get_by_id(revision_id)
        if revision is None:
            return None
        if revision.status != RevisionStatus.PENDING:
            raise ConflictError("Revision is already finalized")
        prompt = await self.prompts.add_prompt(
            {
                "agent_id": revision.agent_id,
                "content": revision.proposed_content,
                "description": revision.proposed_description,
            }
        )
        if prompt is None:
            return None
        revision.approved_prompt_id = prompt.id
        revision.status = RevisionStatus.APPROVED
        revision.updated_at = datetime.now(UTC)
        return revision

    async def discard(self, revision_id: UUID) -> Revision | None:
        revision = await self.get_by_id(revision_id)
        if revision is None:
            return None
        if revision.status != RevisionStatus.PENDING:
            raise ConflictError("Revision is already finalized")
        revision.status = RevisionStatus.DISCARDED
        revision.updated_at = datetime.now(UTC)
        return revision
