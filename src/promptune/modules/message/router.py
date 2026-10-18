from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from promptune.database.session import get_async_session
from promptune.modules.agent_run.repository import AgentRunRepository
from promptune.modules.agent_run.schema import AgentRunSummary, MessageAccepted
from promptune.modules.auth.dependencies import CurrentUser, get_current_user
from promptune.modules.message.repository import MessageRepository
from promptune.modules.message.schema import MessageRead, MessageSend
from promptune.modules.message.service import MessageService
from promptune.modules.session.repository import SessionRepository

router = APIRouter(
    prefix="/sessions/{session_id}/messages",
    tags=["Messages"],
    dependencies=[Depends(get_current_user)],
)


async def get_message_service(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AsyncIterator[MessageService]:
    try:
        yield MessageService(
            MessageRepository(session),
            SessionRepository(session),
            AgentRunRepository(session),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise


@router.get("", response_model=list[MessageRead])
async def list_messages(
    session_id: UUID,
    current_user: CurrentUser,
    service: Annotated[MessageService, Depends(get_message_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1)] = 20,
) -> list[MessageRead]:
    messages = await service.list_messages(session_id, current_user.id, page, size)
    return [MessageRead.model_validate(item) for item in messages]


@router.get("/{message_id}", response_model=MessageRead)
async def get_message(
    session_id: UUID,
    message_id: UUID,
    current_user: CurrentUser,
    service: Annotated[MessageService, Depends(get_message_service)],
) -> MessageRead:
    message = await service.get_message_by_id(
        message_id, session_id, current_user.id
    )
    return MessageRead.model_validate(message)


@router.post("", response_model=MessageAccepted, status_code=status.HTTP_202_ACCEPTED)
async def send_message(
    session_id: UUID,
    data: MessageSend,
    response: Response,
    current_user: CurrentUser,
    service: Annotated[MessageService, Depends(get_message_service)],
) -> MessageAccepted:
    dispatch = await service.send_message(session_id, current_user.id, data)
    response.headers["Location"] = f"/agent-runs/{dispatch.run.id}"
    return MessageAccepted(
        message_id=dispatch.message.id,
        run=AgentRunSummary.model_validate(dispatch.run),
    )
