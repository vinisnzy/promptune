from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from promptune.modules.session.model import SessionStatus


class SessionCreate(BaseModel):
    agent_id: UUID
    base_prompt_id: UUID


class SessionRead(BaseModel):
    id: UUID
    user_id: UUID
    agent_id: UUID
    base_prompt_id: UUID
    status: SessionStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
