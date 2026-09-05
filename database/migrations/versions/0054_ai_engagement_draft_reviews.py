"""Persist immutable engagement drafts for later Human Gate review.

Revision ID: 0054_ai_engagement_draft_reviews
Revises: 0053_ai_release_transition_reconciliation
Create Date: 2026-09-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0054_ai_engagement_draft_reviews"
down_revision: str | None = "0053_ai_release_transition_reconciliation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_engagement_draft_reviews",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("draft_id", sa.String(length=160), nullable=False),
        sa.Column("family_id", sa.String(length=160), nullable=False),
        sa.Column("region_id", sa.String(length=16), nullable=False),
        sa.Column("subject_ids", sa.JSON(), nullable=False),
        sa.Column("purpose", sa.String(length=128), nullable=False),
        sa.Column("consent_version", sa.String(length=160), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("scope_payload", sa.JSON(), nullable=False),
        sa.Column("evidence_event_ids", sa.JSON(), nullable=False),
        sa.Column("output_payload", sa.JSON(), nullable=False),
        sa.Column("provenance_payload", sa.JSON(), nullable=False),
        sa.Column("stable_digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("may_mutate_business_state", sa.Boolean(), nullable=False),
        sa.Column("retention_policy", sa.String(length=160), nullable=False),
        sa.Column("deletion_ref", sa.String(length=256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status = 'DRAFT'",
            name="ck_ai_engagement_review_draft_only",
        ),
        sa.CheckConstraint(
            "may_mutate_business_state = false",
            name="ck_ai_engagement_review_cannot_mutate",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_ai_engagement_review_positive_ttl",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "draft_id"),
    )
    op.create_index(
        "uq_ai_engagement_review_request",
        "ai_engagement_draft_reviews",
        ["tenant_id", "family_id", "request_id"],
        unique=True,
    )
    op.create_index(
        "ix_ai_engagement_review_scope_expiry",
        "ai_engagement_draft_reviews",
        ["tenant_id", "family_id", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_engagement_review_scope_expiry",
        table_name="ai_engagement_draft_reviews",
    )
    op.drop_index(
        "uq_ai_engagement_review_request",
        table_name="ai_engagement_draft_reviews",
    )
    op.drop_table("ai_engagement_draft_reviews")
