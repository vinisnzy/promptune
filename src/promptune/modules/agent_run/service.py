from uuid import UUID

from promptune.core.exceptions import NotFoundError
from promptune.modules.agent_run.model import AgentRun
from promptune.modules.agent_run.repository import IAgentRunRepository
from promptune.modules.agent_run.schema import AgentRunError, AgentRunRead


class AgentRunService:
    def __init__(self, repository: IAgentRunRepository) -> None:
        self.repository = repository

    async def get_run(self, run_id: UUID, user_id: UUID) -> AgentRun:
        run = await self.repository.get_by_id(run_id, user_id)
        if run is None:
            raise NotFoundError(f"Agent run not found with id: {run_id}")
        return run


def serialize_agent_run(run: AgentRun) -> AgentRunRead:
    proposal_id = None
    if run.assistant_message is not None and run.assistant_message.proposal is not None:
        proposal_id = run.assistant_message.proposal.id
    error = None
    if run.error_code is not None and run.error_message is not None:
        error = AgentRunError(code=run.error_code, message=run.error_message)
    return AgentRunRead(
        id=run.id,
        session_id=run.session_id,
        status=run.status,
        user_message_id=run.user_message_id,
        assistant_message_id=run.assistant_message_id,
        proposal_id=proposal_id,
        attempt_count=run.attempt_count,
        error=error,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )
