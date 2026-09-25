from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from promptune.core.config import Settings
from promptune.core.exceptions import ConflictError, UnauthorizedError
from promptune.core.secret import (
    create_token,
    decode_token,
    hash_token,
    verify_password,
)
from promptune.models.user import User
from promptune.schemas.auth import UserCreate
from promptune.services.auth import AuthService
from tests.unit.auth.in_memory_repository import InMemoryUserRepository

EMAIL = "person@example.com"
PASSWORD = "correct-password"


async def test_should_hash_password_when_registering_user(
    auth_service: AuthService, user_repository: InMemoryUserRepository
) -> None:
    user = await auth_service.register(UserCreate(email=EMAIL, password=PASSWORD))

    assert await user_repository.get_user_by_email(EMAIL) is user
    assert user.hashed_password != PASSWORD
    assert verify_password(PASSWORD, user.hashed_password)


async def test_should_reject_duplicate_email_when_registering_user(
    auth_service: AuthService, registered_user: User
) -> None:
    with pytest.raises(ConflictError, match="Email already registered"):
        await auth_service.register(UserCreate(email=EMAIL, password=PASSWORD))


async def test_should_authenticate_valid_credentials(
    auth_service: AuthService, registered_user: User
) -> None:
    assert await auth_service.authenticate(EMAIL, PASSWORD) is registered_user


async def test_should_reject_missing_user_wrong_password_and_inactive_user(
    auth_service: AuthService, registered_user: User
) -> None:
    with pytest.raises(UnauthorizedError, match="Invalid credentials"):
        await auth_service.authenticate("missing@example.com", PASSWORD)
    with pytest.raises(UnauthorizedError, match="Invalid credentials"):
        await auth_service.authenticate(EMAIL, "wrong-password")
    registered_user.is_active = False
    with pytest.raises(UnauthorizedError, match="Invalid credentials"):
        await auth_service.authenticate(EMAIL, PASSWORD)


async def test_should_store_refresh_token_when_issuing_tokens(
    auth_service: AuthService,
    registered_user: User,
    user_repository: InMemoryUserRepository,
    settings: Settings,
) -> None:
    tokens = await auth_service.issue_tokens(registered_user)

    assert decode_token(tokens.access_token, "access", settings)["sub"] == str(
        registered_user.id
    )
    assert decode_token(tokens.refresh_token, "refresh", settings)["sub"] == str(
        registered_user.id
    )
    stored = await user_repository.get_active_refresh_token(
        hash_token(tokens.refresh_token)
    )
    assert stored is not None
    assert stored.user_id == registered_user.id


async def test_should_issue_tokens_when_logging_in(
    auth_service: AuthService, registered_user: User, settings: Settings
) -> None:
    tokens = await auth_service.login(EMAIL, PASSWORD)

    assert decode_token(tokens.access_token, "access", settings)["sub"] == str(
        registered_user.id
    )


async def test_should_reject_invalid_credentials_when_logging_in(
    auth_service: AuthService,
) -> None:
    with pytest.raises(UnauthorizedError):
        await auth_service.login(EMAIL, PASSWORD)


async def test_should_rotate_refresh_token_and_reject_replay(
    auth_service: AuthService,
    registered_user: User,
    user_repository: InMemoryUserRepository,
) -> None:
    original = await auth_service.issue_tokens(registered_user)

    rotated = await auth_service.refresh(original.refresh_token)

    assert rotated.refresh_token != original.refresh_token
    assert (
        user_repository.refresh_tokens[hash_token(original.refresh_token)].revoked_at
        is not None
    )
    assert (
        await user_repository.get_active_refresh_token(
            hash_token(rotated.refresh_token)
        )
        is not None
    )
    with pytest.raises(UnauthorizedError, match="Invalid refresh token"):
        await auth_service.refresh(original.refresh_token)


async def test_should_reject_malformed_wrong_type_expired_and_unstored_refresh_token(
    auth_service: AuthService, registered_user: User, settings: Settings
) -> None:
    access = create_token(registered_user.id, "access", timedelta(minutes=5), settings)
    expired = create_token(registered_user.id, "refresh", timedelta(days=-1), settings)
    unknown = create_token(registered_user.id, "refresh", timedelta(days=1), settings)

    for token in ("not-a-token", access, expired, unknown):
        with pytest.raises(UnauthorizedError, match="Invalid refresh token"):
            await auth_service.refresh(token)


async def test_should_reject_refresh_for_missing_or_inactive_user(
    auth_service: AuthService,
    registered_user: User,
    user_repository: InMemoryUserRepository,
) -> None:
    tokens = await auth_service.issue_tokens(registered_user)
    registered_user.is_active = False
    with pytest.raises(UnauthorizedError):
        await auth_service.refresh(tokens.refresh_token)

    del user_repository.users[registered_user.id]
    with pytest.raises(UnauthorizedError):
        await auth_service.refresh(tokens.refresh_token)


async def test_should_revoke_refresh_token_when_logging_out(
    auth_service: AuthService, registered_user: User
) -> None:
    tokens = await auth_service.issue_tokens(registered_user)

    await auth_service.logout(tokens.refresh_token)

    with pytest.raises(UnauthorizedError, match="Invalid refresh token"):
        await auth_service.refresh(tokens.refresh_token)


async def test_should_resolve_active_user_from_access_token(
    auth_service: AuthService, registered_user: User
) -> None:
    tokens = await auth_service.issue_tokens(registered_user)

    assert (
        await auth_service.get_user_from_access_token(tokens.access_token)
        is registered_user
    )


async def test_should_reject_malformed_wrong_type_expired_and_unknown_access_token(
    auth_service: AuthService, registered_user: User, settings: Settings
) -> None:
    refresh = create_token(registered_user.id, "refresh", timedelta(days=1), settings)
    expired = create_token(registered_user.id, "access", timedelta(days=-1), settings)
    unknown = create_token(uuid4(), "access", timedelta(minutes=5), settings)

    for token in ("not-a-token", refresh, expired, unknown):
        with pytest.raises(UnauthorizedError, match="Invalid or expired access token"):
            await auth_service.get_user_from_access_token(token)


async def test_should_reject_access_token_for_inactive_and_deleted_user(
    auth_service: AuthService, registered_user: User
) -> None:
    tokens = await auth_service.issue_tokens(registered_user)
    registered_user.is_active = False
    with pytest.raises(UnauthorizedError):
        await auth_service.get_user_from_access_token(tokens.access_token)

    registered_user.is_active = True
    registered_user.deleted_at = datetime.now(UTC)
    with pytest.raises(UnauthorizedError):
        await auth_service.get_user_from_access_token(tokens.access_token)
