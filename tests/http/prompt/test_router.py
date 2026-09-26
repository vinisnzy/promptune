from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from promptune.core.exceptions import NotFoundError
from promptune.schemas.prompt import PromptCreate


def prompt_record(agent_id: UUID, version: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        agent_id=agent_id,
        description=f"v{version}",
        content="Instructions",
        version=version,
    )


async def test_should_list_prompts_for_agent_with_pagination(
    client: AsyncClient, prompt_service_mock: AsyncMock, auth_headers: dict[str, str]
) -> None:
    agent_id = uuid4()
    prompt = prompt_record(agent_id)
    prompt_service_mock.get_prompts_by_agent.return_value = [prompt]

    response = await client.get(
        "/prompts",
        params={"agent_id": str(agent_id), "page": 2, "size": 5},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(prompt.id),
            "agent_id": str(agent_id),
            "description": "v1",
            "content": "Instructions",
            "version": 1,
        }
    ]
    prompt_service_mock.get_prompts_by_agent.assert_awaited_once_with(agent_id, 2, 5)


@pytest.mark.parametrize(
    "params",
    [{}, {"agent_id": "bad"}, {"agent_id": str(uuid4()), "page": 0}],
)
async def test_should_reject_invalid_prompt_list_query_before_service_call(
    client: AsyncClient,
    prompt_service_mock: AsyncMock,
    auth_headers: dict[str, str],
    params: dict[str, str | int],
) -> None:
    response = await client.get("/prompts", params=params, headers=auth_headers)

    assert response.status_code == 422
    prompt_service_mock.get_prompts_by_agent.assert_not_awaited()


async def test_should_get_prompt_by_uuid(
    client: AsyncClient, prompt_service_mock: AsyncMock, auth_headers: dict[str, str]
) -> None:
    prompt = prompt_record(uuid4())
    prompt_service_mock.get_prompt_by_id.return_value = prompt

    response = await client.get(f"/prompts/{prompt.id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == str(prompt.id)
    prompt_service_mock.get_prompt_by_id.assert_awaited_once_with(prompt.id)


async def test_should_get_current_prompt_for_agent(
    client: AsyncClient, prompt_service_mock: AsyncMock, auth_headers: dict[str, str]
) -> None:
    agent_id = uuid4()
    prompt = prompt_record(agent_id, version=3)
    prompt_service_mock.get_current_prompt_by_agent.return_value = prompt

    response = await client.get(
        "/prompts/current", params={"agent_id": str(agent_id)}, headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json()["version"] == 3
    prompt_service_mock.get_current_prompt_by_agent.assert_awaited_once_with(agent_id)


async def test_should_create_prompt_from_json_body(
    client: AsyncClient, prompt_service_mock: AsyncMock, auth_headers: dict[str, str]
) -> None:
    agent_id = uuid4()
    prompt = prompt_record(agent_id)
    prompt_service_mock.add_prompt.return_value = prompt

    response = await client.post(
        "/prompts",
        json={"agent_id": str(agent_id), "content": "Instructions"},
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["id"] == str(prompt.id)
    prompt_service_mock.add_prompt.assert_awaited_once_with(
        PromptCreate(agent_id=agent_id, content="Instructions")
    )


async def test_should_reject_invalid_prompt_body_before_service_call(
    client: AsyncClient, prompt_service_mock: AsyncMock, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/prompts",
        json={"agent_id": str(uuid4()), "content": ""},
        headers=auth_headers,
    )

    assert response.status_code == 422
    prompt_service_mock.add_prompt.assert_not_awaited()


@pytest.mark.parametrize("endpoint", ["by_id", "current", "create"])
async def test_should_map_missing_prompt_or_agent_to_not_found(
    client: AsyncClient,
    prompt_service_mock: AsyncMock,
    auth_headers: dict[str, str],
    endpoint: str,
) -> None:
    missing_id = uuid4()
    error = NotFoundError("Resource not found")
    if endpoint == "by_id":
        prompt_service_mock.get_prompt_by_id.side_effect = error
        response = await client.get(f"/prompts/{missing_id}", headers=auth_headers)
    elif endpoint == "current":
        prompt_service_mock.get_current_prompt_by_agent.side_effect = error
        response = await client.get(
            "/prompts/current",
            params={"agent_id": str(missing_id)},
            headers=auth_headers,
        )
    else:
        prompt_service_mock.add_prompt.side_effect = error
        response = await client.post(
            "/prompts",
            json={"agent_id": str(missing_id), "content": "Instructions"},
            headers=auth_headers,
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Resource not found"}


async def test_should_require_authentication_for_prompts(
    client: AsyncClient, prompt_service_mock: AsyncMock
) -> None:
    response = await client.get("/prompts", params={"agent_id": str(uuid4())})

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
    prompt_service_mock.get_prompts_by_agent.assert_not_awaited()
