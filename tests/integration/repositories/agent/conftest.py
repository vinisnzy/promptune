import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from promptune.modules.agent.repository import AgentRepository


@pytest.fixture
def agent_repository(session: AsyncSession) -> AgentRepository:
    return AgentRepository(session)
