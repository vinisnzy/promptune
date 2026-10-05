from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from promptune.core.exceptions import InvalidInputError
from promptune.modules.session.model import Session, SessionStatus
from promptune.modules.session.repository import SessionRepository
from tests.integration.repositories._conversation import setup_conversation

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_sessions_validate_references_filter_and_complete(session: AsyncSession):
    owner, other, agent, prompt, wrong_prompt = await setup_conversation(session)
    sessions = SessionRepository(session)
    with pytest.raises(InvalidInputError):
        await sessions.create(
            user_id=owner.id, agent_id=agent.id, base_prompt_id=wrong_prompt.id
        )
    first = await sessions.create(
        user_id=owner.id, agent_id=agent.id, base_prompt_id=prompt.id
    )
    second = await sessions.create(
        user_id=owner.id, agent_id=agent.id, base_prompt_id=prompt.id
    )
    outsider = await sessions.create(
        user_id=other.id, agent_id=agent.id, base_prompt_id=prompt.id
    )
    first.created_at = datetime.now(UTC) - timedelta(days=1)
    await session.flush()

    loaded = await sessions.get_by_id(first.id, owner.id)
    assert loaded is not None
    assert (loaded.agent.context, loaded.base_prompt.content) == (
        "Scheduling rules",
        "Base",
    )
    assert await sessions.get_by_id(first.id, other.id) is None
    assert [item.id for item in await sessions.list_by_user(owner.id, 1, 1)] == [
        second.id
    ]
    assert [item.id for item in await sessions.list_by_user(owner.id, 2, 1)] == [
        first.id
    ]
    assert await sessions.list_by_user(owner.id, 1, 10, agent_id=uuid4()) == []
    assert await sessions.list_by_user(owner.id, 1, 10, status="completed") == []
    assert outsider.id not in {
        item.id for item in await sessions.list_by_user(owner.id, 1, 10)
    }
    assert await sessions.complete(first.id, other.id) is None
    assert await sessions.complete(first.id, owner.id) is first
    assert await sessions.complete(first.id, owner.id) is first
    assert first.status == SessionStatus.COMPLETED
    assert await sessions.list_by_user(owner.id, 1, 10, status="completed") == [
        first
    ]
    with pytest.raises(InvalidInputError):
        await sessions.list_by_user(owner.id, 0, 10)


async def test_session_rollback_and_deleted_agent(session: AsyncSession):
    owner, _, agent, prompt, _ = await setup_conversation(session)
    sessions = SessionRepository(session)
    conversation = await sessions.create(
        user_id=owner.id, agent_id=agent.id, base_prompt_id=prompt.id
    )
    agent.deleted_at = datetime.now(UTC)
    await session.flush()
    assert await sessions.get_by_id(conversation.id, owner.id) is None
    assert await sessions.list_by_user(owner.id, 1, 10) == []
    await session.rollback()
    assert (
        await session.execute(select(Session).where(Session.id == conversation.id))
    ).scalar_one_or_none() is None
