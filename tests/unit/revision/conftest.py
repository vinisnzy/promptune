import pytest

from promptune.services.agent import AgentService
from promptune.services.prompt import PromptService
from promptune.services.revision import RevisionService
from promptune.services.revision_generator import FakeRevisionGenerator
from tests.unit.agent.in_memory_repository import InMemoryAgentRepository
from tests.unit.prompt.in_memory_repository import InMemoryPromptRepository
from tests.unit.revision.in_memory_repository import InMemoryRevisionRepository


@pytest.fixture
def agent_repository() -> InMemoryAgentRepository:
    return InMemoryAgentRepository()


@pytest.fixture
def prompt_repository(
    agent_repository: InMemoryAgentRepository,
) -> InMemoryPromptRepository:
    return InMemoryPromptRepository(agent_repository)


@pytest.fixture
def revision_repository(
    agent_repository: InMemoryAgentRepository,
    prompt_repository: InMemoryPromptRepository,
) -> InMemoryRevisionRepository:
    return InMemoryRevisionRepository(agent_repository, prompt_repository)


@pytest.fixture
def agent_service(agent_repository: InMemoryAgentRepository) -> AgentService:
    return AgentService(agent_repository)


@pytest.fixture
def prompt_service(prompt_repository: InMemoryPromptRepository) -> PromptService:
    return PromptService(prompt_repository)


@pytest.fixture
def revision_service(
    revision_repository: InMemoryRevisionRepository,
    prompt_repository: InMemoryPromptRepository,
    agent_repository: InMemoryAgentRepository,
) -> RevisionService:
    return RevisionService(
        revision_repository,
        prompt_repository,
        agent_repository,
        FakeRevisionGenerator(),
    )
