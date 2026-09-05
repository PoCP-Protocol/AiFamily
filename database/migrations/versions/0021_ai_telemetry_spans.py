"""Persist metadata-only AI telemetry span lifecycle records."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_ai_telemetry_spans"
down_revision: str | None = "0020_ai_release_decisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_telemetry_spans",
        sa.Column("span_id", sa.String(length=128), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("operation_id", sa.String(length=128), nullable=False),
        sa.Column("parent_span_id", sa.String(length=128), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("request_id", sa.String(length=256), nullable=True),
        sa.Column("session_id", sa.String(length=256), nullable=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=True),
        sa.Column("family_id", sa.String(length=128), nullable=True),
        sa.Column("use_case", sa.String(length=128), nullable=False),
        sa.Column("data_class", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=256), nullable=True),
        sa.Column("causation_id", sa.String(length=256), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("span_id"),
        sa.UniqueConstraint(
            "trace_id",
            "operation_id",
            "name",
            name="uq_ai_telemetry_trace_operation_name",
        ),
    )
    op.create_index(
        "ix_ai_telemetry_trace_sequence",
        "ai_telemetry_spans",
        ["trace_id", "started_at"],
    )
    op.create_index(
        "ix_ai_telemetry_scope_started",
        "ai_telemetry_spans",
        ["tenant_id", "family_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_telemetry_scope_started", table_name="ai_telemetry_spans")
    op.drop_index("ix_ai_telemetry_trace_sequence", table_name="ai_telemetry_spans")
    op.drop_table("ai_telemetry_spans")
