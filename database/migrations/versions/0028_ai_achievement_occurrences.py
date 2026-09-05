"""Allow evidence-bound AI achievements to repeat by stable occurrence.

Revision ID: 0028_ai_achievement_occurrences
Revises: 0027_experience_outbox_dead_letters
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_ai_achievement_occurrences"
down_revision: str | None = "0027_experience_outbox_dead_letters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_achievement_projections",
        sa.Column("occurrence_id", sa.String(length=256), nullable=True),
    )
    op.execute(
        "UPDATE ai_achievement_projections SET occurrence_id = 'default' "
        "WHERE occurrence_id IS NULL"
    )
    op.alter_column(
        "ai_achievement_projections",
        "occurrence_id",
        existing_type=sa.String(length=256),
        nullable=False,
        server_default="default",
    )
    op.drop_constraint(
        "uq_ai_achievement_scope_key",
        "ai_achievement_projections",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_ai_achievement_scope_key",
        "ai_achievement_projections",
        ["scope_fingerprint", "achievement_key", "occurrence_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_ai_achievement_scope_key",
        "ai_achievement_projections",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_ai_achievement_scope_key",
        "ai_achievement_projections",
        ["scope_fingerprint", "achievement_key"],
    )
    op.drop_column("ai_achievement_projections", "occurrence_id")
