from uuid import uuid4

import pytest

from promptune.core.exceptions import InvalidInputError, NotFoundError
from promptune.modules.session.model import SessionStatus
from promptune.modules.session.schema import SessionCreate
from promptune.modules.session.service import SessionService
from tests.unit.session.in_memory_repository import InMemorySessionRepository


async def test_should_create_get_and_list_only_owned_sessions(
    session_service: SessionService,
) -> None:
    owner_id = uuid4()
    other_id = uuid4()
    agent_id = uuid4()
    data = SessionCreate(agent_id=agent_id, base_prompt_id=uuid4())

    first = await session_service.create_session(owner_id, data)
    second = await session_service.create_session(owner_id, data)
    await session_service.create_session(
        other_id, SessionCreate(agent_id=uuid4(), base_prompt_id=uuid4())
    )

    assert first.status == SessionStatus.ACTIVE
    assert await session_service.get_session_by_id(first.id, owner_id) is first
    assert await session_service.list_sessions(owner_id, 1, 1) == [second]
    assert await session_service.list_sessions(owner_id, 2, 1) == [first]
    assert await session_service.list_sessions(
        owner_id, 1, 10, agent_id=agent_id, status=SessionStatus.ACTIVE
    ) == [second, first]
    with pytest.raises(NotFoundError):
        await session_service.get_session_by_id(first.id, other_id)


async def test_should_complete_session_idempotently(
    session_service: SessionService,
) -> None:
    owner_id = uuid4()
    conversation = await session_service.create_session(
        owner_id, SessionCreate(agent_id=uuid4(), base_prompt_id=uuid4())
    )

    completed = await session_service.complete_session(conversation.id, owner_id)
    completed_again = await session_service.complete_session(conversation.id, owner_id)

    assert completed is conversation
    assert completed_again is conversation
    assert conversation.status == SessionStatus.COMPLETED
    assert await session_service.list_sessions(
        owner_id, 1, 10, status=SessionStatus.COMPLETED
    ) == [conversation]


async def test_should_soft_delete_session_and_hide_it(
    session_service: SessionService,
    session_repository: InMemorySessionRepository,
) -> None:
    owner_id = uuid4()
    conversation = await session_service.create_session(
        owner_id, SessionCreate(agent_id=uuid4(), base_prompt_id=uuid4())
    )

    with pytest.raises(NotFoundError):
        await session_service.delete_session(conversation.id, uuid4())
    await session_service.delete_session(conversation.id, owner_id)

    assert conversation.id in session_repository.sessions
    assert conversation.deleted_at is not None
    assert await session_service.list_sessions(owner_id, 1, 10) == []
    with pytest.raises(NotFoundError):
        await session_service.get_session_by_id(conversation.id, owner_id)
    with pytest.raises(NotFoundError):
        await session_service.complete_session(conversation.id, owner_id)
    with pytest.raises(NotFoundError):
        await session_service.delete_session(conversation.id, owner_id)


async def test_should_reject_invalid_session_queries(
    session_service: SessionService,
) -> None:
    owner_id = uuid4()

    for page, size in [(0, 1), (1, 0), (-1, 2)]:
        with pytest.raises(InvalidInputError):
            await session_service.list_sessions(owner_id, page, size)
    with pytest.raises(InvalidInputError):
        await session_service.list_sessions(owner_id, 1, 10, status="invalid")  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        await session_service.get_session_by_id(uuid4(), owner_id)
    with pytest.raises(NotFoundError):
        await session_service.complete_session(uuid4(), owner_id)
    with pytest.raises(NotFoundError):
        await session_service.delete_session(uuid4(), owner_id)
