"""Add tenant/family scope columns to AI runtime ledgers."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_ai_runtime_scope_columns"
down_revision: str | None = "0018_ai_safety_decisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_model_attempts",
        sa.Column("tenant_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "ai_model_attempts",
        sa.Column("family_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_ai_model_attempts_tenant_family",
        "ai_model_attempts",
        ["tenant_id", "family_id", "started_at"],
    )
    op.add_column(
        "ai_safety_decisions",
        sa.Column("tenant_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "ai_safety_decisions",
        sa.Column("family_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_ai_safety_decisions_tenant_family",
        "ai_safety_decisions",
        ["tenant_id", "family_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_safety_decisions_tenant_family",
        table_name="ai_safety_decisions",
    )
    op.drop_column("ai_safety_decisions", "family_id")
    op.drop_column("ai_safety_decisions", "tenant_id")
    op.drop_index(
        "ix_ai_model_attempts_tenant_family",
        table_name="ai_model_attempts",
    )
    op.drop_column("ai_model_attempts", "family_id")
    op.drop_column("ai_model_attempts", "tenant_id")
