from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from promptune.database.session import get_async_session
from promptune.dependencies.auth import get_current_user
from promptune.repositories.agent import AgentRepository
from promptune.schemas.agent import AgentCreate, AgentRead, AgentUpdate
from promptune.services.agent import AgentService

router = APIRouter(
    prefix="/agents", tags=["Agents"], dependencies=[Depends(get_current_user)]
)


def get_agent_service(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AgentService:
    return AgentService(AgentRepository(session))


@router.get("", response_model=list[AgentRead])
async def list_agents(
    service: Annotated[AgentService, Depends(get_agent_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1)] = 20,
    q: str | None = None,
) -> list[AgentRead]:
    agents = await service.get_all_agents(page, size, q)
    return [AgentRead.model_validate(agent) for agent in agents]


@router.get("/{agent_id}", response_model=AgentRead)
async def get_agent(
    agent_id: UUID,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> AgentRead:
    return AgentRead.model_validate(await service.get_agent_by_id(agent_id))


@router.post("", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
async def create_agent(
    data: AgentCreate,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> AgentRead:
    return AgentRead.model_validate(await service.add_agent(data))


@router.patch("/{agent_id}", response_model=AgentRead)
async def update_agent(
    agent_id: UUID,
    data: AgentUpdate,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> AgentRead:
    return AgentRead.model_validate(await service.update_agent(agent_id, data))


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: UUID,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> Response:
    await service.delete_agent(agent_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
