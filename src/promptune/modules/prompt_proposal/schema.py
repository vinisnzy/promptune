from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from promptune.modules.prompt_proposal.model import PromptProposalStatus


class PromptProposalRead(BaseModel):
    id: UUID
    message_id: UUID
    agent_id: UUID
    source_prompt_id: UUID
    change_request: str
    proposed_content: str
    proposed_description: str
    summary: list[str]
    questions: list[str]
    warnings: list[str]
    status: PromptProposalStatus
    approved_prompt_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
