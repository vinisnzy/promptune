from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from promptune.database.session import get_async_session
from promptune.modules.auth.dependencies import CurrentUser, get_current_user
from promptune.modules.session.model import SessionStatus
from promptune.modules.session.repository import SessionRepository
from promptune.modules.session.schema import SessionCreate, SessionRead
from promptune.modules.session.service import SessionService

router = APIRouter(
    prefix="/sessions",
    tags=["Sessions"],
    dependencies=[Depends(get_current_user)],
)


async def get_session_service(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AsyncIterator[SessionService]:
    try:
        yield SessionService(SessionRepository(session))
        await session.commit()
    except Exception:
        await session.rollback()
        raise


@router.get("", response_model=list[SessionRead])
async def list_sessions(
    current_user: CurrentUser,
    service: Annotated[SessionService, Depends(get_session_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1)] = 20,
    agent_id: UUID | None = None,
    status_filter: Annotated[SessionStatus | None, Query(alias="status")] = None,
) -> list[SessionRead]:
    sessions = await service.list_sessions(
        current_user.id,
        page,
        size,
        agent_id=agent_id,
        status=status_filter,
    )
    return [SessionRead.model_validate(item) for item in sessions]


@router.get("/{session_id}", response_model=SessionRead)
async def get_session(
    session_id: UUID,
    current_user: CurrentUser,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> SessionRead:
    conversation = await service.get_session_by_id(session_id, current_user.id)
    return SessionRead.model_validate(conversation)


@router.post("", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(
    data: SessionCreate,
    current_user: CurrentUser,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> SessionRead:
    conversation = await service.create_session(current_user.id, data)
    return SessionRead.model_validate(conversation)


@router.post("/{session_id}/complete", response_model=SessionRead)
async def complete_session(
    session_id: UUID,
    current_user: CurrentUser,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> SessionRead:
    conversation = await service.complete_session(session_id, current_user.id)
    return SessionRead.model_validate(conversation)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: UUID,
    current_user: CurrentUser,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> Response:
    await service.delete_session(session_id, current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
