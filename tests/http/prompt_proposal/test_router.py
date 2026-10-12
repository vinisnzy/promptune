from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from promptune.core.exceptions import ConflictError


def prompt_proposal_record(agent_id: UUID) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        message_id=uuid4(),
        agent_id=agent_id,
        source_prompt_id=uuid4(),
        change_request="Simplificar",
        proposed_content="# Original",
        proposed_description="Descrição sugerida",
        summary=["Saudação simplificada"],
        questions=[],
        warnings=[],
        status="pending",
        approved_prompt_id=None,
        created_at=now,
        updated_at=now,
    )


async def test_list_get_approve_and_discard_owned_prompt_proposal(
    client: AsyncClient,
    prompt_proposal_service_mock: AsyncMock,
    auth_service_mock: AsyncMock,
    auth_headers: dict[str, str],
) -> None:
    user_id = auth_service_mock.get_user_from_access_token.return_value.id
    agent_id = uuid4()
    proposal = prompt_proposal_record(agent_id)
    prompt_proposal_service_mock.list_by_agent.return_value = [proposal]
    prompt_proposal_service_mock.get_by_id.return_value = proposal
    prompt_proposal_service_mock.approve.return_value = proposal
    prompt_proposal_service_mock.discard.return_value = proposal

    listed = await client.get(
        "/prompt-proposals",
        params={"agent_id": str(agent_id), "page": 2, "size": 5},
        headers=auth_headers,
    )
    fetched = await client.get(f"/prompt-proposals/{proposal.id}", headers=auth_headers)
    approved = await client.post(
        f"/prompt-proposals/{proposal.id}/approve", headers=auth_headers
    )
    discarded = await client.post(
        f"/prompt-proposals/{proposal.id}/discard", headers=auth_headers
    )

    assert listed.status_code == fetched.status_code == 200
    assert approved.status_code == discarded.status_code == 200
    assert fetched.json()["message_id"] == str(proposal.message_id)
    prompt_proposal_service_mock.list_by_agent.assert_awaited_once_with(
        agent_id, user_id, 2, 5
    )
    prompt_proposal_service_mock.get_by_id.assert_awaited_once_with(
        proposal.id, user_id
    )
    prompt_proposal_service_mock.approve.assert_awaited_once_with(proposal.id, user_id)
    prompt_proposal_service_mock.discard.assert_awaited_once_with(proposal.id, user_id)


async def test_legacy_prompt_proposal_creation_is_disabled(
    client: AsyncClient,
    prompt_proposal_service_mock: AsyncMock,
    auth_headers: dict[str, str],
) -> None:
    response = await client.post(
        "/prompt-proposals",
        json={"source_prompt_id": str(uuid4()), "change_request": "Simplificar"},
        headers=auth_headers,
    )
    assert response.status_code == 405
    prompt_proposal_service_mock.assert_not_awaited()


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


@pytest.mark.parametrize(
    "path",
    ["/prompt-proposals", "/prompt-proposals/not-a-uuid"],
)
async def test_invalid_prompt_proposal_requests(
    client: AsyncClient,
    prompt_proposal_service_mock: AsyncMock,
    auth_headers: dict[str, str],
    path: str,
) -> None:
    response = await client.get(path, headers=auth_headers)
    assert response.status_code == 422
    prompt_proposal_service_mock.get_by_id.assert_not_awaited()
