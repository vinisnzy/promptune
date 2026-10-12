from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from promptune.core.exceptions import NotFoundError
from promptune.modules.agent_run.service import AgentRunService, serialize_agent_run
from tests.unit.agent_run.in_memory_repository import InMemoryAgentRunRepository
from tests.unit.session.in_memory_repository import InMemorySessionRepository


async def test_should_get_run_only_for_session_owner() -> None:
    sessions = InMemorySessionRepository()
    owner_id = uuid4()
    conversation = await sessions.create(
        user_id=owner_id, agent_id=uuid4(), base_prompt_id=uuid4()
    )
    repository = InMemoryAgentRunRepository(sessions)
    service = AgentRunService(repository)
    run = await repository.create(session_id=conversation.id, user_message_id=uuid4())

    assert await service.get_run(run.id, owner_id) is run
    with pytest.raises(NotFoundError):
        await service.get_run(run.id, uuid4())


def test_should_serialize_result_and_safe_error() -> None:
    now = datetime.now(UTC)
    proposal_id = uuid4()
    run = SimpleNamespace(
        id=uuid4(),
        session_id=uuid4(),
        status="failed",
        user_message_id=uuid4(),
        assistant_message_id=None,
        assistant_message=None,
        attempt_count=3,
        error_code="run_timeout",
        error_message="The run exceeded the retry limit",
        created_at=now,
        started_at=now,
        finished_at=now,
    )

    result = serialize_agent_run(run)

    assert result.error is not None
    assert result.error.code == "run_timeout"
    assert result.proposal_id is None
    run.assistant_message = SimpleNamespace(proposal=SimpleNamespace(id=proposal_id))
    assert serialize_agent_run(run).proposal_id == proposal_id
