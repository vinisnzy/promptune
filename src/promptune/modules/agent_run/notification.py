import json
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

AGENT_RUN_CHANGED_CHANNEL = "agent_run_changed"


async def notify_agent_run_changed(session: AsyncSession, run_id: UUID) -> None:
    payload = json.dumps({"run_id": str(run_id)})
    await session.execute(
        select(func.pg_notify(AGENT_RUN_CHANGED_CHANNEL, payload))
    )
