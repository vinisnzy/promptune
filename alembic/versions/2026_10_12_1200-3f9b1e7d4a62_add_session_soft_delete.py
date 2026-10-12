"""add session soft delete

Revision ID: 3f9b1e7d4a62
Revises: 7146e7ac2e53
Create Date: 2026-10-12 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "3f9b1e7d4a62"
down_revision: str | Sequence[str] | None = "7146e7ac2e53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sessions", "deleted_at")
