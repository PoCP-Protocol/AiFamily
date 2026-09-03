"""Persist immutable metadata-only family-experience release bundles."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040_ai_experience_bundles"
down_revision: str | None = "0039_competitor_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_family_experience_release_bundles",
        sa.Column("bundle_id", sa.String(length=64), nullable=False),
        sa.Column("candidate_id", sa.String(length=256), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("use_case", sa.String(length=256), nullable=False),
        sa.Column("agent_id", sa.String(length=256), nullable=False),
        sa.Column("provider_id", sa.String(length=256), nullable=False),
        sa.Column("model", sa.String(length=256), nullable=False),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("prompt_ref", sa.String(length=256), nullable=False),
        sa.Column("prompt_version", sa.String(length=128), nullable=False),
        sa.Column("schema_ref", sa.String(length=256), nullable=False),
        sa.Column("schema_version", sa.String(length=128), nullable=False),
        sa.Column("safety_policy_version", sa.String(length=128), nullable=False),
        sa.Column("knowledge_refs", sa.JSON(), nullable=False),
        sa.Column("data_class", sa.String(length=64), nullable=False),
        sa.Column("report_ref", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("control_id", sa.String(length=64), nullable=False),
        sa.Column("approval_signature_ref", sa.String(length=64), nullable=False),
        sa.Column("approval_signature_algorithm", sa.String(length=64), nullable=False),
        sa.Column("approved_by", sa.String(length=256), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("asset_digest", sa.String(length=64), nullable=False),
        sa.Column("human_gate_rule", sa.String(length=32), nullable=False),
        sa.Column("draft_only", sa.Boolean(), nullable=False),
        sa.Column("may_mutate_business_state", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "data_class IN ('SYNTHETIC', 'OPERATIONAL_TEXT', "
            "'FAMILY_PRIVATE_TEXT', 'MINOR_PERSONAL_DATA')",
            name="ck_ai_family_experience_bundles_data_class",
        ),
        sa.CheckConstraint(
            "human_gate_rule = 'REVIEW_REQUIRED'",
            name="ck_ai_family_experience_bundles_human_gate",
        ),
        sa.CheckConstraint(
            "draft_only = true AND may_mutate_business_state = false",
            name="ck_ai_family_experience_bundles_draft_boundary",
        ),
        sa.PrimaryKeyConstraint("bundle_id"),
    )
    op.create_index(
        "uq_ai_family_experience_bundles_candidate_environment",
        "ai_family_experience_release_bundles",
        ["candidate_id", "environment"],
        unique=True,
    )
    op.create_index(
        "ix_ai_family_experience_bundles_control",
        "ai_family_experience_release_bundles",
        ["control_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_family_experience_bundles_control",
        table_name="ai_family_experience_release_bundles",
    )
    op.drop_index(
        "uq_ai_family_experience_bundles_candidate_environment",
        table_name="ai_family_experience_release_bundles",
    )
    op.drop_table("ai_family_experience_release_bundles")
