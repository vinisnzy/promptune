from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from promptune.database.session import get_async_session
from promptune.dependencies.auth import get_current_user
from promptune.repositories.agent import AgentRepository
from promptune.repositories.prompt import PromptRepository
from promptune.repositories.revision import RevisionRepository
from promptune.schemas.revision import RevisionCreate, RevisionRead
from promptune.services.revision import RevisionService
from promptune.services.revision_generator import FakeRevisionGenerator

router = APIRouter(
    prefix="/revisions", tags=["Revisions"], dependencies=[Depends(get_current_user)]
)


def get_revision_service(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> RevisionService:
    return RevisionService(
        repository=RevisionRepository(session),
        prompt_repository=PromptRepository(session),
        agent_repository=AgentRepository(session),
        generator=FakeRevisionGenerator(),
    )


@router.get("", response_model=list[RevisionRead])
async def list_revisions(
    agent_id: UUID,
    service: Annotated[RevisionService, Depends(get_revision_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1)] = 20,
) -> list[RevisionRead]:
    revisions = await service.list_by_agent(agent_id, page, size)
    return [RevisionRead.model_validate(revision) for revision in revisions]


@router.get("/{revision_id}", response_model=RevisionRead)
async def get_revision(
    revision_id: UUID,
    service: Annotated[RevisionService, Depends(get_revision_service)],
) -> RevisionRead:
    return RevisionRead.model_validate(await service.get_by_id(revision_id))


@router.post("", response_model=RevisionRead, status_code=status.HTTP_201_CREATED)
async def create_revision(
    data: RevisionCreate,
    service: Annotated[RevisionService, Depends(get_revision_service)],
) -> RevisionRead:
    return RevisionRead.model_validate(await service.create(data))


@router.post("/{revision_id}/approve", response_model=RevisionRead)
async def approve_revision(
    revision_id: UUID,
    service: Annotated[RevisionService, Depends(get_revision_service)],
) -> RevisionRead:
    return RevisionRead.model_validate(await service.approve(revision_id))


@router.post("/{revision_id}/discard", response_model=RevisionRead)
async def discard_revision(
    revision_id: UUID,
    service: Annotated[RevisionService, Depends(get_revision_service)],
) -> RevisionRead:
    return RevisionRead.model_validate(await service.discard(revision_id))
