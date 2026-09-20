from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from promptune.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from promptune.models import Prompt


class Agent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agents"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    context: Mapped[str] = mapped_column(String(300), nullable=False)
    prompts: Mapped[list[Prompt]] = relationship(back_populates="agent")
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=None
    )
