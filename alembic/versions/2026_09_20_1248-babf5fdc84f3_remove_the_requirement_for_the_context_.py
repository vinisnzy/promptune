"""remove the requirement for the context and description fields in the agents table

Revision ID: babf5fdc84f3
Revises: 4a766043c591
Create Date: 2026-09-20 12:48:53.408398

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "babf5fdc84f3"
down_revision: str | Sequence[str] | None = "4a766043c591"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "agents", "description", existing_type=sa.String(length=300), nullable=True
    )
    op.alter_column(
        "agents", "context", existing_type=sa.String(length=300), nullable=True
    )


def downgrade() -> None:
    op.execute(sa.text("UPDATE agents SET description = '' WHERE description IS NULL"))
    op.execute(sa.text("UPDATE agents SET context = '' WHERE context IS NULL"))
    op.alter_column(
        "agents", "description", existing_type=sa.String(length=300), nullable=False
    )
    op.alter_column(
        "agents", "context", existing_type=sa.String(length=300), nullable=False
    )
