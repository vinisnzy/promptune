"""create revisions table

Revision ID: b7f46c2d9e31
Revises: e5d620b8c15e

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7f46c2d9e31"
down_revision: str | Sequence[str] | None = "e5d620b8c15e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "revisions",
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("source_prompt_id", sa.Uuid(), nullable=False),
        sa.Column("change_request", sa.Text(), nullable=False),
        sa.Column("proposed_content", sa.Text(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("questions", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("approved_prompt_id", sa.Uuid(), nullable=True),
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
            "status IN ('pending', 'approved', 'discarded')",
            name=op.f("ck_revisions_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["agents.id"], name=op.f("fk_revisions_agent_id_agents")
        ),
        sa.ForeignKeyConstraint(
            ["source_prompt_id"],
            ["prompts.id"],
            name=op.f("fk_revisions_source_prompt_id_prompts"),
        ),
        sa.ForeignKeyConstraint(
            ["approved_prompt_id"],
            ["prompts.id"],
            name=op.f("fk_revisions_approved_prompt_id_prompts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_revisions")),
    )
    op.create_index(op.f("ix_revisions_agent_id"), "revisions", ["agent_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_revisions_agent_id"), table_name="revisions")
    op.drop_table("revisions")
