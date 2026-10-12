import pytest

from promptune.modules.prompt_proposal.service import PromptProposalService
from tests.unit.prompt_proposal.in_memory_repository import (
    InMemoryPromptProposalRepository,
)


@pytest.fixture
def prompt_proposal_repository() -> InMemoryPromptProposalRepository:
    return InMemoryPromptProposalRepository()


@pytest.fixture
def prompt_proposal_service(
    prompt_proposal_repository: InMemoryPromptProposalRepository,
) -> PromptProposalService:
    return PromptProposalService(prompt_proposal_repository)
