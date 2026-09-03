"""Persist restart-safe family-experience canary scheduler jobs."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043_ai_canary_jobs"
down_revision: str | None = "0042_ai_canary_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_family_experience_canary_jobs",
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("candidate_id", sa.String(length=256), nullable=False),
        sa.Column("candidate_snapshot", sa.JSON(), nullable=False),
        sa.Column("receipt_id", sa.String(length=64), nullable=False),
        sa.Column("receipt_snapshot", sa.JSON(), nullable=False),
        sa.Column("rollback_control_id", sa.String(length=64), nullable=True),
        sa.Column("supervision_key", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(length=256), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assessment_id", sa.String(length=64), nullable=True),
        sa.Column("rollback_receipt_id", sa.String(length=64), nullable=True),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING', 'LEASED', 'COMPLETED', 'FAILED')",
            name="ck_ai_family_experience_canary_job_status",
        ),
        sa.PrimaryKeyConstraint("job_id"),
        sa.UniqueConstraint("supervision_key"),
    )
    op.create_index(
        "ix_ai_family_experience_canary_jobs_due",
        "ai_family_experience_canary_jobs",
        ["environment", "status", "due_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_family_experience_canary_jobs_due",
        table_name="ai_family_experience_canary_jobs",
    )
    op.drop_table("ai_family_experience_canary_jobs")
