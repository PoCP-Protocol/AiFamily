"""Persist governed AgentRun lifecycle records and append-only traces.

Revision ID: 0012_ai_agent_runs
Revises: 0011_ai_human_task_claims
Create Date: 2026-08-30

The tables are owned by the AI runtime.  They retain execution metadata and
validated DRAFT output only; no row is a Family/Growth business fact.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_ai_agent_runs"
down_revision: str | None = "0011_ai_human_task_claims"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_agent_runs",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("request_id", sa.String(length=256), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("use_case", sa.String(length=128), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("idempotency_fingerprint", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("draft_payload", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("tenant_id", "run_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "family_id",
            "idempotency_key",
            name="uq_ai_agent_run_scope_idempotency",
        ),
        sa.CheckConstraint(
            "status IN ('STARTED', 'SUCCEEDED', 'FAILED')",
            name="ck_ai_agent_runs_status",
        ),
    )
    op.create_index(
        "ix_ai_agent_runs_scope",
        "ai_agent_runs",
        ["tenant_id", "family_id", "run_id"],
    )
    op.create_index(
        "ix_ai_agent_runs_trace",
        "ai_agent_runs",
        ["tenant_id", "trace_id"],
    )

    op.create_table(
        "ai_agent_traces",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "trace_id", "sequence"),
        sa.UniqueConstraint(
            "tenant_id",
            "run_id",
            "idempotency_key",
            name="uq_ai_agent_trace_idempotency",
        ),
        sa.CheckConstraint(
            "sequence >= 0",
            name="ck_ai_agent_traces_sequence_nonnegative",
        ),
    )
    op.create_index(
        "ix_ai_agent_traces_scope",
        "ai_agent_traces",
        ["tenant_id", "family_id", "run_id"],
    )
    op.create_index(
        "ix_ai_agent_traces_sequence",
        "ai_agent_traces",
        ["tenant_id", "trace_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_agent_traces_sequence", table_name="ai_agent_traces")
    op.drop_index("ix_ai_agent_traces_scope", table_name="ai_agent_traces")
    op.drop_table("ai_agent_traces")
    op.drop_index("ix_ai_agent_runs_trace", table_name="ai_agent_runs")
    op.drop_index("ix_ai_agent_runs_scope", table_name="ai_agent_runs")
    op.drop_table("ai_agent_runs")
