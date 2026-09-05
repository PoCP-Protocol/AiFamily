"""Persist metadata-only family-experience canary assessments."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041_ai_canary_assessments"
down_revision: str | None = "0040_ai_experience_bundles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_family_experience_canary_assessments",
        sa.Column("assessment_id", sa.String(length=64), nullable=False),
        sa.Column("health", sa.String(length=32), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("observation_id", sa.String(length=256), nullable=False),
        sa.Column("receipt_id", sa.String(length=64), nullable=False),
        sa.Column("candidate_id", sa.String(length=256), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("error_rate", sa.Float(), nullable=False),
        sa.Column("p95_latency_ms", sa.Integer(), nullable=True),
        sa.Column("safety_violation_count", sa.Integer(), nullable=False),
        sa.Column("minor_safety_violation_count", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "health IN ('INSUFFICIENT_DATA', 'HEALTHY', 'BREACHED')",
            name="ck_ai_family_experience_canary_health",
        ),
        sa.PrimaryKeyConstraint("assessment_id"),
    )
    op.create_index(
        "uq_ai_family_experience_canary_observation_policy",
        "ai_family_experience_canary_assessments",
        ["observation_id", "policy_version"],
        unique=True,
    )
    op.create_index(
        "ix_ai_family_experience_canary_candidate_environment",
        "ai_family_experience_canary_assessments",
        ["candidate_id", "environment", "evaluated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_family_experience_canary_candidate_environment",
        table_name="ai_family_experience_canary_assessments",
    )
    op.drop_index(
        "uq_ai_family_experience_canary_observation_policy",
        table_name="ai_family_experience_canary_assessments",
    )
    op.drop_table("ai_family_experience_canary_assessments")
