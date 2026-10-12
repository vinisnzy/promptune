import pytest

from promptune.modules.session.service import SessionService
from tests.unit.session.in_memory_repository import InMemorySessionRepository


@pytest.fixture
def session_repository() -> InMemorySessionRepository:
    return InMemorySessionRepository()


@pytest.fixture
def session_service(
    session_repository: InMemorySessionRepository,
) -> SessionService:
    return SessionService(session_repository)
