from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from promptune.models.agent import Agent
from promptune.repositories.agent import AgentRepository

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_should_add_and_find_agent(agent_repository: AgentRepository) -> None:
    assert await agent_repository.get_all_agents(1, 10) == []

    agent = await agent_repository.add_agent(
        {"name": "Assistant", "description": "Helps users", "context": "Support"}
    )

    assert agent.id is not None
    assert agent.created_at is not None
    assert agent.name == "Assistant"
    assert await agent_repository.get_agent_by_id(agent.id) is agent


async def test_should_paginate_and_search_agents(
    agent_repository: AgentRepository,
) -> None:
    await agent_repository.add_agent({"name": "Writer"})
    prefix = await agent_repository.add_agent({"name": "Billing"})
    description = await agent_repository.add_agent(
        {"name": "Support", "description": "Billing questions"}
    )

    all_agents = await agent_repository.get_all_agents(1, 10)
    assert len(all_agents) == 3
    assert await agent_repository.get_all_agents(1, 1) == all_agents[:1]
    assert await agent_repository.get_all_agents(2, 1) == all_agents[1:2]
    assert await agent_repository.get_all_agents(1, 10, "billing") == [
        prefix,
        description,
    ]


async def test_should_treat_search_wildcards_as_literal_text(
    agent_repository: AgentRepository,
) -> None:
    literal = await agent_repository.add_agent({"name": "100% Helper"})
    await agent_repository.add_agent({"name": "Ordinary Helper"})

    assert await agent_repository.get_all_agents(1, 10, "%") == [literal]


async def test_should_update_only_supplied_fields_and_handle_missing_agent(
    agent_repository: AgentRepository,
) -> None:
    agent = await agent_repository.add_agent(
        {"name": "Original", "description": "Keep", "context": "Old"}
    )

    updated = await agent_repository.update_agent(
        agent.id, {"name": "Renamed", "context": None}
    )

    assert updated is not None
    assert updated.name == "Renamed"
    assert updated.description == "Keep"
    assert updated.context is None
    assert await agent_repository.update_agent(uuid4(), {"name": "Absent"}) is None


async def test_should_soft_delete_and_hide_agent(
    agent_repository: AgentRepository, session: AsyncSession
) -> None:
    agent = await agent_repository.add_agent({"name": "Temporary"})

    assert await agent_repository.delete_agent(agent.id) is True
    deleted_at = await session.scalar(
        select(Agent.deleted_at).where(Agent.id == agent.id)
    )
    assert deleted_at is not None
    assert await agent_repository.get_agent_by_id(agent.id) is None
    assert await agent_repository.get_all_agents(1, 10) == []
    assert await agent_repository.delete_agent(agent.id) is False
    assert await agent_repository.delete_agent(uuid4()) is False


async def test_should_keep_repository_commits_inside_test_transaction(
    agent_repository: AgentRepository, engine: AsyncEngine
) -> None:
    agent = await agent_repository.add_agent({"name": "Uncommitted outside test"})

    async with engine.connect() as other_connection:
        visible = await other_connection.scalar(
            select(Agent.id).where(Agent.id == agent.id)
        )

    assert visible is None
