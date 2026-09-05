"""Per-consumer delivery receipts for the shared domain outbox.

Revision ID: 0062_domain_outbox_consumer_deliveries
Revises: 0061_growth_action_ai_provenance
Create Date: 2026-09-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0062_domain_outbox_consumer_deliveries"
down_revision: str | None = "0061_growth_action_ai_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "domain_outbox_consumer_deliveries",
        sa.Column("outbox_id", sa.Uuid(), nullable=False),
        sa.Column("consumer_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('RETRY','DELIVERED','DISCARDED','DEAD_LETTERED')",
            name="ck_domain_outbox_consumer_delivery_status",
        ),
        sa.ForeignKeyConstraint(
            ["outbox_id"],
            ["outbox_events.outbox_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("outbox_id", "consumer_name"),
    )
    op.create_index(
        "ix_domain_outbox_consumer_pending",
        "domain_outbox_consumer_deliveries",
        ["consumer_name", "status", "updated_at"],
    )
    op.create_index(
        "ix_outbox_events_aggregate_route",
        "outbox_events",
        ["aggregate_type", "event_name", "created_at", "outbox_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_outbox_events_aggregate_route",
        table_name="outbox_events",
    )
    op.drop_index(
        "ix_domain_outbox_consumer_pending",
        table_name="domain_outbox_consumer_deliveries",
    )
    op.drop_table("domain_outbox_consumer_deliveries")
