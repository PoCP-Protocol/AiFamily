"""Persist restart-safe feedback regression scheduler jobs."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0078_ai_feedback_regression_jobs"
down_revision: str | None = "0077_journey_adopted_growth_plans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_feedback_regression_jobs",
        sa.Column("job_id", sa.String(length=128), nullable=False),
        sa.Column("batch_ref", sa.String(length=256), nullable=False),
        sa.Column("case_version", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=256), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(length=256), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING', 'LEASED', 'COMPLETED', 'FAILED')",
            name="ck_ai_feedback_regression_job_status",
        ),
        sa.PrimaryKeyConstraint("job_id"),
    )
    op.create_index(
        "ix_ai_feedback_regression_jobs_due",
        "ai_feedback_regression_jobs",
        ["status", "due_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_feedback_regression_jobs_due", table_name="ai_feedback_regression_jobs")
    op.drop_table("ai_feedback_regression_jobs")
