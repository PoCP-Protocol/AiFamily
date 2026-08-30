"""Persist Human Gate proposals, decisions, and Named Action requests.

Revision ID: 0006_ai_human_tasks
Revises: 0005_fgcn_assignment_idempotency
Create Date: 2026-08-30

The row is a durable HumanTask aggregate.  The JSON snapshots retain the
immutable value objects that were reviewed; scalar columns provide tenant,
expiry, provenance, and replay lookup.  No business-domain foreign key is
introduced because the Human Gate must remain independent of domain facts.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_ai_human_tasks"
down_revision: str | None = "0005_fgcn_assignment_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_human_tasks",
        sa.Column("task_id", sa.String(length=160), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=160), nullable=True),
        sa.Column("subject_ids", postgresql.JSONB(), nullable=False),
        sa.Column("purpose", sa.String(length=96), nullable=False),
        sa.Column("consent_version", sa.String(length=160), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("proposal_id", sa.String(length=160), nullable=False),
        sa.Column("draft_id", sa.String(length=160), nullable=False),
        sa.Column("action_name", sa.String(length=128), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("provenance_ref", sa.String(length=256), nullable=False),
        sa.Column("proposal_payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision_id", sa.String(length=160), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_payload", postgresql.JSONB(), nullable=True),
        sa.Column("request_id", sa.String(length=160), nullable=True),
        sa.Column("action_request_payload", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("task_id"),
        sa.CheckConstraint(
            "status IN ('OPEN', 'DECIDED', 'EXPIRED')",
            name="ck_ai_human_tasks_status",
        ),
        sa.CheckConstraint(
            "(status IN ('OPEN', 'EXPIRED') AND decision_payload IS NULL "
            "AND action_request_payload IS NULL) OR "
            "(status = 'DECIDED' AND decision_payload IS NOT NULL)",
            name="ck_ai_human_tasks_lifecycle_shape",
        ),
    )
    op.create_index("ix_ai_human_tasks_tenant_id", "ai_human_tasks", ["tenant_id"])
    op.create_index("ix_ai_human_tasks_family_id", "ai_human_tasks", ["family_id"])
    op.create_index("ix_ai_human_tasks_correlation_id", "ai_human_tasks", ["correlation_id"])
    op.create_index("ix_ai_human_tasks_status", "ai_human_tasks", ["status"])
    op.create_index("ix_ai_human_tasks_expires_at", "ai_human_tasks", ["expires_at"])
    op.create_index(
        "uq_ai_human_tasks_tenant_proposal",
        "ai_human_tasks",
        ["tenant_id", "proposal_id"],
        unique=True,
    )
    op.create_index(
        "uq_ai_human_tasks_decision_id",
        "ai_human_tasks",
        ["decision_id"],
        unique=True,
        postgresql_where=sa.text("decision_id IS NOT NULL"),
        sqlite_where=sa.text("decision_id IS NOT NULL"),
    )
    op.create_index(
        "uq_ai_human_tasks_request_id",
        "ai_human_tasks",
        ["request_id"],
        unique=True,
        postgresql_where=sa.text("request_id IS NOT NULL"),
        sqlite_where=sa.text("request_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_ai_human_tasks_request_id", table_name="ai_human_tasks")
    op.drop_index("uq_ai_human_tasks_decision_id", table_name="ai_human_tasks")
    op.drop_index("uq_ai_human_tasks_tenant_proposal", table_name="ai_human_tasks")
    op.drop_index("ix_ai_human_tasks_expires_at", table_name="ai_human_tasks")
    op.drop_index("ix_ai_human_tasks_status", table_name="ai_human_tasks")
    op.drop_index("ix_ai_human_tasks_correlation_id", table_name="ai_human_tasks")
    op.drop_index("ix_ai_human_tasks_family_id", table_name="ai_human_tasks")
    op.drop_index("ix_ai_human_tasks_tenant_id", table_name="ai_human_tasks")
    op.drop_table("ai_human_tasks")
