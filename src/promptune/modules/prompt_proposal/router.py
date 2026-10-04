from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from langchain.chat_models import init_chat_model
from sqlalchemy.ext.asyncio import AsyncSession

from promptune.agents.prompt_editor.agent import PromptEditorAgent
from promptune.core.config import Settings, get_settings
from promptune.database.session import get_async_session
from promptune.modules.agent.repository import AgentRepository
from promptune.modules.auth.dependencies import get_current_user
from promptune.modules.prompt.repository import PromptRepository
from promptune.modules.prompt_proposal.repository import PromptProposalRepository
from promptune.modules.prompt_proposal.schema import (
    PromptProposalCreate,
    PromptProposalRead,
)
from promptune.modules.prompt_proposal.service import PromptProposalService

router = APIRouter(
    prefix="/prompt-proposals",
    tags=["Prompt proposals"],
    dependencies=[Depends(get_current_user)],
)


def get_prompt_editor_agent(settings: Annotated[Settings, Depends(get_settings)]):
    model = init_chat_model(
        model=settings.llm_model,
        model_provider=settings.llm_provider,
        api_key=settings.groq_api_key,
    )
    return PromptEditorAgent(model)


def get_prompt_proposal_service(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    prompt_editor_agent: Annotated[
        PromptEditorAgent, Depends(get_prompt_editor_agent)
    ],
) -> PromptProposalService:
    return PromptProposalService(
        repository=PromptProposalRepository(session),
        prompt_repository=PromptRepository(session),
        agent_repository=AgentRepository(session),
        prompt_editor_agent=prompt_editor_agent,
    )


@router.get("", response_model=list[PromptProposalRead])
async def list_prompt_proposals(
    agent_id: UUID,
    service: Annotated[
        PromptProposalService, Depends(get_prompt_proposal_service)
    ],
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1)] = 20,
) -> list[PromptProposalRead]:
    prompt_proposals = await service.list_by_agent(agent_id, page, size)
    return [
        PromptProposalRead.model_validate(prompt_proposal)
        for prompt_proposal in prompt_proposals
    ]


@router.get("/{prompt_proposal_id}", response_model=PromptProposalRead)
async def get_prompt_proposal(
    prompt_proposal_id: UUID,
    service: Annotated[
        PromptProposalService, Depends(get_prompt_proposal_service)
    ],
) -> PromptProposalRead:
    return PromptProposalRead.model_validate(
        await service.get_by_id(prompt_proposal_id)
    )


@router.post(
    "", response_model=PromptProposalRead, status_code=status.HTTP_201_CREATED
)
async def create_prompt_proposal(
    data: PromptProposalCreate,
    service: Annotated[
        PromptProposalService, Depends(get_prompt_proposal_service)
    ],
) -> PromptProposalRead:
    return PromptProposalRead.model_validate(await service.create(data))


@router.post("/{prompt_proposal_id}/approve", response_model=PromptProposalRead)
async def approve_prompt_proposal(
    prompt_proposal_id: UUID,
    service: Annotated[
        PromptProposalService, Depends(get_prompt_proposal_service)
    ],
) -> PromptProposalRead:
    return PromptProposalRead.model_validate(
        await service.approve(prompt_proposal_id)
    )


@router.post("/{prompt_proposal_id}/discard", response_model=PromptProposalRead)
async def discard_prompt_proposal(
    prompt_proposal_id: UUID,
    service: Annotated[
        PromptProposalService, Depends(get_prompt_proposal_service)
    ],
) -> PromptProposalRead:
    return PromptProposalRead.model_validate(
        await service.discard(prompt_proposal_id)
    )
