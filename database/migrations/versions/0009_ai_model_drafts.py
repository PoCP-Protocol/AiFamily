"""Persist provider-produced ModelDraft records and their scope envelope.

Revision ID: 0009_ai_model_drafts
Revises: 0008_experience_runs
Create Date: 2026-08-30

The registry belongs to the AI runtime.  It stores a model result as DRAFT
only, together with the exact tenant/family/subject/purpose/correlation scope
needed before a Human Gate consumer can use its provenance reference.  It has
no foreign key to a business domain and cannot be used to mutate a canonical
fact.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_ai_model_drafts"
down_revision: str | None = "0008_experience_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_model_drafts",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("draft_id", sa.String(length=160), nullable=False),
        sa.Column("provenance_ref", sa.String(length=256), nullable=False),
        sa.Column("family_id", sa.String(length=160), nullable=False),
        sa.Column("subject_person_id", sa.String(length=160), nullable=False),
        sa.Column("purpose", sa.String(length=96), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("provider_id", sa.String(length=160), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("model_version", sa.String(length=160), nullable=False),
        sa.Column("prompt_version", sa.String(length=160), nullable=False),
        sa.Column("schema_version", sa.String(length=160), nullable=False),
        sa.Column("context_snapshot_ref", sa.String(length=256), nullable=False),
        sa.Column("use_case", sa.String(length=160), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("data_class", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("output_payload", postgresql.JSONB(), nullable=False),
        sa.Column("provenance_payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="DRAFT"),
        sa.Column(
            "may_mutate_business_state",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "draft_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "provenance_ref",
            name="uq_ai_model_drafts_tenant_provenance",
        ),
        sa.CheckConstraint("status = 'DRAFT'", name="ck_ai_model_drafts_draft_only"),
        sa.CheckConstraint(
            "may_mutate_business_state = false",
            name="ck_ai_model_drafts_cannot_mutate",
        ),
        sa.CheckConstraint("latency_ms >= 0", name="ck_ai_model_drafts_latency_nonnegative"),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_ai_model_drafts_confidence_range",
        ),
    )
    op.create_index(
        "ix_ai_model_drafts_tenant_family_subject",
        "ai_model_drafts",
        ["tenant_id", "family_id", "subject_person_id"],
    )
    op.create_index(
        "ix_ai_model_drafts_tenant_correlation",
        "ai_model_drafts",
        ["tenant_id", "correlation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_model_drafts_tenant_correlation",
        table_name="ai_model_drafts",
    )
    op.drop_index(
        "ix_ai_model_drafts_tenant_family_subject",
        table_name="ai_model_drafts",
    )
    op.drop_table("ai_model_drafts")
