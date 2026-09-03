"""Persist post-gate Named Action attempts and terminal delivery state.

Revision ID: 0024_ai_accepted_action_delivery
Revises: 0023_ai_growth_graph_projection
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_ai_accepted_action_delivery"
down_revision: str | None = "0023_ai_growth_graph_projection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_accepted_action_deliveries",
        sa.Column("request_id", sa.String(length=160), nullable=False),
        sa.Column("task_id", sa.String(length=160), nullable=False),
        sa.Column("action_name", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=160), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("result_ref", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "attempts >= 0", name="ck_ai_accepted_action_delivery_attempts"
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'SUCCEEDED', 'DEAD_LETTERED')",
            name="ck_ai_accepted_action_delivery_status",
        ),
        sa.PrimaryKeyConstraint("request_id"),
        sa.UniqueConstraint("tenant_id", "task_id", name="uq_ai_accepted_action_delivery_task"),
    )
    op.create_index(
        "ix_ai_accepted_action_deliveries_task_id",
        "ai_accepted_action_deliveries",
        ["task_id"],
    )
    op.create_index(
        "ix_ai_accepted_action_deliveries_tenant_id",
        "ai_accepted_action_deliveries",
        ["tenant_id"],
    )
    op.create_index(
        "ix_ai_accepted_action_deliveries_family_id",
        "ai_accepted_action_deliveries",
        ["family_id"],
    )
    op.create_index(
        "ix_ai_accepted_action_deliveries_status",
        "ai_accepted_action_deliveries",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_accepted_action_deliveries_status",
        table_name="ai_accepted_action_deliveries",
    )
    op.drop_index(
        "ix_ai_accepted_action_deliveries_family_id",
        table_name="ai_accepted_action_deliveries",
    )
    op.drop_index(
        "ix_ai_accepted_action_deliveries_tenant_id",
        table_name="ai_accepted_action_deliveries",
    )
    op.drop_index(
        "ix_ai_accepted_action_deliveries_task_id",
        table_name="ai_accepted_action_deliveries",
    )
    op.drop_table("ai_accepted_action_deliveries")
