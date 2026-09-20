from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    description: Annotated[str | None, Field(min_length=1, max_length=300)] = None
    context: Annotated[str | None, Field(min_length=1, max_length=300)] = None


class AgentRead(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    context: str | None = None

    model_config = ConfigDict(from_attributes=True)


class AgentUpdate(BaseModel):
    name: Annotated[str | None, Field(min_length=1, max_length=100)] = None
    description: Annotated[str | None, Field(min_length=1, max_length=300)] = None
    context: Annotated[str | None, Field(min_length=1, max_length=300)] = None
