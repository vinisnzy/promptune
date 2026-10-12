from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from httpx import AsyncClient

from promptune.modules.message.service import MessageDispatch


async def test_send_message_returns_accepted_run_location(
    client: AsyncClient,
    message_service_mock: AsyncMock,
    auth_service_mock: AsyncMock,
    auth_headers: dict[str, str],
) -> None:
    session_id = uuid4()
    message = SimpleNamespace(id=uuid4())
    run = SimpleNamespace(id=uuid4(), status="queued")
    message_service_mock.send_message.return_value = MessageDispatch(message, run)

    response = await client.post(
        f"/sessions/{session_id}/messages",
        json={"content": "  Improve greeting  "},
        headers=auth_headers,
    )

    assert response.status_code == 202
    assert response.headers["location"] == f"/agent-runs/{run.id}"
    assert response.json() == {
        "message_id": str(message.id),
        "run": {"id": str(run.id), "status": "queued"},
    }
    message_service_mock.send_message.assert_awaited_once()
    args = message_service_mock.send_message.await_args.args
    assert args[0] == session_id
    assert args[1] == auth_service_mock.get_user_from_access_token.return_value.id
    assert args[2].content == "  Improve greeting  "


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
