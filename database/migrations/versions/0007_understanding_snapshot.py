"""Persist immutable server-owned family understanding draft snapshots.

Revision ID: 0007_understanding_snapshot
Revises: 0006_understanding_scope_binding
Create Date: 2026-09-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_understanding_snapshot"
down_revision: str | None = "0006_understanding_scope_binding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "family_understanding_draft_snapshots"


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column("understanding_snapshot_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.tenant_id"),
            nullable=False,
        ),
        sa.Column(
            "family_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("families.family_id"),
            nullable=False,
        ),
        sa.Column("understanding_run_ref", sa.String(length=256), nullable=False),
        sa.Column("artifact_ref", sa.String(length=256), nullable=False),
        sa.Column("artifact_version", sa.Integer(), nullable=False),
        sa.Column("prior_artifact_ref", sa.String(length=256), nullable=True),
        sa.Column("provenance_ref", sa.String(length=256), nullable=False),
        sa.Column(
            "subject_person_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("persons.person_id"),
            nullable=False,
        ),
        sa.Column("desired_change", sa.Text(), nullable=False),
        sa.Column("need_type", sa.String(length=64), nullable=False),
        sa.Column("required_capability_keys", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("evidence_refs", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("source_refs", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("knowledge_refs", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("provider_id", sa.String(length=128), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=128), nullable=False),
        sa.Column("schema_version", sa.String(length=128), nullable=False),
        sa.Column("context_snapshot_ref", sa.String(length=256), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_ref", sa.String(length=256), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "family_id",
            "artifact_ref",
            "artifact_version",
            "provenance_ref",
            name="uq_understanding_snapshot_binding",
        ),
        sa.CheckConstraint("artifact_version > 0", name="ck_understanding_snapshot_version"),
        sa.CheckConstraint(
            "status IN ('DRAFT','REVOKED','EXPIRED')",
            name="ck_understanding_snapshot_status",
        ),
        sa.CheckConstraint(
            "(status = 'REVOKED' AND revoked_at IS NOT NULL AND revocation_ref IS NOT NULL) OR "
            "(status <> 'REVOKED' AND revoked_at IS NULL AND revocation_ref IS NULL)",
            name="ck_understanding_snapshot_revocation",
        ),
        sa.CheckConstraint(
            "CARDINALITY(required_capability_keys) > 0 AND CARDINALITY(evidence_refs) > 0 "
            "AND CARDINALITY(source_refs) > 0 AND CARDINALITY(knowledge_refs) > 0",
            name="ck_understanding_snapshot_nonempty_refs",
        ),
        sa.CheckConstraint(
            "BTRIM(understanding_run_ref) <> '' AND BTRIM(artifact_ref) <> '' "
            "AND BTRIM(provenance_ref) <> '' AND BTRIM(context_snapshot_ref) <> ''",
            name="ck_understanding_snapshot_required_refs",
        ),
    )
    op.create_index(
        "idx_understanding_snapshot_reader",
        TABLE_NAME,
        ["tenant_id", "family_id", "artifact_ref", "artifact_version", "provenance_ref"],
    )
    op.create_index(
        "idx_understanding_snapshot_run",
        TABLE_NAME,
        ["tenant_id", "family_id", "understanding_run_ref", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_understanding_snapshot_run", table_name=TABLE_NAME)
    op.drop_index("idx_understanding_snapshot_reader", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
