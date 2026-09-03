"""Immutable review envelope for UI-05 AI growth-plan drafts.

Revision ID: 0057_ai_growth_plan_draft_reviews
Revises: 0056_course_content
Create Date: 2026-09-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0057_ai_growth_plan_draft_reviews"
down_revision: str | None = "0056_course_content"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "ai_growth_plan_draft_reviews"
IMMUTABLE_FUNCTION = "reject_ai_growth_plan_draft_review_update"
IMMUTABLE_TRIGGER = "trg_ai_growth_plan_draft_review_immutable"


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("draft_id", sa.String(length=160), nullable=False),
        sa.Column("request_id", sa.String(length=160), nullable=False),
        sa.Column("agent_run_id", sa.String(length=160), nullable=False),
        sa.Column("provenance_ref", sa.String(length=256), nullable=False),
        sa.Column("family_id", sa.String(length=160), nullable=False),
        sa.Column("region_id", sa.String(length=16), nullable=False),
        sa.Column("subject_person_id", sa.String(length=160), nullable=False),
        sa.Column("purpose", sa.String(length=96), nullable=False),
        sa.Column("consent_version", sa.String(length=160), nullable=False),
        sa.Column("data_class", sa.String(length=64), nullable=False),
        sa.Column("locale", sa.String(length=32), nullable=False),
        sa.Column("deletion_ref", sa.String(length=256), nullable=False),
        sa.Column("generation_correlation_id", sa.String(length=128), nullable=False),
        sa.Column("scope_payload", sa.JSON(), nullable=False),
        sa.Column("intent_id", sa.String(length=160), nullable=False),
        sa.Column("onboarding_id", sa.String(length=160), nullable=False),
        sa.Column("priority_id", sa.String(length=160), nullable=False),
        sa.Column("input_refs", sa.JSON(), nullable=False),
        sa.Column("stable_digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("may_mutate_business_state", sa.Boolean(), nullable=False),
        sa.Column("retention_policy", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "draft_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "family_id",
            "request_id",
            name="uq_ai_growth_plan_review_request",
        ),
        sa.CheckConstraint(
            "status = 'DRAFT'",
            name="ck_ai_growth_plan_review_draft_only",
        ),
        sa.CheckConstraint(
            "may_mutate_business_state = false",
            name="ck_ai_growth_plan_review_cannot_mutate",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_ai_growth_plan_review_positive_ttl",
        ),
    )
    op.create_index(
        "ix_ai_growth_plan_review_scope_expiry",
        TABLE_NAME,
        ["tenant_id", "family_id", "subject_person_id", "expires_at"],
    )
    op.execute(
        f"""
        CREATE FUNCTION {IMMUTABLE_FUNCTION}() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'ai growth plan draft review rows are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {IMMUTABLE_TRIGGER}
        BEFORE UPDATE ON {TABLE_NAME}
        FOR EACH ROW EXECUTE FUNCTION {IMMUTABLE_FUNCTION}()
        """
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {IMMUTABLE_TRIGGER} ON {TABLE_NAME}")
    op.execute(f"DROP FUNCTION IF EXISTS {IMMUTABLE_FUNCTION}()")
    op.drop_index("ix_ai_growth_plan_review_scope_expiry", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
