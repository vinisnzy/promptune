from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from promptune.core.exceptions import ConflictError, NotFoundError
from promptune.modules.session.schema import SessionCreate


def session_record(
    user_id: UUID,
    *,
    agent_id: UUID | None = None,
    status: str = "active",
) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        agent_id=agent_id or uuid4(),
        base_prompt_id=uuid4(),
        status=status,
        created_at=now,
        updated_at=now,
    )


async def test_should_create_session_for_authenticated_user(
    client: AsyncClient,
    session_service_mock: AsyncMock,
    auth_service_mock: AsyncMock,
    auth_headers: dict[str, str],
) -> None:
    user_id = auth_service_mock.get_user_from_access_token.return_value.id
    conversation = session_record(user_id)
    session_service_mock.create_session.return_value = conversation

    response = await client.post(
        "/sessions",
        json={
            "agent_id": str(conversation.agent_id),
            "base_prompt_id": str(conversation.base_prompt_id),
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["id"] == str(conversation.id)
    assert response.json()["status"] == "active"
    session_service_mock.create_session.assert_awaited_once_with(
        user_id,
        SessionCreate(
            agent_id=conversation.agent_id,
            base_prompt_id=conversation.base_prompt_id,
        ),
    )


async def test_should_list_owned_sessions_with_filters_and_pagination(
    client: AsyncClient,
    session_service_mock: AsyncMock,
    auth_service_mock: AsyncMock,
    auth_headers: dict[str, str],
) -> None:
    user_id = auth_service_mock.get_user_from_access_token.return_value.id
    agent_id = uuid4()
    conversation = session_record(user_id, agent_id=agent_id, status="completed")
    session_service_mock.list_sessions.return_value = [conversation]

    response = await client.get(
        "/sessions",
        params={
            "page": 2,
            "size": 5,
            "agent_id": str(agent_id),
            "status": "completed",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()[0]["id"] == str(conversation.id)
    session_service_mock.list_sessions.assert_awaited_once_with(
        user_id,
        2,
        5,
        agent_id=agent_id,
        status="completed",
    )


async def test_should_get_complete_and_delete_owned_session(
    client: AsyncClient,
    session_service_mock: AsyncMock,
    auth_service_mock: AsyncMock,
    auth_headers: dict[str, str],
) -> None:
    user_id = auth_service_mock.get_user_from_access_token.return_value.id
    conversation = session_record(user_id)
    completed = session_record(
        user_id, agent_id=conversation.agent_id, status="completed"
    )
    completed.id = conversation.id
    completed.base_prompt_id = conversation.base_prompt_id
    session_service_mock.get_session_by_id.return_value = conversation
    session_service_mock.complete_session.return_value = completed

    fetched = await client.get(f"/sessions/{conversation.id}", headers=auth_headers)
    completion = await client.post(
        f"/sessions/{conversation.id}/complete", headers=auth_headers
    )
    deletion = await client.delete(
        f"/sessions/{conversation.id}", headers=auth_headers
    )

    assert fetched.status_code == 200
    assert completion.status_code == 200
    assert completion.json()["status"] == "completed"
    assert deletion.status_code == 204
    assert deletion.content == b""
    session_service_mock.get_session_by_id.assert_awaited_once_with(
        conversation.id, user_id
    )
    session_service_mock.complete_session.assert_awaited_once_with(
        conversation.id, user_id
    )
    session_service_mock.delete_session.assert_awaited_once_with(
        conversation.id, user_id
    )


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/sessions", {"page": 0}),
        ("/sessions", {"size": 0}),
        ("/sessions", {"agent_id": "not-a-uuid"}),
        ("/sessions", {"status": "unknown"}),
        ("/sessions/not-a-uuid", {}),
    ],
)
async def test_should_reject_invalid_session_requests_before_service_call(
    client: AsyncClient,
    session_service_mock: AsyncMock,
    auth_headers: dict[str, str],
    path: str,
    params: dict[str, str | int],
) -> None:
    response = await client.get(path, params=params, headers=auth_headers)

    assert response.status_code == 422
    session_service_mock.list_sessions.assert_not_awaited()
    session_service_mock.get_session_by_id.assert_not_awaited()


async def test_should_map_missing_session_to_not_found(
    client: AsyncClient,
    session_service_mock: AsyncMock,
    auth_headers: dict[str, str],
) -> None:
    session_id = uuid4()
    session_service_mock.get_session_by_id.side_effect = NotFoundError(
        f"Session not found with id: {session_id}"
    )

    response = await client.get(f"/sessions/{session_id}", headers=auth_headers)

    assert response.status_code == 404
    assert response.json() == {"detail": f"Session not found with id: {session_id}"}


async def test_should_map_active_run_conflict_when_completing_session(
    client: AsyncClient,
    session_service_mock: AsyncMock,
    auth_headers: dict[str, str],
) -> None:
    session_id = uuid4()
    session_service_mock.complete_session.side_effect = ConflictError(
        "Session has an active agent run"
    )

    response = await client.post(
        f"/sessions/{session_id}/complete", headers=auth_headers
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Session has an active agent run"}


async def test_should_require_authentication_for_sessions(
    client: AsyncClient, session_service_mock: AsyncMock
) -> None:
    response = await client.get("/sessions")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
    session_service_mock.list_sessions.assert_not_awaited()
