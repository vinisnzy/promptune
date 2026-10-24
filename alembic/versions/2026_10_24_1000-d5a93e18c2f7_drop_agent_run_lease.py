"""drop agent run lease

Revision ID: d5a93e18c2f7
Revises: a4c82d71f9b3
Create Date: 2026-10-24 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d5a93e18c2f7"
down_revision: str | Sequence[str] | None = "a4c82d71f9b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(op.f("ix_agent_runs_lease_expires_at"), table_name="agent_runs")
    op.drop_column("agent_runs", "lease_token")
    op.drop_column("agent_runs", "lease_expires_at")


def downgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("agent_runs", sa.Column("lease_token", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_agent_runs_lease_expires_at"),
        "agent_runs",
        ["lease_expires_at"],
        unique=False,
    )
