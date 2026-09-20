from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PromptCreate(BaseModel):
    agent_id: UUID
    description: Annotated[str, Field(min_length=1, max_length=200)]
    content: Annotated[str, Field(min_length=1)]


class PromptRead(BaseModel):
    id: UUID
    agent_id: UUID
    description: str
    content: str

    model_config = ConfigDict(from_attributes=True)
