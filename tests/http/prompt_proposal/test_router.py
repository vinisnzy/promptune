from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from promptune.core.exceptions import ConflictError
from promptune.modules.prompt_proposal.schema import PromptProposalCreate


def prompt_proposal_record(
    source_prompt_id: UUID, agent_id: UUID
) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        agent_id=agent_id,
        source_prompt_id=source_prompt_id,
        change_request="Simplificar",
        proposed_content="# Original",
        proposed_description="Descrição sugerida",
        summary=["Simulação"],
        questions=[],
        warnings=["Sem IA"],
        status="pending",
        approved_prompt_id=None,
        created_at=now,
        updated_at=now,
    )


async def test_create_and_get_prompt_proposal(
    client: AsyncClient,
    prompt_proposal_service_mock: AsyncMock,
    auth_headers: dict[str, str],
) -> None:
    source_id = uuid4()
    prompt_proposal = prompt_proposal_record(source_id, uuid4())
    prompt_proposal_service_mock.create.return_value = prompt_proposal
    prompt_proposal_service_mock.get_by_id.return_value = prompt_proposal

    created = await client.post(
        "/prompt-proposals",
        json={"source_prompt_id": str(source_id), "change_request": "Simplificar"},
        headers=auth_headers,
    )
    fetched = await client.get(
        f"/prompt-proposals/{prompt_proposal.id}", headers=auth_headers
    )

    assert created.status_code == 201
    assert created.json()["source_prompt_id"] == str(source_id)
    assert created.json()["status"] == "pending"
    assert created.json()["proposed_description"] == "Descrição sugerida"
    assert fetched.status_code == 200
    assert fetched.json()["proposed_description"] == "Descrição sugerida"
    prompt_proposal_service_mock.create.assert_awaited_once_with(
        PromptProposalCreate(
            source_prompt_id=source_id, change_request="Simplificar"
        )
    )


async def test_list_approve_and_discard_prompt_proposal(
    client: AsyncClient,
    prompt_proposal_service_mock: AsyncMock,
    auth_headers: dict[str, str],
) -> None:
    agent_id = uuid4()
    prompt_proposal = prompt_proposal_record(uuid4(), agent_id)
    prompt_proposal_service_mock.list_by_agent.return_value = [prompt_proposal]
    prompt_proposal_service_mock.approve.return_value = prompt_proposal
    prompt_proposal_service_mock.discard.return_value = prompt_proposal

    listed = await client.get(
        "/prompt-proposals",
        params={"agent_id": str(agent_id), "page": 2, "size": 5},
        headers=auth_headers,
    )
    approved = await client.post(
        f"/prompt-proposals/{prompt_proposal.id}/approve", headers=auth_headers
    )
    discarded = await client.post(
        f"/prompt-proposals/{prompt_proposal.id}/discard", headers=auth_headers
    )

    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["proposed_description"] == "Descrição sugerida"
    assert approved.status_code == 200
    assert approved.json()["proposed_description"] == "Descrição sugerida"
    assert discarded.status_code == 200
    prompt_proposal_service_mock.list_by_agent.assert_awaited_once_with(
        agent_id, 2, 5
    )
    prompt_proposal_service_mock.approve.assert_awaited_once_with(prompt_proposal.id)
    prompt_proposal_service_mock.discard.assert_awaited_once_with(prompt_proposal.id)


@pytest.mark.parametrize(
    "method,path,json_body",
    [
        ("POST", "/prompt-proposals", {"change_request": "Alterar"}),
        ("GET", "/prompt-proposals", None),
        ("GET", "/prompt-proposals/not-a-uuid", None),
    ],
)
async def test_invalid_prompt_proposal_requests(
    client: AsyncClient,
    prompt_proposal_service_mock: AsyncMock,
    auth_headers: dict[str, str],
    method: str,
    path: str,
    json_body: dict[str, str] | None,
) -> None:
    response = await client.request(method, path, json=json_body, headers=auth_headers)
    assert response.status_code == 422
    prompt_proposal_service_mock.create.assert_not_awaited()


async def test_prompt_proposal_requires_authentication(
    client: AsyncClient, prompt_proposal_service_mock: AsyncMock
) -> None:
    response = await client.get(f"/prompt-proposals/{uuid4()}")
    assert response.status_code == 401
    prompt_proposal_service_mock.get_by_id.assert_not_awaited()


async def test_finalized_prompt_proposal_returns_conflict(
    client: AsyncClient,
    prompt_proposal_service_mock: AsyncMock,
    auth_headers: dict[str, str],
) -> None:
    prompt_proposal_service_mock.approve.side_effect = ConflictError(
        "Prompt proposal is already finalized"
    )
    response = await client.post(
        f"/prompt-proposals/{uuid4()}/approve", headers=auth_headers
    )
    assert response.status_code == 409
