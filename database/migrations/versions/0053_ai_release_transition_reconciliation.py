"""Add bounded reconciliation leases to ReleaseSet transitions."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0053_ai_release_transition_reconciliation"
down_revision: str | None = "0052_ai_execution_materials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table = "ai_family_experience_release_set_transitions"
    op.add_column(
        table,
        sa.Column(
            "reconciliation_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        table,
        sa.Column("reconciliation_lease_owner", sa.String(length=256), nullable=True),
    )
    op.add_column(
        table,
        sa.Column("reconciliation_lease_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        table,
        sa.Column("next_reconcile_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_ai_release_set_reconciliation_attempts",
        table,
        "reconciliation_attempts >= 0",
    )
    op.create_index(
        "ix_ai_release_set_transition_reconcile_due",
        table,
        ["environment", "status", "next_reconcile_at", "reconciliation_lease_until"],
    )


def downgrade() -> None:
    table = "ai_family_experience_release_set_transitions"
    op.drop_index("ix_ai_release_set_transition_reconcile_due", table_name=table)
    op.drop_constraint(
        "ck_ai_release_set_reconciliation_attempts",
        table,
        type_="check",
    )
    op.drop_column(table, "next_reconcile_at")
    op.drop_column(table, "reconciliation_lease_until")
    op.drop_column(table, "reconciliation_lease_owner")
    op.drop_column(table, "reconciliation_attempts")

