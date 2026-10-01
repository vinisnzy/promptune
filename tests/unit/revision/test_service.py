from uuid import uuid4

import pytest

from promptune.core.exceptions import ConflictError, InvalidInputError, NotFoundError
from promptune.modules.agent.schema import AgentCreate
from promptune.modules.agent.service import AgentService
from promptune.modules.prompt.schema import PromptCreate
from promptune.modules.prompt.service import PromptService
from promptune.modules.revision.model import RevisionStatus
from promptune.modules.revision.schema import RevisionCreate
from promptune.modules.revision.service import RevisionService
from tests.unit.revision.in_memory_repository import InMemoryRevisionRepository


async def test_create_and_get_simulated_revision(
    agent_service: AgentService,
    prompt_service: PromptService,
    revision_service: RevisionService,
) -> None:
    agent = await agent_service.add_agent(
        AgentCreate(name="Assistant", context="Agenda")
    )
    prompt = await prompt_service.add_prompt(
        PromptCreate(agent_id=agent.id, content="# Original")
    )

    revision = await revision_service.create(
        RevisionCreate(
            source_prompt_id=prompt.id,
            change_request="  Simplificar saudação  ",
        )
    )

    assert revision.agent_id == agent.id
    assert revision.source_prompt_id == prompt.id
    assert revision.change_request == "Simplificar saudação"
    assert revision.proposed_content == prompt.content
    assert revision.proposed_description == f"Revisão simulada: {prompt.description}"
    assert revision.status == RevisionStatus.PENDING
    assert revision.summary == ["Simulação: nenhuma alteração foi aplicada ao prompt."]
    assert revision.warnings == [
        "Resultado simulado, sem uso de IA. Revise antes de aprovar."
    ]
    assert await revision_service.get_by_id(revision.id) is revision


async def test_list_revisions_by_agent_with_pagination(
    agent_service: AgentService,
    prompt_service: PromptService,
    revision_service: RevisionService,
) -> None:
    agent = await agent_service.add_agent(AgentCreate(name="First"))
    other = await agent_service.add_agent(AgentCreate(name="Other"))
    source = await prompt_service.add_prompt(
        PromptCreate(agent_id=agent.id, content="Original")
    )
    other_source = await prompt_service.add_prompt(
        PromptCreate(agent_id=other.id, content="Other")
    )
    first = await revision_service.create(
        RevisionCreate(source_prompt_id=source.id, change_request="Primeira")
    )
    second = await revision_service.create(
        RevisionCreate(source_prompt_id=source.id, change_request="Segunda")
    )
    await revision_service.create(
        RevisionCreate(source_prompt_id=other_source.id, change_request="Outra")
    )

    assert await revision_service.list_by_agent(agent.id, 1, 1) == [second]
    assert await revision_service.list_by_agent(agent.id, 2, 1) == [first]
    assert await revision_service.list_by_agent(uuid4(), 1, 10) == []


async def test_approve_revision_from_old_source_creates_latest_version(
    agent_service: AgentService,
    prompt_service: PromptService,
    revision_service: RevisionService,
) -> None:
    agent = await agent_service.add_agent(AgentCreate(name="Assistant"))
    first = await prompt_service.add_prompt(
        PromptCreate(agent_id=agent.id, content="v1")
    )
    revision = await revision_service.create(
        RevisionCreate(source_prompt_id=first.id, change_request="Alterar v1")
    )
    await prompt_service.add_prompt(PromptCreate(agent_id=agent.id, content="v2"))

    approved = await revision_service.approve(revision.id)
    current = await prompt_service.get_current_prompt_by_agent(agent.id)

    assert approved.status == RevisionStatus.APPROVED
    assert current.version == 3
    assert current.content == first.content
    assert current.description == revision.proposed_description
    assert approved.approved_prompt_id == current.id
    with pytest.raises(ConflictError):
        await revision_service.approve(revision.id)


async def test_discard_revision_without_creating_prompt(
    agent_service: AgentService,
    prompt_service: PromptService,
    revision_service: RevisionService,
) -> None:
    agent = await agent_service.add_agent(AgentCreate(name="Assistant"))
    source = await prompt_service.add_prompt(
        PromptCreate(agent_id=agent.id, content="Original")
    )
    revision = await revision_service.create(
        RevisionCreate(source_prompt_id=source.id, change_request="Alterar")
    )

    discarded = await revision_service.discard(revision.id)

    assert discarded.status == RevisionStatus.DISCARDED
    assert discarded.approved_prompt_id is None
    assert await prompt_service.get_current_prompt_by_agent(agent.id) is source
    with pytest.raises(ConflictError):
        await revision_service.approve(revision.id)


async def test_reject_missing_inputs_and_invalid_pagination(
    revision_service: RevisionService,
    revision_repository: InMemoryRevisionRepository,
) -> None:
    with pytest.raises(NotFoundError):
        await revision_service.create(
            RevisionCreate(source_prompt_id=uuid4(), change_request="Alterar")
        )
    with pytest.raises(InvalidInputError):
        await revision_service.create(
            RevisionCreate(source_prompt_id=uuid4(), change_request="   ")
        )
    with pytest.raises(InvalidInputError):
        await revision_service.list_by_agent(uuid4(), 0, 10)
    with pytest.raises(NotFoundError):
        await revision_service.get_by_id(uuid4())
    with pytest.raises(NotFoundError):
        await revision_service.approve(uuid4())
    with pytest.raises(NotFoundError):
        await revision_service.discard(uuid4())
    assert revision_repository.revisions == {}


async def test_deleted_agent_hides_revision(
    agent_service: AgentService,
    prompt_service: PromptService,
    revision_service: RevisionService,
    revision_repository: InMemoryRevisionRepository,
) -> None:
    agent = await agent_service.add_agent(AgentCreate(name="Temporary"))
    source = await prompt_service.add_prompt(
        PromptCreate(agent_id=agent.id, content="Original")
    )
    revision = await revision_service.create(
        RevisionCreate(source_prompt_id=source.id, change_request="Alterar")
    )

    await agent_service.delete_agent(agent.id)

    assert revision.id in revision_repository.revisions
    assert await revision_service.list_by_agent(agent.id, 1, 10) == []
    with pytest.raises(NotFoundError):
        await revision_service.get_by_id(revision.id)
    with pytest.raises(NotFoundError):
        await revision_service.approve(revision.id)
