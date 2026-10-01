import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from promptune.modules.auth.repository import UserRepository


@pytest.fixture
def user_repository(session: AsyncSession) -> UserRepository:
    return UserRepository(session)
