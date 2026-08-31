"""Persist the first complete Journey MVP scenario.

This revision is deliberately separate from the historical 90-day journey
tables.  The first-arrival product is a 21-day family practice loop and needs
its own explicit contract; it must not silently reinterpret the older tables.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_journey_mvp_persistence"
down_revision: str | None = "0003_service_booking_additions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "family_mvp_journey_plans",
        sa.Column("plan_id", sa.String(128), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("family_id", sa.String(128), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("intent_id", sa.String(128), nullable=True),
        sa.Column("focus_id", sa.String(128), nullable=False),
        sa.Column("goal_text", sa.String(500), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("current_phase", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_refs", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("knowledge_refs", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('DRAFT','ACTIVE','PAUSED')", name="ck_mvp_journey_plan_status"
        ),
    )
    op.create_index(
        "uq_mvp_journey_plan_intent",
        "family_mvp_journey_plans",
        ["tenant_id", "family_id", "intent_id"],
        unique=True,
        postgresql_where=sa.text("intent_id IS NOT NULL"),
        sqlite_where=sa.text("intent_id IS NOT NULL"),
    )
    op.create_table(
        "family_mvp_journey_practices",
        sa.Column("practice_id", sa.String(128), primary_key=True),
        sa.Column("plan_id", sa.String(128), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("family_id", sa.String(128), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("rationale", sa.String(1000), nullable=False),
        sa.Column("day_index", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["family_mvp_journey_plans.plan_id"]),
        sa.CheckConstraint("day_index BETWEEN 1 AND 21", name="ck_mvp_journey_practice_day"),
    )
    op.create_index(
        "uq_mvp_journey_practice_day",
        "family_mvp_journey_practices",
        ["plan_id", "day_index"],
        unique=True,
    )
    op.create_table(
        "family_mvp_journey_practice_records",
        sa.Column("record_id", sa.String(128), primary_key=True),
        sa.Column("practice_id", sa.String(128), nullable=False),
        sa.Column("plan_id", sa.String(128), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("family_id", sa.String(128), nullable=False),
        sa.Column("observation", sa.String(2000), nullable=False),
        sa.Column("blocker", sa.String(500), nullable=True),
        sa.ForeignKeyConstraint(["practice_id"], ["family_mvp_journey_practices.practice_id"]),
        sa.ForeignKeyConstraint(["plan_id"], ["family_mvp_journey_plans.plan_id"]),
    )


def downgrade() -> None:
    op.drop_table("family_mvp_journey_practice_records")
    op.drop_index("uq_mvp_journey_practice_day", table_name="family_mvp_journey_practices")
    op.drop_table("family_mvp_journey_practices")
    op.drop_index("uq_mvp_journey_plan_intent", table_name="family_mvp_journey_plans")
    op.drop_table("family_mvp_journey_plans")
