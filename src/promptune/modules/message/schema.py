from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from promptune.modules.message.model import MessageRole


class MessageSend(BaseModel):
    content: Annotated[str, Field(min_length=1)]
    base_proposal_id: UUID | None = None


class MessageRead(BaseModel):
    id: UUID
    session_id: UUID
    role: MessageRole
    content: str
    questions: list[str]
    warnings: list[str]
    reply_to_id: UUID | None
    base_proposal_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
