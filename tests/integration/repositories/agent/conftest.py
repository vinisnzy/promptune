import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from promptune.repositories.agent import AgentRepository


@pytest.fixture
def agent_repository(session: AsyncSession) -> AgentRepository:
    return AgentRepository(session)
