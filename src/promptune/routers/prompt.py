from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from promptune.database.session import get_async_session
from promptune.repositories.prompt import PromptRepository
from promptune.schemas.prompt import PromptCreate, PromptRead
from promptune.services.prompt import PromptService

router = APIRouter(prefix="/prompts", tags=["prompts"])


def get_prompt_service(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> PromptService:
    return PromptService(PromptRepository(session))


@router.get("", response_model=list[PromptRead])
async def list_prompts(
    agent_id: UUID,
    service: Annotated[PromptService, Depends(get_prompt_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1)] = 20,
) -> list[PromptRead]:
    prompts = await service.get_prompts_by_agent(agent_id, page, size)
    return [PromptRead.model_validate(prompt) for prompt in prompts]


@router.get("/current", response_model=PromptRead)
async def get_current_prompt(
    agent_id: UUID,
    service: Annotated[PromptService, Depends(get_prompt_service)],
) -> PromptRead:
    return PromptRead.model_validate(
        await service.get_current_prompt_by_agent(agent_id)
    )


@router.get("/{prompt_id}", response_model=PromptRead)
async def get_prompt(
    prompt_id: UUID,
    service: Annotated[PromptService, Depends(get_prompt_service)],
) -> PromptRead:
    return PromptRead.model_validate(await service.get_prompt_by_id(prompt_id))


@router.post("", response_model=PromptRead, status_code=status.HTTP_201_CREATED)
async def create_prompt(
    data: PromptCreate,
    service: Annotated[PromptService, Depends(get_prompt_service)],
) -> PromptRead:
    return PromptRead.model_validate(await service.add_prompt(data))
