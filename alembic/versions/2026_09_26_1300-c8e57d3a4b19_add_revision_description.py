"""add proposed description to revisions

Revision ID: c8e57d3a4b19
Revises: b7f46c2d9e31

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c8e57d3a4b19"
down_revision: str | Sequence[str] | None = "b7f46c2d9e31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "revisions",
        sa.Column("proposed_description", sa.String(length=200), nullable=True),
    )
    op.execute(
        "UPDATE revisions SET proposed_description = prompts.description "
        "FROM prompts WHERE revisions.source_prompt_id = prompts.id"
    )
    op.alter_column("revisions", "proposed_description", nullable=False)


def downgrade() -> None:
    op.drop_column("revisions", "proposed_description")
