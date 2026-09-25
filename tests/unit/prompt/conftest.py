import pytest

from promptune.services.agent import AgentService
from promptune.services.prompt import PromptService
from tests.unit.agent.in_memory_repository import InMemoryAgentRepository
from tests.unit.prompt.in_memory_repository import InMemoryPromptRepository


@pytest.fixture
def agent_repository() -> InMemoryAgentRepository:
    return InMemoryAgentRepository()


@pytest.fixture
def agent_service(agent_repository: InMemoryAgentRepository) -> AgentService:
    return AgentService(agent_repository)


@pytest.fixture
def prompt_repository(
    agent_repository: InMemoryAgentRepository,
) -> InMemoryPromptRepository:
    return InMemoryPromptRepository(agent_repository)


@pytest.fixture
def prompt_service(prompt_repository: InMemoryPromptRepository) -> PromptService:
    return PromptService(prompt_repository)
