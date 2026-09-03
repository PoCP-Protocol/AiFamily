"""Persist pending ToolCall/Named Action envelopes before Human Gate.

Revision ID: 0014_tool_action_outbox
Revises: 0013_ai_authorization_leases
Create Date: 2026-08-30

Only provider-neutral runtime metadata is stored.  A row is explicitly kept
in ``PENDING_HUMAN_CONFIRMATION`` until a Human Gate consumer acknowledges
delivery; no accepted action or domain fact is represented by this table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_tool_action_outbox"
down_revision: str | None = "0013_ai_authorization_leases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_type = postgresql.JSONB()
    op.create_table(
        "ai_tool_action_outbox",
        sa.Column("message_id", sa.String(length=128), nullable=False),
        sa.Column("call_id", sa.String(length=256), nullable=False),
        sa.Column("tool_id", sa.String(length=128), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("use_case", sa.String(length=128), nullable=False),
        sa.Column("action_name", sa.String(length=128), nullable=False),
        sa.Column("action_arguments", json_type, nullable=False),
        sa.Column("subject_ids", json_type, nullable=False),
        sa.Column("purpose", sa.String(length=128), nullable=False),
        sa.Column("consent_version", sa.String(length=128), nullable=False),
        sa.Column("correlation_id", sa.String(length=256), nullable=False),
        sa.Column("provenance_ref", sa.String(length=256), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_fingerprint", sa.Text(), nullable=False),
        sa.Column("payload", json_type, nullable=False),
        sa.PrimaryKeyConstraint("message_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "call_id",
            name="uq_ai_tool_action_call",
        ),
        sa.CheckConstraint(
            "status = 'PENDING_HUMAN_CONFIRMATION'",
            name="ck_ai_tool_action_pending_gate",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_ai_tool_action_expiry_after_create",
        ),
    )
    op.create_index(
        "ix_ai_tool_action_outbox_pending",
        "ai_tool_action_outbox",
        ["tenant_id", "family_id", "enqueued_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_index(
        "ix_ai_tool_action_outbox_provenance",
        "ai_tool_action_outbox",
        ["tenant_id", "provenance_ref"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_tool_action_outbox_provenance", table_name="ai_tool_action_outbox")
    op.drop_index("ix_ai_tool_action_outbox_pending", table_name="ai_tool_action_outbox")
    op.drop_table("ai_tool_action_outbox")
