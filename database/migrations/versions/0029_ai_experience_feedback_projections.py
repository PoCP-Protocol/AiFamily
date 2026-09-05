"""Persist notification inbox and scope-local analytics projections.

Revision ID: 0029_ai_experience_feedback_projections
Revises: 0028_ai_achievement_occurrences
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_ai_experience_feedback_projections"
down_revision: str | None = "0028_ai_achievement_occurrences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_achievement_notifications",
        sa.Column("notification_id", sa.String(length=256), nullable=False),
        sa.Column("achievement_id", sa.String(length=256), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("subject_ids", sa.String(length=1024), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("message", sa.String(length=4000), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="UNREAD"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("notification_id"),
        sa.UniqueConstraint("achievement_id", name="uq_ai_achievement_notification"),
    )
    for name, column in (
        ("tenant_id", "tenant_id"),
        ("family_id", "family_id"),
    ):
        op.create_index(
            f"ix_ai_achievement_notifications_{name}",
            "ai_achievement_notifications",
            [column],
        )

    op.create_table(
        "ai_experience_analytics",
        sa.Column("row_id", sa.String(length=128), nullable=False),
        sa.Column("scope_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("region_id", sa.String(length=16), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("metric_key", sa.String(length=128), nullable=False),
        sa.Column("value_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("value_count >= 0", name="ck_ai_experience_analytics_count"),
        sa.PrimaryKeyConstraint("row_id"),
        sa.UniqueConstraint(
            "scope_fingerprint", "metric_key", name="uq_ai_experience_analytics_metric"
        ),
    )
    for name, column in (
        ("scope_fingerprint", "scope_fingerprint"),
        ("tenant_id", "tenant_id"),
        ("family_id", "family_id"),
    ):
        op.create_index(
            f"ix_ai_experience_analytics_{name}",
            "ai_experience_analytics",
            [column],
        )

    op.create_table(
        "ai_experience_analytics_records",
        sa.Column("record_id", sa.String(length=256), nullable=False),
        sa.Column("record_kind", sa.String(length=32), nullable=False),
        sa.Column("scope_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("record_id"),
    )
    op.create_index(
        "ix_ai_experience_analytics_records_scope",
        "ai_experience_analytics_records",
        ["scope_fingerprint"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_experience_analytics_records_scope",
        table_name="ai_experience_analytics_records",
    )
    op.drop_table("ai_experience_analytics_records")
    for name in ("family_id", "tenant_id", "scope_fingerprint"):
        op.drop_index(f"ix_ai_experience_analytics_{name}", table_name="ai_experience_analytics")
    op.drop_table("ai_experience_analytics")
    for name in ("family_id", "tenant_id"):
        op.drop_index(
            f"ix_ai_achievement_notifications_{name}",
            table_name="ai_achievement_notifications",
        )
    op.drop_table("ai_achievement_notifications")
