"""Add durable worker claim/lease columns to Human Gate tasks.

Revision ID: 0011_ai_human_task_claims
Revises: 0010_experience_run_interactions
Create Date: 2026-08-30

The claim is an operational delivery lease, not a business fact.  It is
available only for a decided task with an accepted Named Action, and an
expired claim can be atomically replaced by another worker.  The revision is
placed after the current experience-run chain so it does not edit an already
applied Human Gate migration.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_ai_human_task_claims"
down_revision: str | None = "0010_experience_run_interactions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_human_tasks",
        sa.Column("claim_owner", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "ai_human_tasks",
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_ai_human_tasks_claim_shape",
        "ai_human_tasks",
        "(claim_owner IS NULL AND claim_expires_at IS NULL) OR "
        "(status = 'DECIDED' AND action_request_payload IS NOT NULL "
        "AND claim_owner IS NOT NULL AND claim_expires_at IS NOT NULL)",
    )
    op.create_index(
        "ix_ai_human_tasks_claim_owner",
        "ai_human_tasks",
        ["claim_owner"],
    )
    op.create_index(
        "ix_ai_human_tasks_claim_expires_at",
        "ai_human_tasks",
        ["claim_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_human_tasks_claim_expires_at", table_name="ai_human_tasks")
    op.drop_index("ix_ai_human_tasks_claim_owner", table_name="ai_human_tasks")
    op.drop_constraint(
        "ck_ai_human_tasks_claim_shape",
        "ai_human_tasks",
        type_="check",
    )
    op.drop_column("ai_human_tasks", "claim_expires_at")
    op.drop_column("ai_human_tasks", "claim_owner")
