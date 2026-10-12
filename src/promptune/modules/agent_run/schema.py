from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from promptune.modules.agent_run.model import AgentRunStatus


class AgentRunSummary(BaseModel):
    id: UUID
    status: AgentRunStatus

    model_config = ConfigDict(from_attributes=True)


class MessageAccepted(BaseModel):
    message_id: UUID
    run: AgentRunSummary


class AgentRunError(BaseModel):
    code: str
    message: str


class AgentRunRead(BaseModel):
    id: UUID
    session_id: UUID
    status: AgentRunStatus
    user_message_id: UUID
    assistant_message_id: UUID | None
    proposal_id: UUID | None
    attempt_count: int
    error: AgentRunError | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
