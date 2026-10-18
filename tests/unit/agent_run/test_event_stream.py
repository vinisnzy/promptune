import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest

from promptune.modules.agent_run.event_stream import AgentRunEventService
from promptune.modules.agent_run.notification import AGENT_RUN_CHANGED_CHANNEL
from promptune.modules.agent_run.schema import AgentRunRead

NotificationCallback = Callable[[asyncpg.Connection, int, str, str], Any]


class FakeNotificationConnection:
    def __init__(self) -> None:
        self.callback: NotificationCallback | None = None
        self.removed = False
        self.closed = False

    async def add_listener(
        self, channel: str, callback: NotificationCallback
    ) -> None:
        assert channel == AGENT_RUN_CHANGED_CHANNEL
        self.callback = callback

    async def remove_listener(
        self, channel: str, callback: NotificationCallback
    ) -> None:
        assert channel == AGENT_RUN_CHANGED_CHANNEL
        assert callback is self.callback
        self.removed = True

    async def close(self) -> None:
        self.closed = True

    def notify(self, run_id: UUID) -> None:
        assert self.callback is not None
        self.callback(
            self, 1, AGENT_RUN_CHANGED_CHANNEL, json.dumps({"run_id": str(run_id)})
        )


def run_snapshot(run_id: UUID, status: str) -> AgentRunRead:
    now = datetime.now(UTC)
    terminal = status in {"completed", "failed", "canceled"}
    return AgentRunRead(
        id=run_id,
        session_id=uuid4(),
        status=status,
        user_message_id=uuid4(),
        assistant_message_id=uuid4() if status == "completed" else None,
        proposal_id=None,
        attempt_count=1,
        error=None,
        created_at=now,
        started_at=now if status != "queued" else None,
        finished_at=now if terminal else None,
    )


def event_data(event: str) -> dict[str, Any]:
    return json.loads(event.split("data: ", maxsplit=1)[1])


async def build_service(
    snapshots: list[AgentRunRead], connection: FakeNotificationConnection
) -> AgentRunEventService:
    remaining = iter(snapshots)

    async def load_run(_run_id: UUID, _user_id: UUID) -> AgentRunRead:
        return next(remaining)

    async def connect(_dsn: str) -> asyncpg.Connection:
        return connection  # type: ignore[return-value]

    return AgentRunEventService(
        "postgresql+asyncpg://user:password@localhost/database",
        load_run,
        connect,
    )


async def test_should_stream_initial_and_notified_states_until_completion() -> None:
    run_id = uuid4()
    other_run_id = uuid4()
    connection = FakeNotificationConnection()
    service = await build_service(
        [
            run_snapshot(run_id, "queued"),
            run_snapshot(run_id, "processing"),
            run_snapshot(run_id, "completed"),
        ],
        connection,
    )
    events = service.stream_events(run_id, uuid4())

    initial = await anext(events)
    connection.notify(other_run_id)
    connection.notify(run_id)
    processing = await anext(events)
    connection.notify(run_id)
    completed = await anext(events)

    assert initial.startswith("event: run.updated\n")
    assert [
        event_data(initial)["status"],
        event_data(processing)["status"],
        event_data(completed)["status"],
    ] == ["queued", "processing", "completed"]
    with pytest.raises(StopAsyncIteration):
        await anext(events)
    assert connection.removed
    assert connection.closed


async def test_should_close_listener_after_initial_failed_state() -> None:
    run_id = uuid4()
    connection = FakeNotificationConnection()
    service = await build_service(
        [run_snapshot(run_id, "failed")],
        connection,
    )
    events = service.stream_events(run_id, uuid4())

    failed = await anext(events)

    assert event_data(failed)["status"] == "failed"
    with pytest.raises(StopAsyncIteration):
        await anext(events)
    assert connection.removed
    assert connection.closed


async def test_should_close_listener_when_stream_is_cancelled() -> None:
    run_id = uuid4()
    connection = FakeNotificationConnection()
    service = await build_service(
        [run_snapshot(run_id, "processing")],
        connection,
    )
    events = service.stream_events(run_id, uuid4())
    await anext(events)
    waiting: asyncio.Task[str] = asyncio.create_task(anext(events))

    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting

    assert connection.removed
    assert connection.closed
