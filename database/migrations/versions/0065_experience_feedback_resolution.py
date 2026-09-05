"""Human response receipts and subject deletion proofs for feedback.

Revision ID: 0065_experience_feedback_resolution
Revises: 0064_family_experience_signals
Create Date: 2026-09-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0065_experience_feedback_resolution"
down_revision: str | None = "0064_family_experience_signals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_experience_feedback_resolutions",
        sa.Column("resolution_id", sa.String(length=96), nullable=False),
        sa.Column("feedback_id", sa.String(length=96), nullable=False),
        sa.Column("request_id", sa.String(length=160), nullable=False),
        sa.Column("human_task_id", sa.String(length=160), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("subject_ids", postgresql.JSONB(), nullable=False),
        sa.Column("purpose", sa.String(length=128), nullable=False),
        sa.Column("consent_version", sa.String(length=160), nullable=False),
        sa.Column("deletion_ref", sa.String(length=256), nullable=False),
        sa.Column("responder_actor_id", sa.String(length=160), nullable=False),
        sa.Column("resolution_code", sa.String(length=64), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("resolution_id"),
        sa.ForeignKeyConstraint(
            ["feedback_id"], ["ai_achievement_feedback.feedback_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["human_task_id"], ["ai_human_tasks.task_id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("feedback_id", name="uq_ai_feedback_resolution_feedback"),
        sa.UniqueConstraint("request_id", name="uq_ai_feedback_resolution_request"),
        sa.CheckConstraint(
            "resolution_code = 'HUMAN_FOLLOWUP_QUEUED'",
            name="ck_ai_feedback_resolution_code",
        ),
    )
    op.create_index(
        "ix_ai_feedback_resolution_scope",
        "ai_experience_feedback_resolutions",
        ["tenant_id", "family_id", "resolved_at"],
    )
    op.create_table(
        "ai_experience_feedback_deletion_fences",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("subject_ref_digest", sa.String(length=64), nullable=False),
        sa.Column("deletion_ref_digest", sa.String(length=64), nullable=False),
        sa.Column("fenced_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "subject_ref_digest"),
    )
    op.create_table(
        "ai_achievement_feedback_deletion_proofs",
        sa.Column("proof_id", sa.String(length=96), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("subject_ref_digest", sa.String(length=64), nullable=False),
        sa.Column("deletion_ref_digest", sa.String(length=64), nullable=False),
        sa.Column("deleted_feedback", sa.Integer(), nullable=False),
        sa.Column("deleted_resolutions", sa.Integer(), nullable=False),
        sa.Column("deleted_deliveries", sa.Integer(), nullable=False),
        sa.Column("deleted_human_tasks", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("proof_id"),
        sa.CheckConstraint(
            "deleted_feedback >= 0 AND deleted_resolutions >= 0 "
            "AND deleted_deliveries >= 0 AND deleted_human_tasks >= 0",
            name="ck_ai_feedback_deletion_counts",
        ),
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_ai_achievement_feedback_update()
        RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE'
             AND current_setting('aifamily.deletion_mode', true) = 'subject_request' THEN
            RETURN OLD;
          END IF;
          RAISE EXCEPTION 'ai_achievement_feedback is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_ai_experience_feedback_resolution_change()
        RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE'
             AND current_setting('aifamily.deletion_mode', true) = 'subject_request' THEN
            RETURN OLD;
          END IF;
          RAISE EXCEPTION 'ai_experience_feedback_resolutions is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_experience_feedback_resolutions_append_only
        BEFORE UPDATE OR DELETE ON ai_experience_feedback_resolutions
        FOR EACH ROW EXECUTE FUNCTION reject_ai_experience_feedback_resolution_change()
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_ai_feedback_governance_change()
        RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'AI feedback governance evidence is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table_name in (
        "ai_achievement_feedback_deletion_proofs",
        "ai_experience_feedback_deletion_fences",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_worm
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION reject_ai_feedback_governance_change()
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_no_truncate
            BEFORE TRUNCATE ON {table_name}
            FOR EACH STATEMENT EXECUTE FUNCTION reject_ai_feedback_governance_change()
            """
        )


def downgrade() -> None:
    for table_name in (
        "ai_achievement_feedback_deletion_proofs",
        "ai_experience_feedback_deletion_fences",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_worm ON {table_name}")
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_no_truncate ON {table_name}")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_ai_experience_feedback_resolutions_append_only "
        "ON ai_experience_feedback_resolutions"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_ai_experience_feedback_resolution_change()")
    op.execute("DROP FUNCTION IF EXISTS reject_ai_feedback_governance_change()")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_ai_achievement_feedback_update()
        RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'ai_achievement_feedback is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.drop_table("ai_achievement_feedback_deletion_proofs")
    op.drop_table("ai_experience_feedback_deletion_fences")
    op.drop_index(
        "ix_ai_feedback_resolution_scope",
        table_name="ai_experience_feedback_resolutions",
    )
    op.drop_table("ai_experience_feedback_resolutions")
