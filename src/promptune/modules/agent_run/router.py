from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from promptune.database.session import get_async_session
from promptune.modules.agent_run.repository import AgentRunRepository
from promptune.modules.agent_run.schema import AgentRunRead
from promptune.modules.agent_run.service import AgentRunService, serialize_agent_run
from promptune.modules.auth.dependencies import CurrentUser, get_current_user

router = APIRouter(
    prefix="/agent-runs",
    tags=["Agent runs"],
    dependencies=[Depends(get_current_user)],
)


def get_agent_run_service(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AgentRunService:
    return AgentRunService(AgentRunRepository(session))


@router.get("/{run_id}", response_model=AgentRunRead)
async def get_agent_run(
    run_id: UUID,
    current_user: CurrentUser,
    service: Annotated[AgentRunService, Depends(get_agent_run_service)],
) -> AgentRunRead:
    return serialize_agent_run(await service.get_run(run_id, current_user.id))
