"""Persist evidence-bound achievement read-model projections.

Revision ID: 0015_ai_achievement_projections
Revises: 0014_tool_action_outbox
Create Date: 2026-08-30

The table is a derived AI experience projection only.  It intentionally has
no score, rank, streak, family-total, or reward-balance columns.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_ai_achievement_projections"
down_revision: str | None = "0014_tool_action_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_type = postgresql.JSONB()
    op.create_table(
        "ai_achievement_projections",
        sa.Column("achievement_id", sa.String(length=256), nullable=False),
        sa.Column("achievement_key", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("region_id", sa.String(length=16), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("subject_ids", json_type, nullable=False),
        sa.Column("purpose", sa.String(length=128), nullable=False),
        sa.Column("consent_version", sa.String(length=128), nullable=False),
        sa.Column("scope_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("scope_payload", json_type, nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("evidence_refs", json_type, nullable=False),
        sa.Column("provenance_payload", json_type, nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("stable_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("earned_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("achievement_id"),
        sa.UniqueConstraint(
            "scope_fingerprint",
            "achievement_key",
            name="uq_ai_achievement_scope_key",
        ),
    )
    op.create_index(
        "ix_ai_achievement_scope_lookup",
        "ai_achievement_projections",
        ["tenant_id", "family_id", "scope_fingerprint", "earned_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_achievement_scope_lookup",
        table_name="ai_achievement_projections",
    )
    op.drop_table("ai_achievement_projections")
