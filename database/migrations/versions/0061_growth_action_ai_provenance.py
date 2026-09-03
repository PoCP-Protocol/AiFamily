"""Bind AI-originated GrowthAction rows to reviewed draft provenance.

Revision ID: 0061_growth_action_ai_provenance
Revises: 0060_product_improvement_candidates
Create Date: 2026-09-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0061_growth_action_ai_provenance"
down_revision: str | None = "0060_product_improvement_candidates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "growth_actions",
        sa.Column("source_draft_id", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "growth_actions",
        sa.Column("source_draft_digest", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "growth_actions",
        sa.Column("source_provenance_ref", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "growth_actions",
        sa.Column("source_consent_version", sa.String(length=160), nullable=True),
    )
    op.create_check_constraint(
        "ck_growth_actions_ai_source_complete",
        "growth_actions",
        "(action_type <> 'AI_PLAN_DAILY_PRACTICE') OR "
        "(source_draft_id IS NOT NULL AND source_draft_digest IS NOT NULL "
        "AND source_provenance_ref IS NOT NULL AND source_consent_version IS NOT NULL)",
    )
    op.create_index(
        "ix_growth_actions_source_draft",
        "growth_actions",
        ["family_id", "source_draft_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_growth_actions_source_draft", table_name="growth_actions")
    op.drop_constraint(
        "ck_growth_actions_ai_source_complete",
        "growth_actions",
        type_="check",
    )
    op.drop_column("growth_actions", "source_consent_version")
    op.drop_column("growth_actions", "source_provenance_ref")
    op.drop_column("growth_actions", "source_draft_digest")
    op.drop_column("growth_actions", "source_draft_id")
