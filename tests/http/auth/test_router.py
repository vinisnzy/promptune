from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from httpx import AsyncClient

from promptune.core.exceptions import ConflictError, UnauthorizedError
from promptune.schemas.auth import TokenPair, UserCreate


async def test_should_register_user_and_serialize_response(
    client: AsyncClient, auth_service_mock: AsyncMock
) -> None:
    user_id = uuid4()
    auth_service_mock.register.return_value = SimpleNamespace(
        id=user_id, email="person@example.com"
    )

    response = await client.post(
        "/auth/register",
        json={"email": "person@example.com", "password": "strong-password"},
    )

    assert response.status_code == 201
    assert response.json() == {"id": str(user_id), "email": "person@example.com"}
    auth_service_mock.register.assert_awaited_once_with(
        UserCreate(email="person@example.com", password="strong-password")
    )


async def test_should_reject_invalid_registration_before_calling_service(
    client: AsyncClient, auth_service_mock: AsyncMock
) -> None:
    response = await client.post(
        "/auth/register", json={"email": "invalid", "password": "short"}
    )

    assert response.status_code == 422
    auth_service_mock.register.assert_not_awaited()


async def test_should_map_duplicate_registration_to_conflict(
    client: AsyncClient, auth_service_mock: AsyncMock
) -> None:
    auth_service_mock.register.side_effect = ConflictError("Email already registered")

    response = await client.post(
        "/auth/register",
        json={"email": "person@example.com", "password": "strong-password"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Email already registered"}


async def test_should_login_with_query_credentials(
    client: AsyncClient, auth_service_mock: AsyncMock
) -> None:
    auth_service_mock.login.return_value = TokenPair(
        access_token="access", refresh_token="refresh"
    )

    response = await client.post(
        "/auth/login", params={"email": "person@example.com", "password": "secret"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "access_token": "access",
        "refresh_token": "refresh",
        "token_type": "bearer",
    }
    auth_service_mock.login.assert_awaited_once_with("person@example.com", "secret")


async def test_should_require_login_query_credentials(
    client: AsyncClient, auth_service_mock: AsyncMock
) -> None:
    response = await client.post("/auth/login", json={"email": "person@example.com"})

    assert response.status_code == 422
    auth_service_mock.login.assert_not_awaited()


async def test_should_map_invalid_login_to_unauthorized(
    client: AsyncClient, auth_service_mock: AsyncMock
) -> None:
    auth_service_mock.login.side_effect = UnauthorizedError("Invalid credentials")

    response = await client.post(
        "/auth/login", params={"email": "person@example.com", "password": "wrong"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}


async def test_should_refresh_tokens_from_request_body(
    client: AsyncClient, auth_service_mock: AsyncMock
) -> None:
    auth_service_mock.refresh.return_value = TokenPair(
        access_token="new-access", refresh_token="new-refresh"
    )

    response = await client.post("/auth/refresh", json={"refresh_token": "old"})

    assert response.status_code == 200
    assert response.json()["refresh_token"] == "new-refresh"
    auth_service_mock.refresh.assert_awaited_once_with("old")


async def test_should_map_invalid_refresh_token_to_unauthorized(
    client: AsyncClient, auth_service_mock: AsyncMock
) -> None:
    auth_service_mock.refresh.side_effect = UnauthorizedError("Invalid refresh token")

    response = await client.post("/auth/refresh", json={"refresh_token": "bad"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid refresh token"}


async def test_should_logout_with_no_content_response(
    client: AsyncClient, auth_service_mock: AsyncMock
) -> None:
    response = await client.post("/auth/logout", json={"refresh_token": "token"})

    assert response.status_code == 204
    assert response.content == b""
    auth_service_mock.logout.assert_awaited_once_with("token")


async def test_should_return_current_user_for_bearer_token(
    client: AsyncClient, auth_service_mock: AsyncMock, auth_headers: dict[str, str]
) -> None:
    user = auth_service_mock.get_user_from_access_token.return_value

    response = await client.get("/auth/me", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"id": str(user.id), "email": user.email}
    auth_service_mock.get_user_from_access_token.assert_awaited_once_with("test-token")


async def test_should_require_bearer_token_for_current_user(
    client: AsyncClient, auth_service_mock: AsyncMock
) -> None:
    response = await client.get("/auth/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
    auth_service_mock.get_user_from_access_token.assert_not_awaited()


async def test_should_map_invalid_bearer_token_to_unauthorized(
    client: AsyncClient, auth_service_mock: AsyncMock, auth_headers: dict[str, str]
) -> None:
    auth_service_mock.get_user_from_access_token.side_effect = UnauthorizedError(
        "Invalid or expired access token"
    )

    response = await client.get("/auth/me", headers=auth_headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired access token"}


async def test_should_add_request_id_to_success_and_error_responses(
    client: AsyncClient, auth_service_mock: AsyncMock, auth_headers: dict[str, str]
) -> None:
    success = await client.get("/auth/me", headers=auth_headers)
    error = await client.get("/auth/me")

    assert success.status_code == 200
    assert error.status_code == 401
    assert UUID(success.headers["X-Request-ID"])
    assert UUID(error.headers["X-Request-ID"])
    assert success.headers["X-Request-ID"] != error.headers["X-Request-ID"]


async def test_should_return_generic_server_error_without_leaking_exception(
    client: AsyncClient, auth_service_mock: AsyncMock
) -> None:
    auth_service_mock.register.side_effect = RuntimeError("secret internal failure")

    response = await client.post(
        "/auth/register",
        json={"email": "person@example.com", "password": "strong-password"},
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert UUID(response.headers["X-Request-ID"])
