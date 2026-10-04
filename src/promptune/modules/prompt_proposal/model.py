from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from promptune.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from promptune.modules.message.model import Message


class PromptProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DISCARDED = "discarded"


class PromptProposal(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "prompt_proposals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'discarded')",
            name="valid_status",
        ),
    )

    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), index=True)
    source_prompt_id: Mapped[UUID] = mapped_column(ForeignKey("prompts.id"))
    message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("messages.id"), nullable=True, unique=True
    )
    change_request: Mapped[str] = mapped_column(Text)
    proposed_content: Mapped[str] = mapped_column(Text)
    proposed_description: Mapped[str] = mapped_column(String(200))
    summary: Mapped[list[str]] = mapped_column(JSON)
    # Compatibility with the existing proposal endpoint until it creates messages.
    questions: Mapped[list[str]] = mapped_column(JSON)
    warnings: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(
        String(20), default=PromptProposalStatus.PENDING
    )
    approved_prompt_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("prompts.id"), nullable=True
    )

    message: Mapped[Message | None] = relationship(
        foreign_keys=[message_id],
        back_populates="proposal",
    )
    based_messages: Mapped[list[Message]] = relationship(
        foreign_keys="Message.base_proposal_id",
        back_populates="base_proposal",
    )
