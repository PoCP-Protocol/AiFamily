"""Persist auditable Context Engine observations and immutable snapshots.

Revision ID: 0037_ops_audit
Revises: 0010_experience_run_interactions
Create Date: 2026-09-02

These tables are technical AI-runtime projections.  They preserve the exact
tenant, family, subject, consent, purpose, locale, provenance, retention and
deletion envelope used to construct a model context.  They do not create or
promote a family fact.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037_ops_audit"
down_revision: str | None = "0010_experience_run_interactions"
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
        "ix_ai_context_observations_family_id",
        "ai_context_observations",
        ["family_id"],
    )
    op.create_index(
        "ix_ai_context_observations_subject_id",
        "ai_context_observations",
        ["subject_id"],
    )
    op.create_index(
        "ix_ai_context_observations_purpose",
        "ai_context_observations",
        ["purpose"],
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
        "ix_ai_context_snapshots_tenant_id",
        "ai_context_snapshots",
        ["tenant_id"],
    )
    op.create_index(
        "ix_ai_context_snapshots_family_id",
        "ai_context_snapshots",
        ["family_id"],
    )

    op.create_table(
        "ai_context_snapshot_observations",
        sa.Column("snapshot_ref", sa.String(length=256), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("observation_id", sa.String(length=256), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("snapshot_ref", "tenant_id", "observation_id", "position"),
    )


def downgrade() -> None:
    op.drop_table("ai_context_snapshot_observations")
    op.drop_index("ix_ai_context_snapshots_family_id", table_name="ai_context_snapshots")
    op.drop_index("ix_ai_context_snapshots_tenant_id", table_name="ai_context_snapshots")
    op.drop_table("ai_context_snapshots")
    op.drop_index("ix_ai_context_observations_purpose", table_name="ai_context_observations")
    op.drop_index("ix_ai_context_observations_subject_id", table_name="ai_context_observations")
    op.drop_index("ix_ai_context_observations_family_id", table_name="ai_context_observations")
    op.drop_table("ai_context_observations")
