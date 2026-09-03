"""Persist durable, scoped Context Engine observations and snapshots."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036_ai_context_engine"
down_revision: str | None = "0035_ai_benchmark_report_slices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_context_observations",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("observation_id", sa.String(length=256), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("subject_id", sa.String(length=128), nullable=False),
        sa.Column("dimension", sa.String(length=128), nullable=False),
        sa.Column("observed_value", sa.Text(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.String(length=256), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retention_policy", sa.String(length=128), nullable=False),
        sa.Column("region_id", sa.String(length=16), nullable=False),
        sa.Column("locale", sa.String(length=32), nullable=False),
        sa.Column("data_class", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=128), nullable=False),
        sa.Column("consent_version", sa.String(length=128), nullable=False),
        sa.Column("consent_granted", sa.Boolean(), nullable=False),
        sa.Column("deletion_ref", sa.String(length=256), nullable=False),
        sa.Column("correlation_id", sa.String(length=256), nullable=False),
        sa.Column("causation_id", sa.String(length=256), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "observation_id"),
    )
    op.create_index(
        "ix_ai_context_observations_family",
        "ai_context_observations",
        ["tenant_id", "family_id", "subject_id"],
    )
    op.create_index(
        "ix_ai_context_observations_purpose",
        "ai_context_observations",
        ["tenant_id", "purpose", "consent_version", "expires_at"],
    )

    op.create_table(
        "ai_context_snapshots",
        sa.Column("snapshot_ref", sa.String(length=256), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("region_id", sa.String(length=16), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("subject_ids", sa.JSON(), nullable=False),
        sa.Column("purpose", sa.String(length=128), nullable=False),
        sa.Column("consent_version", sa.String(length=128), nullable=False),
        sa.Column("data_class", sa.String(length=64), nullable=False),
        sa.Column("locale", sa.String(length=32), nullable=False),
        sa.Column("content_locale", sa.String(length=32), nullable=True),
        sa.Column("model_locale", sa.String(length=32), nullable=True),
        sa.Column("policy_locale", sa.String(length=32), nullable=True),
        sa.Column("consent_granted", sa.Boolean(), nullable=False),
        sa.Column("correlation_id", sa.String(length=256), nullable=False),
        sa.Column("causation_id", sa.String(length=256), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provenance", sa.String(length=256), nullable=False),
        sa.Column("deletion_ref", sa.String(length=256), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("snapshot_ref"),
    )
    op.create_index(
        "ix_ai_context_snapshots_scope",
        "ai_context_snapshots",
        ["tenant_id", "family_id", "expires_at"],
    )

    op.create_table(
        "ai_context_snapshot_observations",
        sa.Column("snapshot_ref", sa.String(length=256), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("observation_id", sa.String(length=256), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint(
            "snapshot_ref", "tenant_id", "observation_id", "position"
        ),
    )


def downgrade() -> None:
    op.drop_table("ai_context_snapshot_observations")
    op.drop_index(
        "ix_ai_context_snapshots_scope", table_name="ai_context_snapshots"
    )
    op.drop_table("ai_context_snapshots")
    op.drop_index(
        "ix_ai_context_observations_purpose",
        table_name="ai_context_observations",
    )
    op.drop_index(
        "ix_ai_context_observations_family",
        table_name="ai_context_observations",
    )
    op.drop_table("ai_context_observations")
