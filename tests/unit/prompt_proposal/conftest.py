import pytest

from promptune.modules.agent.service import AgentService
from promptune.modules.prompt.service import PromptService
from promptune.modules.prompt_proposal.service import PromptProposalService
from tests.unit.agent.in_memory_repository import InMemoryAgentRepository
from tests.unit.prompt.in_memory_repository import InMemoryPromptRepository
from tests.unit.prompt_proposal.fake_agent import FakePromptEditorAgent
from tests.unit.prompt_proposal.in_memory_repository import (
    InMemoryPromptProposalRepository,
)


@pytest.fixture
def agent_repository() -> InMemoryAgentRepository:
    return InMemoryAgentRepository()


@pytest.fixture
def prompt_repository(
    agent_repository: InMemoryAgentRepository,
) -> InMemoryPromptRepository:
    return InMemoryPromptRepository(agent_repository)


@pytest.fixture
def prompt_proposal_repository(
    agent_repository: InMemoryAgentRepository,
    prompt_repository: InMemoryPromptRepository,
) -> InMemoryPromptProposalRepository:
    return InMemoryPromptProposalRepository(agent_repository, prompt_repository)


@pytest.fixture
def agent_service(agent_repository: InMemoryAgentRepository) -> AgentService:
    return AgentService(agent_repository)


@pytest.fixture
def prompt_service(prompt_repository: InMemoryPromptRepository) -> PromptService:
    return PromptService(prompt_repository)


@pytest.fixture
def prompt_proposal_service(
    prompt_proposal_repository: InMemoryPromptProposalRepository,
    prompt_repository: InMemoryPromptRepository,
    agent_repository: InMemoryAgentRepository,
) -> PromptProposalService:
    return PromptProposalService(
        prompt_proposal_repository,
        prompt_repository,
        agent_repository,
        FakePromptEditorAgent(),
    )
