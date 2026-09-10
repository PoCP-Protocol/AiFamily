"""Create durable notification intents and delivery attempts."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0079_platform_notification_control_plane"
down_revision: str | None = "0078_ai_feedback_regression_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_notification_intents",
        sa.Column("intent_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("subject_id", sa.String(length=128), nullable=False),
        sa.Column("purpose", sa.String(length=128), nullable=False),
        sa.Column("consent_version", sa.String(length=128), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("template_key", sa.String(length=256), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("external_effect", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("intent_id"),
    )
    op.create_index(
        "ix_platform_notification_intents_tenant_id",
        "platform_notification_intents",
        ["tenant_id"],
    )
    op.create_index(
        "ix_platform_notification_intents_family_id",
        "platform_notification_intents",
        ["family_id"],
    )
    op.create_table(
        "platform_notification_attempts",
        sa.Column("attempt_id", sa.String(length=128), nullable=False),
        sa.Column("intent_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(length=256), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_reference", sa.String(length=256), nullable=True),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'leased', 'delivered', 'retry', 'suppressed', 'dead_letter')",
            name="ck_platform_notification_attempt_status",
        ),
        sa.PrimaryKeyConstraint("attempt_id"),
    )
    op.create_index(
        "ix_platform_notification_attempts_intent_id",
        "platform_notification_attempts",
        ["intent_id"],
    )
    op.create_index(
        "ix_platform_notification_attempts_status",
        "platform_notification_attempts",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_platform_notification_attempts_status",
        table_name="platform_notification_attempts",
    )
    op.drop_index(
        "ix_platform_notification_attempts_intent_id",
        table_name="platform_notification_attempts",
    )
    op.drop_table("platform_notification_attempts")
    op.drop_index(
        "ix_platform_notification_intents_family_id",
        table_name="platform_notification_intents",
    )
    op.drop_index(
        "ix_platform_notification_intents_tenant_id",
        table_name="platform_notification_intents",
    )
    op.drop_table("platform_notification_intents")
