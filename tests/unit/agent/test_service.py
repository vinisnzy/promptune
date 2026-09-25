from uuid import uuid4

import pytest

from promptune.core.exceptions import InvalidInputError, NotFoundError
from promptune.schemas.agent import AgentCreate, AgentUpdate
from promptune.services.agent import AgentService
from tests.unit.agent.in_memory_repository import InMemoryAgentRepository


async def test_should_add_and_get_agent(agent_service: AgentService) -> None:
    agent = await agent_service.add_agent(
        AgentCreate(name="Assistant", description="Helps users", context="Support")
    )

    assert agent.id is not None
    assert agent.name == "Assistant"
    assert agent.description == "Helps users"
    assert await agent_service.get_agent_by_id(agent.id) is agent


async def test_should_filter_and_paginate_agents(agent_service: AgentService) -> None:
    await agent_service.add_agent(AgentCreate(name="Writer"))
    first = await agent_service.add_agent(
        AgentCreate(name="Support", description="Answers billing questions")
    )
    second = await agent_service.add_agent(AgentCreate(name="Billing"))

    assert [agent.id for agent in await agent_service.get_all_agents(1, 1)] == [
        second.id
    ]
    assert [agent.id for agent in await agent_service.get_all_agents(2, 1)] == [
        first.id
    ]
    assert [
        agent.id for agent in await agent_service.get_all_agents(1, 10, " billing ")
    ] == [
        second.id,
        first.id,
    ]
    assert len(await agent_service.get_all_agents(1, 10, "   ")) == 3


@pytest.mark.parametrize("page,size", [(0, 1), (1, 0), (-1, 2)])
async def test_should_reject_invalid_agent_pagination(
    agent_service: AgentService, page: int, size: int
) -> None:
    with pytest.raises(InvalidInputError):
        await agent_service.get_all_agents(page, size)


async def test_should_update_only_supplied_agent_fields(
    agent_service: AgentService,
) -> None:
    agent = await agent_service.add_agent(
        AgentCreate(name="Original", description="Keep me", context="Old")
    )

    updated = await agent_service.update_agent(
        agent.id, AgentUpdate(name="Renamed", context=None)
    )

    assert updated is agent
    assert updated.name == "Renamed"
    assert updated.description == "Keep me"
    assert updated.context is None


async def test_should_soft_delete_agent_and_hide_it(
    agent_service: AgentService, agent_repository: InMemoryAgentRepository
) -> None:
    agent = await agent_service.add_agent(AgentCreate(name="Temporary"))

    await agent_service.delete_agent(agent.id)

    assert agent_repository.agents[agent.id].deleted_at is not None
    assert await agent_service.get_all_agents(1, 10) == []
    with pytest.raises(NotFoundError):
        await agent_service.get_agent_by_id(agent.id)
    with pytest.raises(NotFoundError):
        await agent_service.update_agent(agent.id, AgentUpdate(name="Again"))
    with pytest.raises(NotFoundError):
        await agent_service.delete_agent(agent.id)


async def test_should_raise_not_found_for_missing_agent_operations(
    agent_service: AgentService,
) -> None:
    missing_id = uuid4()

    with pytest.raises(NotFoundError):
        await agent_service.get_agent_by_id(missing_id)
    with pytest.raises(NotFoundError):
        await agent_service.update_agent(missing_id, AgentUpdate(name="Absent"))
    with pytest.raises(NotFoundError):
        await agent_service.delete_agent(missing_id)
