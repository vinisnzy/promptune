from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from promptune.core.exceptions import NotFoundError
from promptune.modules.message.service import MessageDispatch


def message_record(
    session_id: UUID,
    *,
    content: str,
    created_at: datetime,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        session_id=session_id,
        role="user",
        content=content,
        questions=[],
        warnings=[],
        reply_to_id=None,
        base_proposal_id=None,
        created_at=created_at,
        updated_at=created_at,
    )


async def test_should_send_message_and_return_accepted_run_location(
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


async def test_should_list_session_messages_in_service_order(
    client: AsyncClient,
    message_service_mock: AsyncMock,
    auth_service_mock: AsyncMock,
    auth_headers: dict[str, str],
) -> None:
    session_id = uuid4()
    now = datetime.now(UTC)
    first = message_record(session_id, content="First", created_at=now)
    second = message_record(
        session_id, content="Second", created_at=now + timedelta(seconds=1)
    )
    message_service_mock.list_messages.return_value = [first, second]

    response = await client.get(
        f"/sessions/{session_id}/messages",
        params={"page": 2, "size": 5},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(first.id), str(second.id)]
    message_service_mock.list_messages.assert_awaited_once_with(
        session_id,
        auth_service_mock.get_user_from_access_token.return_value.id,
        2,
        5,
    )


async def test_should_get_message_from_owned_session(
    client: AsyncClient,
    message_service_mock: AsyncMock,
    auth_service_mock: AsyncMock,
    auth_headers: dict[str, str],
) -> None:
    session_id = uuid4()
    message = message_record(
        session_id, content="Improve greeting", created_at=datetime.now(UTC)
    )
    message_service_mock.get_message_by_id.return_value = message

    response = await client.get(
        f"/sessions/{session_id}/messages/{message.id}", headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json()["content"] == "Improve greeting"
    message_service_mock.get_message_by_id.assert_awaited_once_with(
        message.id,
        session_id,
        auth_service_mock.get_user_from_access_token.return_value.id,
    )


@pytest.mark.parametrize(
    ("path", "params"),
    [
        (f"/sessions/{uuid4()}/messages", {"page": 0}),
        (f"/sessions/{uuid4()}/messages", {"size": 0}),
        ("/sessions/not-a-uuid/messages", {}),
        (f"/sessions/{uuid4()}/messages/not-a-uuid", {}),
    ],
)
async def test_should_reject_invalid_message_reads_before_service_call(
    client: AsyncClient,
    message_service_mock: AsyncMock,
    auth_headers: dict[str, str],
    path: str,
    params: dict[str, int],
) -> None:
    response = await client.get(path, params=params, headers=auth_headers)

    assert response.status_code == 422
    message_service_mock.list_messages.assert_not_awaited()
    message_service_mock.get_message_by_id.assert_not_awaited()


async def test_should_hide_message_outside_owned_session(
    client: AsyncClient,
    message_service_mock: AsyncMock,
    auth_headers: dict[str, str],
) -> None:
    session_id = uuid4()
    message_id = uuid4()
    message_service_mock.get_message_by_id.side_effect = NotFoundError(
        f"Message not found with id: {message_id}"
    )

    response = await client.get(
        f"/sessions/{session_id}/messages/{message_id}", headers=auth_headers
    )

    assert response.status_code == 404
    assert response.json() == {"detail": f"Message not found with id: {message_id}"}


async def test_should_require_authentication_for_message_reads(
    client: AsyncClient, message_service_mock: AsyncMock
) -> None:
    response = await client.get(f"/sessions/{uuid4()}/messages")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
    message_service_mock.list_messages.assert_not_awaited()
