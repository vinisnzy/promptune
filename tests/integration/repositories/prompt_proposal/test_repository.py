from uuid import uuid4

import pytest

from promptune.core.exceptions import ConflictError
from promptune.modules.agent.repository import AgentRepository
from promptune.modules.prompt.repository import PromptRepository
from promptune.modules.prompt_proposal.model import PromptProposalStatus
from promptune.modules.prompt_proposal.repository import PromptProposalRepository
from promptune.modules.prompt_proposal.schema import PromptProposalDraft

pytestmark = pytest.mark.asyncio(loop_scope="session")


def draft(content: str) -> PromptProposalDraft:
    return PromptProposalDraft(
        proposed_content=content,
        proposed_description="Descrição sugerida",
        summary=["Resumo"],
        questions=[],
        warnings=["Simulação"],
    )


async def test_approve_old_source_creates_latest_version(session) -> None:
    agents = AgentRepository(session)
    prompts = PromptRepository(session)
    prompt_proposals = PromptProposalRepository(session)
    agent = await agents.add_agent({"name": "Assistant", "context": "Agenda"})
    first = await prompts.add_prompt({"agent_id": agent.id, "content": "v1"})
    assert first is not None
    prompt_proposal = await prompt_proposals.create(
        first.id, "Alterar v1", draft("Proposta v1")
    )
    assert prompt_proposal is not None
    await prompts.add_prompt({"agent_id": agent.id, "content": "v2"})

    approved = await prompt_proposals.approve(prompt_proposal.id)
    current = await prompts.get_current_prompt_by_agent(agent.id)

    assert approved is not None
    assert approved.status == PromptProposalStatus.APPROVED
    assert current is not None
    assert (current.version, current.content) == (3, "Proposta v1")
    assert prompt_proposal.proposed_description == "Descrição sugerida"
    assert current.description == prompt_proposal.proposed_description
    assert approved.approved_prompt_id == current.id
    with pytest.raises(ConflictError):
        await prompt_proposals.approve(prompt_proposal.id)


async def test_discard_does_not_create_version(session) -> None:
    agents = AgentRepository(session)
    prompts = PromptRepository(session)
    prompt_proposals = PromptProposalRepository(session)
    agent = await agents.add_agent({"name": "Assistant"})
    source = await prompts.add_prompt({"agent_id": agent.id, "content": "Original"})
    assert source is not None
    prompt_proposal = await prompt_proposals.create(
        source.id, "Alterar", draft("Alterado")
    )
    assert prompt_proposal is not None

    discarded = await prompt_proposals.discard(prompt_proposal.id)
    assert discarded is not None
    assert discarded.status == PromptProposalStatus.DISCARDED
    current = await prompts.get_current_prompt_by_agent(agent.id)
    assert current is not None
    assert current.id == source.id
    with pytest.raises(ConflictError):
        await prompt_proposals.approve(prompt_proposal.id)


async def test_missing_and_deleted_agent_hide_prompt_proposals(session) -> None:
    agents = AgentRepository(session)
    prompts = PromptRepository(session)
    prompt_proposals = PromptProposalRepository(session)
    assert await prompt_proposals.get_by_id(uuid4()) is None
    assert await prompt_proposals.list_by_agent(uuid4(), 1, 10) == []
    agent = await agents.add_agent({"name": "Temporary"})
    source = await prompts.add_prompt({"agent_id": agent.id, "content": "Original"})
    assert source is not None
    prompt_proposal = await prompt_proposals.create(
        source.id, "Alterar", draft("Alterado")
    )
    assert prompt_proposal is not None
    assert await prompt_proposals.list_by_agent(agent.id, 1, 10) == [
        prompt_proposal
    ]

    await agents.delete_agent(agent.id)
    assert await prompt_proposals.get_by_id(prompt_proposal.id) is None
    assert await prompt_proposals.list_by_agent(agent.id, 1, 10) == []
    assert await prompt_proposals.approve(prompt_proposal.id) is None
