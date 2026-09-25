from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from promptune.models.refresh_token import RefreshToken
from promptune.models.user import User
from promptune.repositories.user import IUserRepository


class InMemoryUserRepository(IUserRepository):
    def __init__(self) -> None:
        self.users: dict[UUID, User] = {}
        self.refresh_tokens: dict[str, RefreshToken] = {}

    async def get_user_by_email(self, email: str) -> User | None:
        return next((user for user in self.users.values() if user.email == email), None)

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        return self.users.get(user_id)

    async def add_user(self, data: dict[str, Any]) -> User:
        now = datetime.now(UTC)
        user = User(
            id=uuid4(),
            created_at=now,
            updated_at=now,
            is_active=True,
            deleted_at=None,
            **data,
        )
        self.users[user.id] = user
        return user

    async def update_user(self, user_id: UUID, data: dict[str, Any]) -> User | None:
        user = self.users.get(user_id)
        if user is None:
            return None
        for field, value in data.items():
            setattr(user, field, value)
        return user

    async def store_refresh_token(
        self, user_id: UUID, token_hash: str, expires_at: datetime
    ) -> RefreshToken:
        token = RefreshToken(
            id=uuid4(),
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            revoked_at=None,
        )
        self.refresh_tokens[token_hash] = token
        return token

    async def get_active_refresh_token(self, token_hash: str) -> RefreshToken | None:
        token = self.refresh_tokens.get(token_hash)
        if token is None or token.revoked_at is not None:
            return None
        return token if token.expires_at > datetime.now(UTC) else None

    async def revoke_refresh_token(self, token_hash: str) -> None:
        token = self.refresh_tokens.get(token_hash)
        if token is not None:
            token.revoked_at = datetime.now(UTC)

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        for token in self.refresh_tokens.values():
            if token.user_id == user_id and token.revoked_at is None:
                token.revoked_at = datetime.now(UTC)
