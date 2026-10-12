from datetime import UTC, datetime
from uuid import UUID, uuid4

from promptune.core.exceptions import ConflictError
from promptune.modules.agent_run.model import AgentRun, AgentRunStatus
from promptune.modules.agent_run.repository import IAgentRunRepository
from tests.unit.session.in_memory_repository import InMemorySessionRepository


class InMemoryAgentRunRepository(IAgentRunRepository):
    def __init__(self, sessions: InMemorySessionRepository) -> None:
        self.sessions = sessions
        self.runs: dict[UUID, AgentRun] = {}

    async def create(self, *, session_id: UUID, user_message_id: UUID) -> AgentRun:
        if await self.has_active_for_session(session_id):
            raise ConflictError("Session already has an active agent run")
        now = datetime.now(UTC)
        run = AgentRun(
            id=uuid4(),
            session_id=session_id,
            user_message_id=user_message_id,
            assistant_message_id=None,
            status=AgentRunStatus.QUEUED,
            attempt_count=0,
            error_code=None,
            error_message=None,
            started_at=None,
            finished_at=None,
            lease_expires_at=None,
            lease_token=None,
            created_at=now,
            updated_at=now,
        )
        self.runs[run.id] = run
        return run

    async def get_by_id(self, run_id: UUID, user_id: UUID) -> AgentRun | None:
        run = self.runs.get(run_id)
        if (
            run is None
            or await self.sessions.get_by_id(run.session_id, user_id) is None
        ):
            return None
        return run

    async def has_active_for_session(self, session_id: UUID) -> bool:
        return any(
            run.session_id == session_id
            and run.status in (AgentRunStatus.QUEUED, AgentRunStatus.PROCESSING)
            for run in self.runs.values()
        )
