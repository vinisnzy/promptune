import pytest

from promptune.core.config import Settings
from promptune.models.user import User
from promptune.schemas.auth import UserCreate
from promptune.services.auth import AuthService
from tests.unit.auth.in_memory_repository import InMemoryUserRepository


@pytest.fixture
def user_repository() -> InMemoryUserRepository:
    return InMemoryUserRepository()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://test:test@localhost/test",
        jwt_secret="test-secret-for-unit-tests-at-least-32-bytes",
        jwt_algorithm="HS256",
        access_token_expires_in_minutes=15,
        refresh_token_expires_in_days=7,
    )


@pytest.fixture
def auth_service(
    user_repository: InMemoryUserRepository, settings: Settings
) -> AuthService:
    return AuthService(user_repository, settings)


@pytest.fixture
async def registered_user(auth_service: AuthService) -> User:
    return await auth_service.register(
        UserCreate(email="person@example.com", password="correct-password")
    )
