from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from promptune.database.session import get_async_session
from promptune.modules.agent_run.event_stream import AgentRunEventService
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


def get_agent_run_event_service(request: Request) -> AgentRunEventService:
    async def load_run(run_id: UUID, user_id: UUID) -> AgentRunRead:
        async with request.app.state.session_maker() as session:
            service = AgentRunService(AgentRunRepository(session))
            return serialize_agent_run(await service.get_run(run_id, user_id))

    return AgentRunEventService(
        request.app.state.settings.database_url,
        load_run,
    )


@router.get("/{run_id}", response_model=AgentRunRead)
async def get_agent_run(
    run_id: UUID,
    current_user: CurrentUser,
    service: Annotated[AgentRunService, Depends(get_agent_run_service)],
) -> AgentRunRead:
    return serialize_agent_run(await service.get_run(run_id, current_user.id))


@router.get("/{run_id}/events")
async def stream_agent_run_events(
    run_id: UUID,
    current_user: CurrentUser,
    event_service: Annotated[
        AgentRunEventService, Depends(get_agent_run_event_service)
    ],
) -> StreamingResponse:
    await event_service.get_snapshot(run_id, current_user.id)
    return StreamingResponse(
        event_service.stream_events(run_id, current_user.id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
