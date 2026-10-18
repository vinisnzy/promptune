import asyncio
import json
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from promptune.database.session import build_session_maker
from promptune.modules.agent_run.notification import (
    AGENT_RUN_CHANGED_CHANNEL,
    notify_agent_run_changed,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _asyncpg_dsn(database_url: str) -> str:
    url = make_url(database_url).set(drivername="postgresql")
    return url.render_as_string(hide_password=False)


async def test_notification_is_delivered_only_after_commit(
    engine: AsyncEngine, postgres_url: str
) -> None:
    notifications: asyncio.Queue[str] = asyncio.Queue()
    connection = await asyncpg.connect(_asyncpg_dsn(postgres_url))

    def receive_notification(
        _connection: asyncpg.Connection,
        _process_id: int,
        _channel: str,
        payload: str,
    ) -> None:
        notifications.put_nowait(payload)

    await connection.add_listener(AGENT_RUN_CHANGED_CHANNEL, receive_notification)
    maker = build_session_maker(engine)
    rolled_back_id = uuid4()
    committed_id = uuid4()

    try:
        async with maker() as session:
            await notify_agent_run_changed(session, rolled_back_id)
            await session.rollback()

        with pytest.raises(TimeoutError):
            await asyncio.wait_for(notifications.get(), timeout=0.1)

        async with maker() as session:
            await notify_agent_run_changed(session, committed_id)
            await session.commit()

        payload = await asyncio.wait_for(notifications.get(), timeout=2)
        assert json.loads(payload) == {"run_id": str(committed_id)}
    finally:
        await connection.remove_listener(
            AGENT_RUN_CHANGED_CHANNEL, receive_notification
        )
        await connection.close()
