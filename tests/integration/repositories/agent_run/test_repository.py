from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from promptune.database.session import build_session_maker
from promptune.modules.agent_run.model import AgentRunStatus
from promptune.modules.agent_run.repository import AgentRunRepository
from tests.integration.repositories.agent_run.test_processor import enqueue_run

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_claim_by_id_increments_attempt_and_accepts_processing(
    engine: AsyncEngine,
) -> None:
    owner_id, _, _, run_id = await enqueue_run(engine)
    maker = build_session_maker(engine)
    now = datetime.now(UTC)
    async with maker() as session:
        assert await AgentRunRepository(session).claim_by_id(run_id, now=now) == 1
        await session.commit()
    async with maker() as session:
        assert await AgentRunRepository(session).claim_by_id(run_id, now=now) == 2
        await session.commit()
    async with maker() as session:
        run = await AgentRunRepository(session).get_by_id(run_id, owner_id)
        assert run.status == AgentRunStatus.PROCESSING
        assert run.attempt_count == 2
        assert run.started_at is not None


async def test_claim_by_id_ignores_unknown_and_terminal_runs(
    engine: AsyncEngine,
) -> None:
    _, _, _, run_id = await enqueue_run(engine)
    maker = build_session_maker(engine)
    now = datetime.now(UTC)
    async with maker() as session:
        repository = AgentRunRepository(session)
        assert await repository.claim_by_id(uuid4(), now=now) is None
        assert await repository.claim_by_id(run_id, now=now) == 1
        assert await repository.mark_error(
            run_id, 1, code="x", message="y", retry=False, now=now
        )
        assert await repository.claim_by_id(run_id, now=now) is None
        await session.commit()


async def test_fencing_rejects_transitions_from_stale_attempt(
    engine: AsyncEngine,
) -> None:
    owner_id, _, _, run_id = await enqueue_run(engine)
    maker = build_session_maker(engine)
    now = datetime.now(UTC)
    async with maker() as session:
        repository = AgentRunRepository(session)
        await repository.claim_by_id(run_id, now=now)
        await repository.claim_by_id(run_id, now=now)
        assert not await repository.mark_error(
            run_id, 1, code="x", message="y", retry=True, now=now
        )
        assert not await repository.mark_completed(run_id, 1, uuid4(), now=now)
        await session.commit()
    async with maker() as session:
        run = await AgentRunRepository(session).get_by_id(run_id, owner_id)
        assert run.status == AgentRunStatus.PROCESSING
        assert run.error_code is None
