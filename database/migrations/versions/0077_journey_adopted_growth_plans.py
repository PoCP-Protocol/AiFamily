"""Persist guardian-adopted growth-plan projections."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0077_journey_adopted_growth_plans"
down_revision: str | None = "0076_course_release_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "journey_adopted_growth_plans",
        sa.Column("plan_id", sa.String(160), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("family_id", sa.String(160), nullable=False),
        sa.Column("subject_refs", sa.JSON(), nullable=False),
        sa.Column("draft_ref", sa.String(256), nullable=False),
        sa.Column("draft_version", sa.Integer(), nullable=False),
        sa.Column("model_run_ref", sa.String(256), nullable=False),
        sa.Column("provenance_ref", sa.String(256), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("family_goal", sa.JSON(), nullable=False),
        sa.Column("why_this_plan", sa.Text(), nullable=False),
        sa.Column("duration", sa.JSON(), nullable=False),
        sa.Column("stages", sa.JSON(), nullable=False),
        sa.Column("adjustable_choices", sa.JSON(), nullable=False),
        sa.Column("selected_choices", sa.JSON(), nullable=False),
        sa.Column("unknowns_to_watch", sa.JSON(), nullable=False),
        sa.Column("review_rhythm", sa.JSON(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("adopted_by", sa.String(160), nullable=False),
        sa.Column("adopted_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("plan_id"),
        sa.UniqueConstraint("tenant_id", "family_id", name="uq_journey_adopted_growth_plan_scope"),
        sa.CheckConstraint("status = 'ACTIVE'", name="ck_journey_adopted_growth_plan_active"),
        sa.CheckConstraint("draft_version > 0", name="ck_journey_adopted_growth_plan_version"),
    )
    op.create_index(
        "ix_journey_adopted_growth_plan_scope",
        "journey_adopted_growth_plans",
        ["tenant_id", "family_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_journey_adopted_growth_plan_scope",
        table_name="journey_adopted_growth_plans",
    )
    op.drop_table("journey_adopted_growth_plans")
