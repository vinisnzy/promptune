from uuid import uuid4

import pytest

from promptune.core.exceptions import ConflictError, InvalidInputError, NotFoundError
from promptune.modules.prompt_proposal.model import PromptProposalStatus
from promptune.modules.prompt_proposal.service import PromptProposalService
from tests.unit.prompt_proposal.in_memory_repository import (
    InMemoryPromptProposalRepository,
)


async def test_should_list_and_get_only_owned_proposals(
    prompt_proposal_service: PromptProposalService,
    prompt_proposal_repository: InMemoryPromptProposalRepository,
) -> None:
    owner_id = uuid4()
    agent_id = uuid4()
    first = prompt_proposal_repository.add(user_id=owner_id, agent_id=agent_id)
    second = prompt_proposal_repository.add(user_id=owner_id, agent_id=agent_id)
    prompt_proposal_repository.add(user_id=uuid4(), agent_id=agent_id)

    assert await prompt_proposal_service.list_by_agent(agent_id, owner_id, 1, 1) == [
        second
    ]
    assert await prompt_proposal_service.list_by_agent(agent_id, owner_id, 2, 1) == [
        first
    ]
    assert await prompt_proposal_service.get_by_id(first.id, owner_id) is first
    with pytest.raises(NotFoundError):
        await prompt_proposal_service.get_by_id(first.id, uuid4())


async def test_should_approve_or_discard_owned_proposal(
    prompt_proposal_service: PromptProposalService,
    prompt_proposal_repository: InMemoryPromptProposalRepository,
) -> None:
    owner_id = uuid4()
    approved = prompt_proposal_repository.add(user_id=owner_id)
    discarded = prompt_proposal_repository.add(user_id=owner_id)

    assert (
        await prompt_proposal_service.approve(approved.id, owner_id)
    ).status == PromptProposalStatus.APPROVED
    assert (
        await prompt_proposal_service.discard(discarded.id, owner_id)
    ).status == PromptProposalStatus.DISCARDED
    with pytest.raises(ConflictError):
        await prompt_proposal_service.approve(approved.id, owner_id)
    with pytest.raises(NotFoundError):
        await prompt_proposal_service.discard(discarded.id, uuid4())


async def test_should_validate_pagination_and_missing_proposals(
    prompt_proposal_service: PromptProposalService,
) -> None:
    with pytest.raises(InvalidInputError):
        await prompt_proposal_service.list_by_agent(uuid4(), uuid4(), 0, 10)
    with pytest.raises(NotFoundError):
        await prompt_proposal_service.get_by_id(uuid4(), uuid4())
