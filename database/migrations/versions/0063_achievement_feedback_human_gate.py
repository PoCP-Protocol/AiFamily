"""Append-only achievement feedback and Human Gate linkage.

Revision ID: 0063_achievement_feedback_human_gate
Revises: 0062_domain_outbox_consumer_deliveries
Create Date: 2026-09-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0063_achievement_feedback_human_gate"
down_revision: str | None = "0062_domain_outbox_consumer_deliveries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_achievement_feedback",
        sa.Column("feedback_id", sa.String(length=96), nullable=False),
        sa.Column("achievement_id", sa.String(length=256), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("signal", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("region_id", sa.String(length=16), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("subject_ids", postgresql.JSONB(), nullable=False),
        sa.Column("purpose", sa.String(length=128), nullable=False),
        sa.Column("consent_version", sa.String(length=160), nullable=False),
        sa.Column("data_class", sa.String(length=64), nullable=False),
        sa.Column("locale", sa.String(length=32), nullable=False),
        sa.Column("deletion_ref", sa.String(length=256), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("causation_id", sa.String(length=128), nullable=False),
        sa.Column("actor_id", sa.String(length=160), nullable=False),
        sa.Column("reason_code", sa.String(length=128), nullable=True),
        sa.Column("provenance_ref", sa.String(length=256), nullable=False),
        sa.Column("provenance_payload", postgresql.JSONB(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("human_task_id", sa.String(length=160), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("feedback_id"),
        sa.ForeignKeyConstraint(
            ["achievement_id"],
            ["ai_achievement_projections.achievement_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["human_task_id"],
            ["ai_human_tasks.task_id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_ai_achievement_feedback_idempotency",
        ),
        sa.CheckConstraint(
            "signal IN ('helpful','not_helpful','request_human')",
            name="ck_ai_achievement_feedback_signal",
        ),
        sa.CheckConstraint(
            "(signal = 'helpful') OR reason_code IS NOT NULL",
            name="ck_ai_achievement_feedback_reason",
        ),
        sa.CheckConstraint(
            "(signal = 'request_human' AND human_task_id IS NOT NULL) OR "
            "(signal <> 'request_human' AND human_task_id IS NULL)",
            name="ck_ai_achievement_feedback_human_task",
        ),
    )
    op.create_index(
        "ix_ai_achievement_feedback_scope",
        "ai_achievement_feedback",
        ["tenant_id", "family_id", "achievement_id", "occurred_at"],
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_ai_achievement_feedback_update()
        RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'ai_achievement_feedback is append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_achievement_feedback_append_only
        BEFORE UPDATE OR DELETE ON ai_achievement_feedback
        FOR EACH ROW EXECUTE FUNCTION reject_ai_achievement_feedback_update()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_ai_achievement_feedback_append_only "
        "ON ai_achievement_feedback"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_ai_achievement_feedback_update()")
    op.drop_index(
        "ix_ai_achievement_feedback_scope",
        table_name="ai_achievement_feedback",
    )
    op.drop_table("ai_achievement_feedback")
