import pytest

from promptune.services.agent import AgentService
from tests.unit.agent.in_memory_repository import InMemoryAgentRepository


@pytest.fixture
def agent_repository() -> InMemoryAgentRepository:
    return InMemoryAgentRepository()


@pytest.fixture
def agent_service(agent_repository: InMemoryAgentRepository) -> AgentService:
    return AgentService(agent_repository)
