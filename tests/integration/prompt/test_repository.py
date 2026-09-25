from uuid import uuid4

import pytest

from promptune.repositories.agent import AgentRepository
from promptune.repositories.prompt import PromptRepository

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_should_create_versioned_prompts_and_return_current_one(
    agent_repository: AgentRepository, prompt_repository: PromptRepository
) -> None:
    agent = await agent_repository.add_agent({"name": "Assistant"})
    first = await prompt_repository.add_prompt(
        {"agent_id": agent.id, "content": "First instructions"}
    )
    second = await prompt_repository.add_prompt(
        {"agent_id": agent.id, "content": "Revised", "description": "Release"}
    )

    assert first is not None
    assert second is not None
    assert (first.version, first.description) == (1, "v1")
    assert (second.version, second.description) == (2, "Release")
    assert await prompt_repository.get_prompt_by_id(first.id) is first
    assert await prompt_repository.get_current_prompt_by_agent(agent.id) is second


async def test_should_paginate_prompts_and_separate_agents(
    agent_repository: AgentRepository, prompt_repository: PromptRepository
) -> None:
    agent = await agent_repository.add_agent({"name": "First"})
    other = await agent_repository.add_agent({"name": "Other"})
    first = await prompt_repository.add_prompt({"agent_id": agent.id, "content": "One"})
    second = await prompt_repository.add_prompt(
        {"agent_id": agent.id, "content": "Two"}
    )
    other_prompt = await prompt_repository.add_prompt(
        {"agent_id": other.id, "content": "Other"}
    )

    assert first is not None
    assert second is not None
    assert other_prompt is not None
    all_prompts = await prompt_repository.get_prompts_by_agent(agent.id, 1, 10)
    assert {prompt.id for prompt in all_prompts} == {first.id, second.id}
    assert (
        await prompt_repository.get_prompts_by_agent(agent.id, 1, 1) == all_prompts[:1]
    )
    assert (
        await prompt_repository.get_prompts_by_agent(agent.id, 2, 1) == all_prompts[1:2]
    )
    assert await prompt_repository.get_prompts_by_agent(other.id, 1, 10) == [
        other_prompt
    ]


async def test_should_return_none_for_missing_prompt_or_agent(
    prompt_repository: PromptRepository,
) -> None:
    missing_id = uuid4()

    assert await prompt_repository.get_prompt_by_id(missing_id) is None
    assert await prompt_repository.get_current_prompt_by_agent(missing_id) is None
    assert await prompt_repository.get_prompts_by_agent(missing_id, 1, 10) == []
    assert (
        await prompt_repository.add_prompt(
            {"agent_id": missing_id, "content": "Orphan"}
        )
        is None
    )


async def test_should_hide_prompts_and_reject_creation_for_deleted_agent(
    agent_repository: AgentRepository, prompt_repository: PromptRepository
) -> None:
    agent = await agent_repository.add_agent({"name": "Temporary"})
    prompt = await prompt_repository.add_prompt(
        {"agent_id": agent.id, "content": "Saved"}
    )
    assert prompt is not None

    await agent_repository.delete_agent(agent.id)

    assert await prompt_repository.get_prompt_by_id(prompt.id) is None
    assert await prompt_repository.get_current_prompt_by_agent(agent.id) is None
    assert await prompt_repository.get_prompts_by_agent(agent.id, 1, 10) == []
    assert (
        await prompt_repository.add_prompt({"agent_id": agent.id, "content": "New"})
        is None
    )
