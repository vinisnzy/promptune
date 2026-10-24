from datetime import UTC, datetime
from uuid import UUID, uuid4

from promptune.core.exceptions import ConflictError
from promptune.modules.agent_run.model import AgentRun, AgentRunStatus
from promptune.modules.agent_run.repository import IAgentRunRepository
from promptune.modules.session.model import SessionStatus
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

    async def claim_by_id(self, run_id: UUID, *, now: datetime) -> int | None:
        run = self.runs.get(run_id)
        conversation = self.sessions.sessions.get(run.session_id) if run else None
        if (
            run is None
            or run.status not in (AgentRunStatus.QUEUED, AgentRunStatus.PROCESSING)
            or conversation is None
            or conversation.status != SessionStatus.ACTIVE
            or conversation.deleted_at is not None
        ):
            return None
        run.status = AgentRunStatus.PROCESSING
        run.attempt_count += 1
        run.started_at = run.started_at or now
        run.finished_at = None
        run.error_code = None
        run.error_message = None
        return run.attempt_count

    async def get_for_processing(self, run_id: UUID) -> AgentRun | None:
        return self.runs.get(run_id)

    async def mark_completed(
        self,
        run_id: UUID,
        attempt_count: int,
        assistant_message_id: UUID,
        *,
        now: datetime,
    ) -> bool:
        run = self._owned(run_id, attempt_count)
        if run is None:
            return False
        run.assistant_message_id = assistant_message_id
        run.status = AgentRunStatus.COMPLETED
        run.error_code = None
        run.error_message = None
        run.finished_at = now
        return True

    async def mark_error(
        self,
        run_id: UUID,
        attempt_count: int,
        *,
        code: str,
        message: str,
        retry: bool,
        now: datetime,
    ) -> bool:
        run = self._owned(run_id, attempt_count)
        if run is None:
            return False
        run.error_code = code
        run.error_message = message
        run.status = AgentRunStatus.QUEUED if retry else AgentRunStatus.FAILED
        run.finished_at = None if retry else now
        return True

    async def mark_failed(
        self, run_id: UUID, *, code: str, message: str, now: datetime
    ) -> bool:
        run = self.runs.get(run_id)
        if run is None or run.status not in (
            AgentRunStatus.QUEUED,
            AgentRunStatus.PROCESSING,
        ):
            return False
        run.status = AgentRunStatus.FAILED
        run.error_code = code
        run.error_message = message
        run.finished_at = now
        return True

    def _owned(self, run_id: UUID, attempt_count: int) -> AgentRun | None:
        run = self.runs.get(run_id)
        if (
            run is None
            or run.status != AgentRunStatus.PROCESSING
            or run.attempt_count != attempt_count
        ):
            return None
        return run
