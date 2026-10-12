"""create agent runs

Revision ID: a4c82d71f9b3
Revises: 3f9b1e7d4a62
Create Date: 2026-10-12 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4c82d71f9b3"
down_revision: str | Sequence[str] | None = "3f9b1e7d4a62"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("user_message_id", sa.Uuid(), nullable=False),
        sa.Column("assistant_message_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("error_message", sa.String(length=300), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name=op.f("ck_agent_runs_non_negative_attempt_count"),
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'failed', 'canceled')",
            name=op.f("ck_agent_runs_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["assistant_message_id"],
            ["messages.id"],
            name=op.f("fk_agent_runs_assistant_message_id_messages"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name=op.f("fk_agent_runs_session_id_sessions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_message_id"],
            ["messages.id"],
            name=op.f("fk_agent_runs_user_message_id_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_runs")),
        sa.UniqueConstraint(
            "assistant_message_id",
            name=op.f("uq_agent_runs_assistant_message_id"),
        ),
        sa.UniqueConstraint(
            "user_message_id", name=op.f("uq_agent_runs_user_message_id")
        ),
    )
    op.create_index(
        op.f("ix_agent_runs_lease_expires_at"),
        "agent_runs",
        ["lease_expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_runs_session_id"),
        "agent_runs",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_runs_status"), "agent_runs", ["status"], unique=False
    )
    op.create_index(
        "uq_agent_runs_active_session",
        "agent_runs",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'processing')"),
    )
    op.alter_column(
        "prompt_proposals", "message_id", existing_type=sa.Uuid(), nullable=False
    )


def downgrade() -> None:
    op.alter_column(
        "prompt_proposals", "message_id", existing_type=sa.Uuid(), nullable=True
    )
    op.drop_index("uq_agent_runs_active_session", table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_status"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_session_id"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_lease_expires_at"), table_name="agent_runs")
    op.drop_table("agent_runs")
