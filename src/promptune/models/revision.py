from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from promptune.models.base import Base, TimestampMixin, UUIDMixin


class RevisionStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DISCARDED = "discarded"


class Revision(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "revisions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'discarded')",
            name="valid_status",
        ),
    )

    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), index=True)
    source_prompt_id: Mapped[UUID] = mapped_column(ForeignKey("prompts.id"))
    change_request: Mapped[str] = mapped_column(Text)
    proposed_content: Mapped[str] = mapped_column(Text)
    proposed_description: Mapped[str] = mapped_column(String(200))
    summary: Mapped[list[str]] = mapped_column(JSON)
    questions: Mapped[list[str]] = mapped_column(JSON)
    warnings: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default=RevisionStatus.PENDING)
    approved_prompt_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("prompts.id"), nullable=True
    )
