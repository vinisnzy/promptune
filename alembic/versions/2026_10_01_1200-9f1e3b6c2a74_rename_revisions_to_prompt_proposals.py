"""rename revisions to prompt proposals

Revision ID: 9f1e3b6c2a74
Revises: c8e57d3a4b19

"""

from collections.abc import Sequence

from alembic import op

revision: str = "9f1e3b6c2a74"
down_revision: str | Sequence[str] | None = "c8e57d3a4b19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.rename_table("revisions", "prompt_proposals")
    op.execute(
        "ALTER TABLE prompt_proposals "
        "RENAME CONSTRAINT pk_revisions TO pk_prompt_proposals"
    )
    op.execute(
        "ALTER TABLE prompt_proposals "
        "RENAME CONSTRAINT ck_revisions_valid_status "
        "TO ck_prompt_proposals_valid_status"
    )
    op.execute(
        "ALTER TABLE prompt_proposals "
        "RENAME CONSTRAINT fk_revisions_agent_id_agents "
        "TO fk_prompt_proposals_agent_id_agents"
    )
    op.execute(
        "ALTER TABLE prompt_proposals "
        "RENAME CONSTRAINT fk_revisions_source_prompt_id_prompts "
        "TO fk_prompt_proposals_source_prompt_id_prompts"
    )
    op.execute(
        "ALTER TABLE prompt_proposals "
        "RENAME CONSTRAINT fk_revisions_approved_prompt_id_prompts "
        "TO fk_prompt_proposals_approved_prompt_id_prompts"
    )
    op.execute(
        "ALTER INDEX ix_revisions_agent_id "
        "RENAME TO ix_prompt_proposals_agent_id"
    )


def downgrade() -> None:
    op.execute(
        "ALTER INDEX ix_prompt_proposals_agent_id "
        "RENAME TO ix_revisions_agent_id"
    )
    op.execute(
        "ALTER TABLE prompt_proposals "
        "RENAME CONSTRAINT fk_prompt_proposals_approved_prompt_id_prompts "
        "TO fk_revisions_approved_prompt_id_prompts"
    )
    op.execute(
        "ALTER TABLE prompt_proposals "
        "RENAME CONSTRAINT fk_prompt_proposals_source_prompt_id_prompts "
        "TO fk_revisions_source_prompt_id_prompts"
    )
    op.execute(
        "ALTER TABLE prompt_proposals "
        "RENAME CONSTRAINT fk_prompt_proposals_agent_id_agents "
        "TO fk_revisions_agent_id_agents"
    )
    op.execute(
        "ALTER TABLE prompt_proposals "
        "RENAME CONSTRAINT ck_prompt_proposals_valid_status "
        "TO ck_revisions_valid_status"
    )
    op.execute(
        "ALTER TABLE prompt_proposals "
        "RENAME CONSTRAINT pk_prompt_proposals TO pk_revisions"
    )
    op.rename_table("prompt_proposals", "revisions")
