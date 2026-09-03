"""Persist metadata-only operator access decisions for Experience operations."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Keep the Alembic revision identifier below PostgreSQL's historical
# ``alembic_version.version_num VARCHAR(32)`` limit.  The descriptive filename
# remains the stable human-facing reference.
revision: str = "0037_ops_audit"
down_revision: str | None = "0036_ai_context_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_experience_operations_audit",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("operator_id", sa.String(length=128), nullable=False),
        sa.Column("authorization_ref", sa.String(length=256), nullable=False),
        sa.Column("environment", sa.String(length=32), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_ai_experience_operations_audit_environment_time",
        "ai_experience_operations_audit",
        ["environment", "occurred_at"],
    )
    op.create_index(
        "ix_ai_experience_operations_audit_operator_time",
        "ai_experience_operations_audit",
        ["operator_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_experience_operations_audit_operator_time",
        table_name="ai_experience_operations_audit",
    )
    op.drop_index(
        "ix_ai_experience_operations_audit_environment_time",
        table_name="ai_experience_operations_audit",
    )
    op.drop_table("ai_experience_operations_audit")
