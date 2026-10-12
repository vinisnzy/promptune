import pytest

from promptune.modules.message.service import MessageService
from promptune.modules.session.service import SessionService
from tests.unit.message.in_memory_repository import InMemoryMessageRepository
from tests.unit.session.in_memory_repository import InMemorySessionRepository


@pytest.fixture
def session_repository() -> InMemorySessionRepository:
    return InMemorySessionRepository()


@pytest.fixture
def session_service(
    session_repository: InMemorySessionRepository,
) -> SessionService:
    return SessionService(session_repository)


@pytest.fixture
def message_repository(
    session_repository: InMemorySessionRepository,
) -> InMemoryMessageRepository:
    return InMemoryMessageRepository(session_repository)


@pytest.fixture
def message_service(
    message_repository: InMemoryMessageRepository,
    session_repository: InMemorySessionRepository,
) -> MessageService:
    return MessageService(message_repository, session_repository)
