"""Add model budget accounts and pre-call reservations."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044_ai_model_budget_reservations"
down_revision: str | None = "0043_ai_canary_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_model_budget_accounts",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("period_key", sa.String(length=32), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("limit_microusd", sa.BigInteger(), nullable=False),
        sa.Column("reserved_microusd", sa.BigInteger(), nullable=False),
        sa.Column("spent_microusd", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "environment", "period_key"),
    )
    op.create_table(
        "ai_model_budget_reservations",
        sa.Column("reservation_id", sa.String(length=64), nullable=False),
        sa.Column("reservation_key", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("period_key", sa.String(length=32), nullable=False),
        sa.Column("request_ref", sa.String(length=64), nullable=False),
        sa.Column("provider_id", sa.String(length=128), nullable=False),
        sa.Column("model", sa.String(length=256), nullable=False),
        sa.Column("route_sequence", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("rate_card_version", sa.String(length=128), nullable=False),
        sa.Column("reserved_microusd", sa.BigInteger(), nullable=False),
        sa.Column("actual_microusd", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("outcome_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('RESERVED', 'SETTLED', 'CONSUMED_UNCERTAIN')",
            name="ck_ai_model_budget_reservation_status",
        ),
        sa.PrimaryKeyConstraint("reservation_id"),
        sa.UniqueConstraint("reservation_key"),
    )
    op.create_index(
        "ix_ai_model_budget_reservations_tenant_id",
        "ai_model_budget_reservations",
        ["tenant_id"],
    )
    op.create_index(
        "ix_ai_model_budget_reservations_request_ref",
        "ai_model_budget_reservations",
        ["request_ref"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_model_budget_reservations_request_ref",
        table_name="ai_model_budget_reservations",
    )
    op.drop_index(
        "ix_ai_model_budget_reservations_tenant_id",
        table_name="ai_model_budget_reservations",
    )
    op.drop_table("ai_model_budget_reservations")
    op.drop_table("ai_model_budget_accounts")
