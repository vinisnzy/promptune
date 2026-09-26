from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from promptune.models.revision import RevisionStatus


class RevisionCreate(BaseModel):
    source_prompt_id: UUID
    change_request: Annotated[str, Field(min_length=1)]


class RevisionDraft(BaseModel):
    proposed_content: str
    proposed_description: Annotated[str, Field(min_length=1, max_length=200)]
    summary: list[str]
    questions: list[str]
    warnings: list[str]


class RevisionRead(BaseModel):
    id: UUID
    agent_id: UUID
    source_prompt_id: UUID
    change_request: str
    proposed_content: str
    proposed_description: str
    summary: list[str]
    questions: list[str]
    warnings: list[str]
    status: RevisionStatus
    approved_prompt_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
