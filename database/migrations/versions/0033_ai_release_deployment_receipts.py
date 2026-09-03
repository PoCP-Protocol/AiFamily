"""Persist metadata-only release deployment and rollback receipts."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033_ai_release_deployment_receipts"
down_revision: str | None = "0032_ai_release_candidates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_release_deployment_receipts",
        sa.Column("receipt_id", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("phase", sa.String(length=16), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("candidate_id", sa.String(length=256), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("control_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=256), nullable=False),
        sa.Column("rollout_percent", sa.Integer(), nullable=False),
        sa.Column("external_ref", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "operation IN ('APPLY', 'ROLLBACK')",
            name="ck_ai_release_deployment_receipts_operation",
        ),
        sa.CheckConstraint(
            "phase IN ('CANARY', 'ACTIVE', 'ROLLED_BACK')",
            name="ck_ai_release_deployment_receipts_phase",
        ),
        sa.PrimaryKeyConstraint("receipt_id"),
    )
    op.create_index(
        "uq_ai_release_deployment_receipts_idempotency",
        "ai_release_deployment_receipts",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_ai_release_deployment_receipts_candidate_environment",
        "ai_release_deployment_receipts",
        ["candidate_id", "environment", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_release_deployment_receipts_candidate_environment",
        table_name="ai_release_deployment_receipts",
    )
    op.drop_index(
        "uq_ai_release_deployment_receipts_idempotency",
        table_name="ai_release_deployment_receipts",
    )
    op.drop_table("ai_release_deployment_receipts")
