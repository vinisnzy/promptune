from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from httpx import AsyncClient

from promptune.core.exceptions import NotFoundError
from promptune.modules.agent_run.router import get_agent_run_event_service


def agent_run_record(status: str = "completed") -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        session_id=uuid4(),
        status=status,
        user_message_id=uuid4(),
        assistant_message_id=None,
        assistant_message=None,
        attempt_count=1,
        error_code=None,
        error_message=None,
        created_at=now,
        started_at=now,
        finished_at=now if status in {"completed", "failed", "canceled"} else None,
    )


class FakeAgentRunEventService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.snapshot_requests = []

    async def get_snapshot(self, run_id, user_id):
        self.snapshot_requests.append((run_id, user_id))
        if self.error is not None:
            raise self.error

    async def stream_events(self, run_id, user_id):
        yield (
            "event: run.updated\n"
            f'data: {{"id":"{run_id}","status":"completed"}}\n\n'
        )


async def test_get_agent_run_returns_authoritative_status(
    client: AsyncClient,
    agent_run_service_mock: AsyncMock,
    auth_service_mock: AsyncMock,
    auth_headers: dict[str, str],
) -> None:
    now = datetime.now(UTC)
    proposal = SimpleNamespace(id=uuid4())
    assistant = SimpleNamespace(proposal=proposal)
    run = SimpleNamespace(
        id=uuid4(),
        session_id=uuid4(),
        status="completed",
        user_message_id=uuid4(),
        assistant_message_id=uuid4(),
        assistant_message=assistant,
        attempt_count=1,
        error_code=None,
        error_message=None,
        created_at=now,
        started_at=now,
        finished_at=now,
    )
    agent_run_service_mock.get_run.return_value = run

    response = await client.get(f"/agent-runs/{run.id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["proposal_id"] == str(proposal.id)
    assert response.json()["status"] == "completed"
    agent_run_service_mock.get_run.assert_awaited_once_with(
        run.id, auth_service_mock.get_user_from_access_token.return_value.id
    )


async def test_stream_agent_run_events_returns_sse_response(
    client: AsyncClient,
    app,
    auth_service_mock: AsyncMock,
    auth_headers: dict[str, str],
) -> None:
    run = agent_run_record()
    event_service = FakeAgentRunEventService()
    app.dependency_overrides[get_agent_run_event_service] = lambda: event_service

    response = await client.get(f"/agent-runs/{run.id}/events", headers=auth_headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.text == (
        "event: run.updated\n"
        f'data: {{"id":"{run.id}","status":"completed"}}\n\n'
    )
    assert event_service.snapshot_requests == [
        (run.id, auth_service_mock.get_user_from_access_token.return_value.id)
    ]


async def test_stream_agent_run_events_checks_ownership_before_streaming(
    client: AsyncClient,
    app,
    auth_headers: dict[str, str],
) -> None:
    run_id = uuid4()
    event_service = FakeAgentRunEventService(
        NotFoundError(f"Agent run not found with id: {run_id}")
    )
    app.dependency_overrides[get_agent_run_event_service] = lambda: event_service

    response = await client.get(f"/agent-runs/{run_id}/events", headers=auth_headers)

    assert response.status_code == 404


async def test_stream_agent_run_events_requires_authentication(
    client: AsyncClient,
    agent_run_service_mock: AsyncMock,
) -> None:
    response = await client.get(f"/agent-runs/{uuid4()}/events")

    assert response.status_code == 401
    agent_run_service_mock.get_run.assert_not_awaited()
