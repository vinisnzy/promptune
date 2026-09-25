import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from promptune.repositories.agent import AgentRepository
from promptune.repositories.prompt import PromptRepository


@pytest.fixture
def agent_repository(session: AsyncSession) -> AgentRepository:
    return AgentRepository(session)


@pytest.fixture
def prompt_repository(session: AsyncSession) -> PromptRepository:
    return PromptRepository(session)
