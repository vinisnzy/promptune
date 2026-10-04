from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from promptune.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from promptune.modules.prompt_proposal.model import PromptProposal
    from promptune.modules.session.model import Session


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class Message(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant')",
            name="valid_role",
        ),
        CheckConstraint(
            "reply_to_id IS NULL OR reply_to_id <> id",
            name="not_self_reply",
        ),
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)
    questions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reply_to_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("messages.id"), nullable=True, index=True
    )
    base_proposal_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("prompt_proposals.id"), nullable=True, index=True
    )

    session: Mapped[Session] = relationship(back_populates="messages")
    reply_to: Mapped[Message | None] = relationship(
        remote_side="Message.id",
        foreign_keys=[reply_to_id],
        back_populates="replies",
    )
    replies: Mapped[list[Message]] = relationship(
        foreign_keys=[reply_to_id],
        back_populates="reply_to",
    )
    base_proposal: Mapped[PromptProposal | None] = relationship(
        foreign_keys=[base_proposal_id],
        back_populates="based_messages",
    )
    proposal: Mapped[PromptProposal | None] = relationship(
        foreign_keys="PromptProposal.message_id",
        back_populates="message",
        uselist=False,
    )
