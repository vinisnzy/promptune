import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from uuid import UUID

import asyncpg
from sqlalchemy.engine import make_url

from promptune.modules.agent_run.model import AgentRunStatus
from promptune.modules.agent_run.notification import AGENT_RUN_CHANGED_CHANNEL
from promptune.modules.agent_run.schema import AgentRunRead

RunLoader = Callable[[UUID, UUID], Awaitable[AgentRunRead]]
ConnectionFactory = Callable[[str], Awaitable[asyncpg.Connection]]

TERMINAL_STATUSES = {
    AgentRunStatus.COMPLETED,
    AgentRunStatus.FAILED,
    AgentRunStatus.CANCELED,
}


class AgentRunEventService:
    def __init__(
        self,
        database_url: str,
        run_loader: RunLoader,
        connection_factory: ConnectionFactory = asyncpg.connect,
    ) -> None:
        self.database_url = database_url
        self.run_loader = run_loader
        self.connection_factory = connection_factory

    async def get_snapshot(self, run_id: UUID, user_id: UUID) -> AgentRunRead:
        return await self.run_loader(run_id, user_id)

    async def stream_events(
        self, run_id: UUID, user_id: UUID
    ) -> AsyncIterator[str]:
        notifications: asyncio.Queue[str] = asyncio.Queue()
        connection = await self.connection_factory(_asyncpg_dsn(self.database_url))
        listener_added = False

        def receive_notification(
            _connection: asyncpg.Connection,
            _process_id: int,
            _channel: str,
            payload: str,
        ) -> None:
            notifications.put_nowait(payload)

        try:
            await connection.add_listener(
                AGENT_RUN_CHANGED_CHANNEL, receive_notification
            )
            listener_added = True
            snapshot = await self.get_snapshot(run_id, user_id)
            yield format_sse_event("run.updated", snapshot.model_dump(mode="json"))

            while snapshot.status not in TERMINAL_STATUSES:
                payload = await notifications.get()
                if not _matches_run(payload, run_id):
                    continue
                snapshot = await self.get_snapshot(run_id, user_id)
                yield format_sse_event(
                    "run.updated", snapshot.model_dump(mode="json")
                )
        finally:
            try:
                if listener_added:
                    await connection.remove_listener(
                        AGENT_RUN_CHANGED_CHANNEL, receive_notification
                    )
            finally:
                await connection.close()


def format_sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _asyncpg_dsn(database_url: str) -> str:
    url = make_url(database_url).set(drivername="postgresql")
    return url.render_as_string(hide_password=False)


def _matches_run(payload: str, run_id: UUID) -> bool:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return False
    return isinstance(data, dict) and data.get("run_id") == str(run_id)
