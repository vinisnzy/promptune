from uuid import uuid4

import pytest

from promptune.core.exceptions import ConflictError, InvalidInputError, NotFoundError
from promptune.modules.agent.schema import AgentCreate
from promptune.modules.agent.service import AgentService
from promptune.modules.prompt.schema import PromptCreate
from promptune.modules.prompt.service import PromptService
from promptune.modules.prompt_proposal.model import PromptProposalStatus
from promptune.modules.prompt_proposal.schema import PromptProposalCreate
from promptune.modules.prompt_proposal.service import PromptProposalService
from tests.unit.prompt_proposal.in_memory_repository import (
    InMemoryPromptProposalRepository,
)


async def test_create_and_get_simulated_prompt_proposal(
    agent_service: AgentService,
    prompt_service: PromptService,
    prompt_proposal_service: PromptProposalService,
) -> None:
    agent = await agent_service.add_agent(
        AgentCreate(name="Assistant", context="Agenda")
    )
    prompt = await prompt_service.add_prompt(
        PromptCreate(agent_id=agent.id, content="# Original")
    )

    prompt_proposal = await prompt_proposal_service.create(
        PromptProposalCreate(
            source_prompt_id=prompt.id,
            change_request="  Simplificar saudação  ",
        )
    )

    assert prompt_proposal.agent_id == agent.id
    assert prompt_proposal.source_prompt_id == prompt.id
    assert prompt_proposal.change_request == "Simplificar saudação"
    assert prompt_proposal.proposed_content == prompt.content
    assert prompt_proposal.proposed_description == (
        f"Revisão simulada: {prompt.description}"
    )
    assert prompt_proposal.status == PromptProposalStatus.PENDING
    assert prompt_proposal.summary == [
        "Simulação: nenhuma alteração foi aplicada ao prompt."
    ]
    assert prompt_proposal.warnings == [
        "Resultado simulado, sem uso de IA. Revise antes de aprovar."
    ]
    assert (
        await prompt_proposal_service.get_by_id(prompt_proposal.id)
        is prompt_proposal
    )


async def test_list_prompt_proposals_by_agent_with_pagination(
    agent_service: AgentService,
    prompt_service: PromptService,
    prompt_proposal_service: PromptProposalService,
) -> None:
    agent = await agent_service.add_agent(AgentCreate(name="First"))
    other = await agent_service.add_agent(AgentCreate(name="Other"))
    source = await prompt_service.add_prompt(
        PromptCreate(agent_id=agent.id, content="Original")
    )
    other_source = await prompt_service.add_prompt(
        PromptCreate(agent_id=other.id, content="Other")
    )
    first = await prompt_proposal_service.create(
        PromptProposalCreate(source_prompt_id=source.id, change_request="Primeira")
    )
    second = await prompt_proposal_service.create(
        PromptProposalCreate(source_prompt_id=source.id, change_request="Segunda")
    )
    await prompt_proposal_service.create(
        PromptProposalCreate(source_prompt_id=other_source.id, change_request="Outra")
    )

    assert await prompt_proposal_service.list_by_agent(agent.id, 1, 1) == [second]
    assert await prompt_proposal_service.list_by_agent(agent.id, 2, 1) == [first]
    assert await prompt_proposal_service.list_by_agent(uuid4(), 1, 10) == []


async def test_approve_prompt_proposal_from_old_source_creates_latest_version(
    agent_service: AgentService,
    prompt_service: PromptService,
    prompt_proposal_service: PromptProposalService,
) -> None:
    agent = await agent_service.add_agent(AgentCreate(name="Assistant"))
    first = await prompt_service.add_prompt(
        PromptCreate(agent_id=agent.id, content="v1")
    )
    prompt_proposal = await prompt_proposal_service.create(
        PromptProposalCreate(source_prompt_id=first.id, change_request="Alterar v1")
    )
    await prompt_service.add_prompt(PromptCreate(agent_id=agent.id, content="v2"))

    approved = await prompt_proposal_service.approve(prompt_proposal.id)
    current = await prompt_service.get_current_prompt_by_agent(agent.id)

    assert approved.status == PromptProposalStatus.APPROVED
    assert current.version == 3
    assert current.content == first.content
    assert current.description == prompt_proposal.proposed_description
    assert approved.approved_prompt_id == current.id
    with pytest.raises(ConflictError):
        await prompt_proposal_service.approve(prompt_proposal.id)


async def test_discard_prompt_proposal_without_creating_prompt(
    agent_service: AgentService,
    prompt_service: PromptService,
    prompt_proposal_service: PromptProposalService,
) -> None:
    agent = await agent_service.add_agent(AgentCreate(name="Assistant"))
    source = await prompt_service.add_prompt(
        PromptCreate(agent_id=agent.id, content="Original")
    )
    prompt_proposal = await prompt_proposal_service.create(
        PromptProposalCreate(source_prompt_id=source.id, change_request="Alterar")
    )

    discarded = await prompt_proposal_service.discard(prompt_proposal.id)

    assert discarded.status == PromptProposalStatus.DISCARDED
    assert discarded.approved_prompt_id is None
    assert await prompt_service.get_current_prompt_by_agent(agent.id) is source
    with pytest.raises(ConflictError):
        await prompt_proposal_service.approve(prompt_proposal.id)


async def test_reject_missing_inputs_and_invalid_pagination(
    prompt_proposal_service: PromptProposalService,
    prompt_proposal_repository: InMemoryPromptProposalRepository,
) -> None:
    with pytest.raises(NotFoundError):
        await prompt_proposal_service.create(
            PromptProposalCreate(source_prompt_id=uuid4(), change_request="Alterar")
        )
    with pytest.raises(InvalidInputError):
        await prompt_proposal_service.create(
            PromptProposalCreate(source_prompt_id=uuid4(), change_request="   ")
        )
    with pytest.raises(InvalidInputError):
        await prompt_proposal_service.list_by_agent(uuid4(), 0, 10)
    with pytest.raises(NotFoundError):
        await prompt_proposal_service.get_by_id(uuid4())
    with pytest.raises(NotFoundError):
        await prompt_proposal_service.approve(uuid4())
    with pytest.raises(NotFoundError):
        await prompt_proposal_service.discard(uuid4())
    assert prompt_proposal_repository.prompt_proposals == {}


async def test_deleted_agent_hides_prompt_proposal(
    agent_service: AgentService,
    prompt_service: PromptService,
    prompt_proposal_service: PromptProposalService,
    prompt_proposal_repository: InMemoryPromptProposalRepository,
) -> None:
    agent = await agent_service.add_agent(AgentCreate(name="Temporary"))
    source = await prompt_service.add_prompt(
        PromptCreate(agent_id=agent.id, content="Original")
    )
    prompt_proposal = await prompt_proposal_service.create(
        PromptProposalCreate(source_prompt_id=source.id, change_request="Alterar")
    )

    await agent_service.delete_agent(agent.id)

    assert prompt_proposal.id in prompt_proposal_repository.prompt_proposals
    assert await prompt_proposal_service.list_by_agent(agent.id, 1, 10) == []
    with pytest.raises(NotFoundError):
        await prompt_proposal_service.get_by_id(prompt_proposal.id)
    with pytest.raises(NotFoundError):
        await prompt_proposal_service.approve(prompt_proposal.id)
