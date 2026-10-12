from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from promptune.database.session import get_async_session
from promptune.modules.auth.dependencies import CurrentUser, get_current_user
from promptune.modules.prompt_proposal.repository import PromptProposalRepository
from promptune.modules.prompt_proposal.schema import PromptProposalRead
from promptune.modules.prompt_proposal.service import PromptProposalService

router = APIRouter(
    prefix="/prompt-proposals",
    tags=["Prompt proposals"],
    dependencies=[Depends(get_current_user)],
)


async def get_prompt_proposal_service(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AsyncIterator[PromptProposalService]:
    try:
        yield PromptProposalService(PromptProposalRepository(session))
        await session.commit()
    except Exception:
        await session.rollback()
        raise


@router.get("", response_model=list[PromptProposalRead])
async def list_prompt_proposals(
    agent_id: UUID,
    current_user: CurrentUser,
    service: Annotated[PromptProposalService, Depends(get_prompt_proposal_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1)] = 20,
) -> list[PromptProposalRead]:
    proposals = await service.list_by_agent(agent_id, current_user.id, page, size)
    return [PromptProposalRead.model_validate(item) for item in proposals]


@router.get("/{prompt_proposal_id}", response_model=PromptProposalRead)
async def get_prompt_proposal(
    prompt_proposal_id: UUID,
    current_user: CurrentUser,
    service: Annotated[PromptProposalService, Depends(get_prompt_proposal_service)],
) -> PromptProposalRead:
    return PromptProposalRead.model_validate(
        await service.get_by_id(prompt_proposal_id, current_user.id)
    )


@router.post("/{prompt_proposal_id}/approve", response_model=PromptProposalRead)
async def approve_prompt_proposal(
    prompt_proposal_id: UUID,
    current_user: CurrentUser,
    service: Annotated[PromptProposalService, Depends(get_prompt_proposal_service)],
) -> PromptProposalRead:
    return PromptProposalRead.model_validate(
        await service.approve(prompt_proposal_id, current_user.id)
    )


@router.post("/{prompt_proposal_id}/discard", response_model=PromptProposalRead)
async def discard_prompt_proposal(
    prompt_proposal_id: UUID,
    current_user: CurrentUser,
    service: Annotated[PromptProposalService, Depends(get_prompt_proposal_service)],
) -> PromptProposalRead:
    return PromptProposalRead.model_validate(
        await service.discard(prompt_proposal_id, current_user.id)
    )
