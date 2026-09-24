from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from promptune.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from promptune.models.refresh_token import RefreshToken


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(back_populates="user")
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
