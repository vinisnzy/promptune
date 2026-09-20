from uuid import UUID

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from promptune.models import Agent
from promptune.models.base import Base, TimestampMixin, UUIDMixin


class Prompt(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "prompts"
    __table_args__ = (UniqueConstraint("agent_id", "version"),)

    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agents.id"), nullable=False, index=True
    )
    agent: Mapped[Agent] = relationship(back_populates="prompts")
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
