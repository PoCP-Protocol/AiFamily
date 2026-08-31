"""Persist the exact Model Gateway draft a guardian reviewed.

Revision ID: 0005_reviewed_signal
Revises: 0004_ai_run_ledger
Create Date: 2026-09-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_reviewed_signal"
down_revision: str | None = "0004_ai_run_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "assessment_reviewed_understanding_signals"


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column("reviewed_signal_id", postgresql.UUID(as_uuid=True), primary_key=True),
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
        sa.Column(
            "assessment_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("family_assessment_sessions.assessment_session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("signal_ref", sa.String(length=256), nullable=False),
        sa.Column("signal_version", sa.Integer(), nullable=False),
        sa.Column("scope_ref", sa.String(length=256), nullable=False),
        sa.Column("reviewed_draft_ref", sa.String(length=256), nullable=False),
        sa.Column("draft_version", sa.Integer(), nullable=False),
        sa.Column("provenance_ref", sa.String(length=256), nullable=False),
        sa.Column("draft_source", sa.String(length=32), nullable=False),
        sa.Column("output_schema_ref", sa.String(length=256), nullable=False),
        sa.Column("view_event_ref", sa.String(length=256), nullable=False),
        sa.Column("human_gate_receipt_ref", sa.String(length=256), nullable=False),
        sa.Column("effective_status", sa.String(length=16), nullable=False),
        sa.Column(
            "reviewed_by_actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("persons.person_id"),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_ref", sa.String(length=256), nullable=True),
        sa.Column(
            "subject_person_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("persons.person_id"),
            nullable=False,
        ),
        sa.Column("need_type", sa.String(length=64), nullable=False),
        sa.Column("goal_text", sa.Text(), nullable=False),
        sa.Column(
            "required_capability_keys",
            postgresql.ARRAY(sa.String()),
            nullable=False,
        ),
        sa.Column("evidence_refs", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "family_id",
            "human_gate_receipt_ref",
            name="uq_reviewed_understanding_gate_receipt",
        ),
        sa.CheckConstraint("signal_version > 0", name="ck_reviewed_understanding_signal_version"),
        sa.CheckConstraint("draft_version > 0", name="ck_reviewed_understanding_draft_version"),
        sa.CheckConstraint(
            "effective_status IN ('EFFECTIVE', 'REVOKED', 'EXPIRED')",
            name="ck_reviewed_understanding_effective_status",
        ),
        sa.CheckConstraint(
            "draft_source = 'MODEL_GATEWAY'",
            name="ck_reviewed_understanding_model_gateway_source",
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > reviewed_at",
            name="ck_reviewed_understanding_expiry_order",
        ),
        sa.CheckConstraint(
            "(effective_status = 'REVOKED' AND revoked_at IS NOT NULL "
            "AND revocation_ref IS NOT NULL) OR "
            "(effective_status <> 'REVOKED' AND revoked_at IS NULL "
            "AND revocation_ref IS NULL)",
            name="ck_reviewed_understanding_revocation_consistency",
        ),
        sa.CheckConstraint(
            "effective_status <> 'EXPIRED' OR expires_at IS NOT NULL",
            name="ck_reviewed_understanding_expired_has_expiry",
        ),
    )
    op.create_index(
        "idx_reviewed_understanding_scope_timeline",
        TABLE_NAME,
        ["tenant_id", "family_id", "assessment_session_id", sa.text("reviewed_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_reviewed_understanding_scope_timeline", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
