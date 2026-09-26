from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from promptune.models.refresh_token import RefreshToken
from promptune.repositories.user import UserRepository

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_should_add_and_find_user(user_repository: UserRepository) -> None:
    user = await user_repository.add_user(
        {"email": "person@example.com", "hashed_password": "hashed-password"}
    )

    assert user.id is not None
    assert user.email == "person@example.com"
    assert await user_repository.get_user_by_email(user.email) is user
    assert await user_repository.get_user_by_id(user.id) is user
    assert await user_repository.get_user_by_email("missing@example.com") is None
    assert await user_repository.get_user_by_id(uuid4()) is None


async def test_should_enforce_unique_user_email(
    user_repository: UserRepository,
) -> None:
    data = {"email": "duplicate@example.com", "hashed_password": "hashed-password"}
    await user_repository.add_user(data)

    with pytest.raises(IntegrityError):
        await user_repository.add_user(data)


async def test_should_update_user_and_handle_missing_id(
    user_repository: UserRepository,
) -> None:
    user = await user_repository.add_user(
        {"email": "person@example.com", "hashed_password": "hashed-password"}
    )
    deleted_at = datetime.now(UTC)

    updated = await user_repository.update_user(
        user.id, {"is_active": False, "deleted_at": deleted_at}
    )

    assert updated is not None
    assert updated.is_active is False
    assert updated.deleted_at is not None
    assert await user_repository.get_user_by_id(user.id) is updated
    assert await user_repository.update_user(user.id, {}) is updated
    assert await user_repository.update_user(uuid4(), {"is_active": False}) is None


async def test_should_store_and_find_only_active_refresh_tokens(
    user_repository: UserRepository,
) -> None:
    user = await user_repository.add_user(
        {"email": "person@example.com", "hashed_password": "hashed-password"}
    )
    active_hash = uuid4().hex
    expired_hash = uuid4().hex
    active = await user_repository.store_refresh_token(
        user.id, active_hash, datetime.now(UTC) + timedelta(days=1)
    )
    await user_repository.store_refresh_token(
        user.id, expired_hash, datetime.now(UTC) - timedelta(days=1)
    )

    assert await user_repository.get_active_refresh_token(active_hash) is active
    assert await user_repository.get_active_refresh_token(expired_hash) is None
    assert await user_repository.get_active_refresh_token("missing") is None


async def test_should_revoke_one_refresh_token(
    user_repository: UserRepository,
) -> None:
    user = await user_repository.add_user(
        {"email": "person@example.com", "hashed_password": "hashed-password"}
    )
    first_hash = uuid4().hex
    second_hash = uuid4().hex
    expires_at = datetime.now(UTC) + timedelta(days=1)
    await user_repository.store_refresh_token(user.id, first_hash, expires_at)
    second = await user_repository.store_refresh_token(user.id, second_hash, expires_at)

    await user_repository.revoke_refresh_token(first_hash)

    revoked_at = await user_repository.session.scalar(
        select(RefreshToken.revoked_at).where(RefreshToken.token_hash == first_hash)
    )
    assert revoked_at is not None
    assert await user_repository.get_active_refresh_token(first_hash) is None
    assert await user_repository.get_active_refresh_token(second_hash) is second


async def test_should_revoke_all_refresh_tokens_only_for_requested_user(
    user_repository: UserRepository,
) -> None:
    user = await user_repository.add_user(
        {"email": "first@example.com", "hashed_password": "hashed-password"}
    )
    other = await user_repository.add_user(
        {"email": "second@example.com", "hashed_password": "hashed-password"}
    )
    expires_at = datetime.now(UTC) + timedelta(days=1)
    first_hash = uuid4().hex
    second_hash = uuid4().hex
    other_hash = uuid4().hex
    await user_repository.store_refresh_token(user.id, first_hash, expires_at)
    await user_repository.store_refresh_token(user.id, second_hash, expires_at)
    other_token = await user_repository.store_refresh_token(
        other.id, other_hash, expires_at
    )

    await user_repository.revoke_all_for_user(user.id)

    assert await user_repository.get_active_refresh_token(first_hash) is None
    assert await user_repository.get_active_refresh_token(second_hash) is None
    assert await user_repository.get_active_refresh_token(other_hash) is other_token
