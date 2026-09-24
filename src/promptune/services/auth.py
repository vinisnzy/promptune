import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

import anyio
import jwt

from promptune.core.config import Settings
from promptune.core.exceptions import ConflictError, UnauthorizedError
from promptune.core.secret import (
    create_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)
from promptune.models.user import User
from promptune.repositories.user import IUserRepository
from promptune.schemas.auth import TokenPair, UserCreate

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, repository: IUserRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    async def register(self, payload: UserCreate) -> User:
        if await self.repository.get_user_by_email(payload.email):
            raise ConflictError(message="Email already registered")

        hash = await anyio.to_thread.run_sync(hash_password, payload.password)
        user = await self.repository.add_user(
            {"email": payload.email, "hashed_password": hash}
        )
        logger.info(
            "User registered",
            extra={"event": "user_registered", "user_id": str(user.id)},
        )
        return user

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.repository.get_user_by_email(email)

        if user is None:
            raise UnauthorizedError(message="Invalid credentials")

        valid = await anyio.to_thread.run_sync(
            verify_password, password, user.hashed_password
        )
        if not valid or not user.is_active:
            raise UnauthorizedError(message="Invalid credentials")

        return user

    async def issue_tokens(self, user: User) -> TokenPair:
        user_id = user.id
        access = create_token(
            user_id,
            "access",
            timedelta(minutes=self.settings.access_token_expires_in_minutes),
            self.settings,
        )

        refresh_expires = timedelta(days=self.settings.refresh_token_expires_in_days)
        refresh = create_token(
            user_id,
            "refresh",
            refresh_expires,
            self.settings,
        )

        await self.repository.store_refresh_token(
            user_id=user_id,
            token_hash=hash_token(refresh),
            expires_at=datetime.now(UTC) + refresh_expires,
        )
        return TokenPair(access_token=access, refresh_token=refresh)

    async def login(self, email: str, password: str) -> TokenPair:
        user = await self.authenticate(email, password)
        tokens = await self.issue_tokens(user)
        logger.info(
            "User logged in",
            extra={"event": "login_succeeded", "user_id": str(user.id)},
        )
        return tokens

    async def refresh(self, refresh_token: str) -> TokenPair:
        try:
            decode_token(refresh_token, "refresh", self.settings)
        except jwt.ExpiredSignatureError as exc:
            error = UnauthorizedError(message="Invalid refresh token")
            raise error from exc
        except jwt.PyJWTError as exc:
            raise UnauthorizedError(message="Invalid refresh token") from exc
        token_hash = hash_token(refresh_token)
        stored = await self.repository.get_active_refresh_token(token_hash)

        if stored is None:
            raise UnauthorizedError(message="Invalid refresh token")

        user = await self.repository.get_user_by_id(stored.user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError(message="Invalid refresh token")

        await self.repository.revoke_refresh_token(token_hash)
        tokens = await self.issue_tokens(user)
        logger.info(
            "Tokens refreshed",
            extra={"event": "tokens_refreshed", "user_id": str(user.id)},
        )
        return tokens

    async def logout(self, refresh_token: str) -> None:
        await self.repository.revoke_refresh_token(hash_token(refresh_token))
        logger.info("User logged out", extra={"event": "logout_succeeded"})

    async def get_user_from_access_token(self, token: str) -> User:
        try:
            payload = decode_token(token, "access", self.settings)
            user_id = UUID(payload["sub"])
        except (
            jwt.PyJWTError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise UnauthorizedError(message="Invalid or expired access token") from exc

        user = await self.repository.get_user_by_id(user_id)
        if user is None or not user.is_active or user.deleted_at is not None:
            raise UnauthorizedError(message="Invalid or expired access token")

        return user
