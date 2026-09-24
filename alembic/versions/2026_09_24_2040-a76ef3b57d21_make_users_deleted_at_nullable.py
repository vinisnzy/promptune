"""make users deleted_at nullable

Revision ID: a76ef3b57d21
Revises: ec08c05a2068
Create Date: 2026-09-24 20:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a76ef3b57d21"
down_revision: str | Sequence[str] | None = "ec08c05a2068"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "deleted_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "deleted_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
