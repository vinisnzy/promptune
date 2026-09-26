from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from promptune.core.exceptions import NotFoundError
from promptune.schemas.agent import AgentCreate, AgentUpdate


def agent_record(name: str = "Assistant") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(), name=name, description="Helps users", context="Support"
    )


async def test_should_list_agents_with_default_pagination(
    client: AsyncClient, agent_service_mock: AsyncMock, auth_headers: dict[str, str]
) -> None:
    agent = agent_record()
    agent_service_mock.get_all_agents.return_value = [agent]

    response = await client.get("/agents", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(agent.id),
            "name": "Assistant",
            "description": "Helps users",
            "context": "Support",
        }
    ]
    agent_service_mock.get_all_agents.assert_awaited_once_with(1, 20, None)


async def test_should_pass_agent_search_and_pagination_to_service(
    client: AsyncClient, agent_service_mock: AsyncMock, auth_headers: dict[str, str]
) -> None:
    agent_service_mock.get_all_agents.return_value = []

    response = await client.get(
        "/agents", params={"page": 2, "size": 5, "q": "billing"}, headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json() == []
    agent_service_mock.get_all_agents.assert_awaited_once_with(2, 5, "billing")


@pytest.mark.parametrize("params", [{"page": 0}, {"size": 0}])
async def test_should_reject_invalid_agent_pagination_before_service_call(
    client: AsyncClient,
    agent_service_mock: AsyncMock,
    auth_headers: dict[str, str],
    params: dict[str, int],
) -> None:
    response = await client.get("/agents", params=params, headers=auth_headers)

    assert response.status_code == 422
    agent_service_mock.get_all_agents.assert_not_awaited()


async def test_should_get_agent_by_uuid(
    client: AsyncClient, agent_service_mock: AsyncMock, auth_headers: dict[str, str]
) -> None:
    agent = agent_record()
    agent_service_mock.get_agent_by_id.return_value = agent

    response = await client.get(f"/agents/{agent.id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == str(agent.id)
    agent_service_mock.get_agent_by_id.assert_awaited_once_with(agent.id)


async def test_should_reject_invalid_agent_uuid_before_service_call(
    client: AsyncClient, agent_service_mock: AsyncMock, auth_headers: dict[str, str]
) -> None:
    response = await client.get("/agents/not-a-uuid", headers=auth_headers)

    assert response.status_code == 422
    agent_service_mock.get_agent_by_id.assert_not_awaited()


async def test_should_create_agent_from_json_body(
    client: AsyncClient, agent_service_mock: AsyncMock, auth_headers: dict[str, str]
) -> None:
    agent = agent_record()
    agent_service_mock.add_agent.return_value = agent

    response = await client.post(
        "/agents",
        json={"name": "Assistant", "description": "Helps users", "context": "Support"},
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["id"] == str(agent.id)
    agent_service_mock.add_agent.assert_awaited_once_with(
        AgentCreate(name="Assistant", description="Helps users", context="Support")
    )


async def test_should_reject_invalid_agent_body_before_service_call(
    client: AsyncClient, agent_service_mock: AsyncMock, auth_headers: dict[str, str]
) -> None:
    response = await client.post("/agents", json={"name": ""}, headers=auth_headers)

    assert response.status_code == 422
    agent_service_mock.add_agent.assert_not_awaited()


async def test_should_update_agent_with_supplied_fields(
    client: AsyncClient, agent_service_mock: AsyncMock, auth_headers: dict[str, str]
) -> None:
    agent = agent_record("Renamed")
    agent_service_mock.update_agent.return_value = agent

    response = await client.patch(
        f"/agents/{agent.id}", json={"name": "Renamed"}, headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"
    agent_service_mock.update_agent.assert_awaited_once_with(
        agent.id, AgentUpdate(name="Renamed")
    )


async def test_should_delete_agent_with_no_content_response(
    client: AsyncClient, agent_service_mock: AsyncMock, auth_headers: dict[str, str]
) -> None:
    agent_id = uuid4()

    response = await client.delete(f"/agents/{agent_id}", headers=auth_headers)

    assert response.status_code == 204
    assert response.content == b""
    agent_service_mock.delete_agent.assert_awaited_once_with(agent_id)


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
async def test_should_map_missing_agent_to_not_found(
    client: AsyncClient,
    agent_service_mock: AsyncMock,
    auth_headers: dict[str, str],
    method: str,
) -> None:
    agent_id = uuid4()
    error = NotFoundError(f"Agent not found with id: {agent_id}")
    if method == "get":
        agent_service_mock.get_agent_by_id.side_effect = error
        response = await client.get(f"/agents/{agent_id}", headers=auth_headers)
    elif method == "patch":
        agent_service_mock.update_agent.side_effect = error
        response = await client.patch(
            f"/agents/{agent_id}", json={"name": "Renamed"}, headers=auth_headers
        )
    else:
        agent_service_mock.delete_agent.side_effect = error
        response = await client.delete(f"/agents/{agent_id}", headers=auth_headers)

    assert response.status_code == 404
    assert response.json() == {"detail": str(error)}


async def test_should_require_authentication_for_agents(
    client: AsyncClient, agent_service_mock: AsyncMock
) -> None:
    response = await client.get("/agents")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
    agent_service_mock.get_all_agents.assert_not_awaited()
