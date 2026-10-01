from uuid import uuid4

import pytest

from promptune.core.exceptions import ConflictError
from promptune.modules.agent.repository import AgentRepository
from promptune.modules.prompt.repository import PromptRepository
from promptune.modules.revision.model import RevisionStatus
from promptune.modules.revision.repository import RevisionRepository
from promptune.modules.revision.schema import RevisionDraft

pytestmark = pytest.mark.asyncio(loop_scope="session")


def draft(content: str) -> RevisionDraft:
    return RevisionDraft(
        proposed_content=content,
        proposed_description="Descrição sugerida",
        summary=["Resumo"],
        questions=[],
        warnings=["Simulação"],
    )


async def test_approve_old_source_creates_latest_version(session) -> None:
    agents = AgentRepository(session)
    prompts = PromptRepository(session)
    revisions = RevisionRepository(session)
    agent = await agents.add_agent({"name": "Assistant", "context": "Agenda"})
    first = await prompts.add_prompt({"agent_id": agent.id, "content": "v1"})
    assert first is not None
    revision = await revisions.create(first.id, "Alterar v1", draft("Proposta v1"))
    assert revision is not None
    await prompts.add_prompt({"agent_id": agent.id, "content": "v2"})

    approved = await revisions.approve(revision.id)
    current = await prompts.get_current_prompt_by_agent(agent.id)

    assert approved is not None
    assert approved.status == RevisionStatus.APPROVED
    assert current is not None
    assert (current.version, current.content) == (3, "Proposta v1")
    assert revision.proposed_description == "Descrição sugerida"
    assert current.description == revision.proposed_description
    assert approved.approved_prompt_id == current.id
    with pytest.raises(ConflictError):
        await revisions.approve(revision.id)


async def test_discard_does_not_create_version(session) -> None:
    agents = AgentRepository(session)
    prompts = PromptRepository(session)
    revisions = RevisionRepository(session)
    agent = await agents.add_agent({"name": "Assistant"})
    source = await prompts.add_prompt({"agent_id": agent.id, "content": "Original"})
    assert source is not None
    revision = await revisions.create(source.id, "Alterar", draft("Alterado"))
    assert revision is not None

    discarded = await revisions.discard(revision.id)
    assert discarded is not None
    assert discarded.status == RevisionStatus.DISCARDED
    current = await prompts.get_current_prompt_by_agent(agent.id)
    assert current is not None
    assert current.id == source.id
    with pytest.raises(ConflictError):
        await revisions.approve(revision.id)


async def test_missing_and_deleted_agent_hide_revisions(session) -> None:
    agents = AgentRepository(session)
    prompts = PromptRepository(session)
    revisions = RevisionRepository(session)
    assert await revisions.get_by_id(uuid4()) is None
    assert await revisions.list_by_agent(uuid4(), 1, 10) == []
    agent = await agents.add_agent({"name": "Temporary"})
    source = await prompts.add_prompt({"agent_id": agent.id, "content": "Original"})
    assert source is not None
    revision = await revisions.create(source.id, "Alterar", draft("Alterado"))
    assert revision is not None
    assert await revisions.list_by_agent(agent.id, 1, 10) == [revision]

    await agents.delete_agent(agent.id)
    assert await revisions.get_by_id(revision.id) is None
    assert await revisions.list_by_agent(agent.id, 1, 10) == []
    assert await revisions.approve(revision.id) is None
