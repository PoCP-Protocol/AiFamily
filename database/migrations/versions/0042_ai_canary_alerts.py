"""Persist metadata-only canary alerts and human acknowledgement."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0042_ai_canary_alerts"
down_revision: str | None = "0041_ai_canary_assessments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_family_experience_canary_alerts",
        sa.Column("alert_id", sa.String(length=64), nullable=False),
        sa.Column("assessment_id", sa.String(length=64), nullable=False),
        sa.Column("candidate_id", sa.String(length=256), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("rollback_receipt_id", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_by", sa.String(length=256), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('ROLLBACK_EXECUTED', 'ROLLBACK_BLOCKED')",
            name="ck_ai_family_experience_canary_alert_kind",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN', 'ACKNOWLEDGED')",
            name="ck_ai_family_experience_canary_alert_status",
        ),
        sa.PrimaryKeyConstraint("alert_id"),
    )
    op.create_index(
        "ix_ai_family_experience_canary_alerts_environment_status",
        "ai_family_experience_canary_alerts",
        ["environment", "status", "opened_at"],
    )
    op.create_index(
        "uq_ai_family_experience_canary_alert_assessment",
        "ai_family_experience_canary_alerts",
        ["assessment_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_ai_family_experience_canary_alert_assessment",
        table_name="ai_family_experience_canary_alerts",
    )
    op.drop_index(
        "ix_ai_family_experience_canary_alerts_environment_status",
        table_name="ai_family_experience_canary_alerts",
    )
    op.drop_table("ai_family_experience_canary_alerts")
