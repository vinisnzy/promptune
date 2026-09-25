from uuid import uuid4

import pytest

from promptune.core.exceptions import InvalidInputError, NotFoundError
from promptune.schemas.agent import AgentCreate
from promptune.schemas.prompt import PromptCreate
from promptune.services.agent import AgentService
from promptune.services.prompt import PromptService
from tests.unit.prompt.in_memory_repository import InMemoryPromptRepository


async def test_should_version_new_prompts_and_return_current_prompt(
    agent_service: AgentService, prompt_service: PromptService
) -> None:
    agent = await agent_service.add_agent(AgentCreate(name="Assistant"))

    first = await prompt_service.add_prompt(
        PromptCreate(agent_id=agent.id, content="First instructions")
    )
    second = await prompt_service.add_prompt(
        PromptCreate(agent_id=agent.id, content="Revised", description="Release")
    )

    assert (first.version, first.description) == (1, "v1")
    assert (second.version, second.description) == (2, "Release")
    assert await prompt_service.get_prompt_by_id(first.id) is first
    assert await prompt_service.get_current_prompt_by_agent(agent.id) is second


async def test_should_paginate_prompts_and_separate_agents(
    agent_service: AgentService, prompt_service: PromptService
) -> None:
    agent = await agent_service.add_agent(AgentCreate(name="First"))
    other = await agent_service.add_agent(AgentCreate(name="Other"))
    first = await prompt_service.add_prompt(
        PromptCreate(agent_id=agent.id, content="One")
    )
    second = await prompt_service.add_prompt(
        PromptCreate(agent_id=agent.id, content="Two")
    )
    await prompt_service.add_prompt(PromptCreate(agent_id=other.id, content="Other"))

    assert [
        p.id for p in await prompt_service.get_prompts_by_agent(agent.id, 1, 1)
    ] == [second.id]
    assert [
        p.id for p in await prompt_service.get_prompts_by_agent(agent.id, 2, 1)
    ] == [first.id]
    assert await prompt_service.get_prompts_by_agent(uuid4(), 1, 10) == []


@pytest.mark.parametrize("page,size", [(0, 1), (1, 0), (-1, 2)])
async def test_should_reject_invalid_prompt_pagination(
    prompt_service: PromptService, page: int, size: int
) -> None:
    with pytest.raises(InvalidInputError):
        await prompt_service.get_prompts_by_agent(uuid4(), page, size)


async def test_should_raise_not_found_for_missing_prompt_and_agent(
    prompt_service: PromptService,
) -> None:
    missing_id = uuid4()

    with pytest.raises(NotFoundError):
        await prompt_service.get_prompt_by_id(missing_id)
    with pytest.raises(NotFoundError):
        await prompt_service.get_current_prompt_by_agent(missing_id)
    with pytest.raises(NotFoundError):
        await prompt_service.add_prompt(
            PromptCreate(agent_id=missing_id, content="Orphan")
        )


async def test_should_hide_prompts_and_reject_creation_for_deleted_agent(
    agent_service: AgentService,
    prompt_service: PromptService,
    prompt_repository: InMemoryPromptRepository,
) -> None:
    agent = await agent_service.add_agent(AgentCreate(name="Temporary"))
    prompt = await prompt_service.add_prompt(
        PromptCreate(agent_id=agent.id, content="Saved")
    )

    await agent_service.delete_agent(agent.id)

    assert prompt.id in prompt_repository.prompts
    assert await prompt_service.get_prompts_by_agent(agent.id, 1, 10) == []
    with pytest.raises(NotFoundError):
        await prompt_service.get_prompt_by_id(prompt.id)
    with pytest.raises(NotFoundError):
        await prompt_service.get_current_prompt_by_agent(agent.id)
    with pytest.raises(NotFoundError):
        await prompt_service.add_prompt(PromptCreate(agent_id=agent.id, content="New"))
