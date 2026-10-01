from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from promptune.core.config import Settings, get_settings
from promptune.main import create_app
from promptune.modules.agent.router import get_agent_service
from promptune.modules.agent.service import AgentService
from promptune.modules.auth.dependencies import get_auth_service
from promptune.modules.auth.service import AuthService
from promptune.modules.prompt.router import get_prompt_service
from promptune.modules.prompt.service import PromptService
from promptune.modules.revision.router import get_revision_service
from promptune.modules.revision.service import RevisionService


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://test:test@localhost/unused",
        jwt_secret="test-secret-for-http-tests-at-least-32-bytes",
        jwt_algorithm="HS256",
    )


@pytest.fixture
def auth_service_mock() -> AsyncMock:
    service = AsyncMock(spec=AuthService)
    service.get_user_from_access_token.return_value = SimpleNamespace(
        id=uuid4(), email="person@example.com"
    )
    return service


@pytest.fixture
def agent_service_mock() -> AsyncMock:
    return AsyncMock(spec=AgentService)


@pytest.fixture
def prompt_service_mock() -> AsyncMock:
    return AsyncMock(spec=PromptService)


@pytest.fixture
def revision_service_mock() -> AsyncMock:
    return AsyncMock(spec=RevisionService)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def app(
    settings: Settings,
    auth_service_mock: AsyncMock,
    agent_service_mock: AsyncMock,
    prompt_service_mock: AsyncMock,
    revision_service_mock: AsyncMock,
) -> FastAPI:
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_auth_service] = lambda: auth_service_mock
    app.dependency_overrides[get_agent_service] = lambda: agent_service_mock
    app.dependency_overrides[get_prompt_service] = lambda: prompt_service_mock
    app.dependency_overrides[get_revision_service] = lambda: revision_service_mock
    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    try:
        async with LifespanManager(app) as manager:
            transport = ASGITransport(app=manager.app, raise_app_exceptions=False)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                yield client
    finally:
        app.dependency_overrides.clear()
