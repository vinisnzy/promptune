from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from promptune.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from promptune.modules.agent.model import Agent
    from promptune.modules.auth.models.user import User
    from promptune.modules.message.model import Message
    from promptune.modules.prompt.model import Prompt


class SessionStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"


class Session(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'completed')",
            name="valid_status",
        ),
    )

    base_prompt_id: Mapped[UUID] = mapped_column(
        ForeignKey("prompts.id"), nullable=False, index=True
    )
    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agents.id"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SessionStatus.ACTIVE
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    base_prompt: Mapped[Prompt] = relationship()
    agent: Mapped[Agent] = relationship()
    user: Mapped[User] = relationship()
    messages: Mapped[list[Message]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
