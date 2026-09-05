"""Persist scoped AgentAuthorization leases and their audit trail.

Revision ID: 0013_ai_authorization_leases
Revises: 0012_ai_agent_runs
Create Date: 2026-08-30

This is runtime metadata only.  Expiry is evaluated at read time and revoked
leases are retained for audit; neither table is a Family/Growth fact store.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_ai_authorization_leases"
down_revision: str | None = "0012_ai_agent_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_type = postgresql.JSONB()
    op.create_table(
        "ai_agent_authorizations",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("authorization_id", sa.String(length=128), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("allowed_use_cases", json_type, nullable=False),
        sa.Column("allowed_tools", json_type, nullable=False),
        sa.Column("issued_by", sa.String(length=128), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_steps", sa.Integer(), nullable=False),
        sa.Column("max_cost_micros", sa.BigInteger(), nullable=True),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("audit_ref", sa.String(length=256), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "authorization_id"),
        sa.CheckConstraint("expires_at > issued_at", name="ck_ai_auth_expires_after_issue"),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= issued_at",
            name="ck_ai_auth_revoke_after_issue",
        ),
        sa.CheckConstraint("max_steps >= 1", name="ck_ai_auth_max_steps_positive"),
        sa.CheckConstraint(
            "max_cost_micros IS NULL OR max_cost_micros >= 0",
            name="ck_ai_auth_max_cost_nonnegative",
        ),
    )
    op.create_index(
        "ix_ai_agent_authorizations_scope",
        "ai_agent_authorizations",
        ["tenant_id", "family_id", "agent_id"],
    )
    op.create_index(
        "ix_ai_agent_authorizations_expiry",
        "ai_agent_authorizations",
        ["tenant_id", "family_id", "expires_at"],
    )

    op.create_table(
        "ai_agent_authorization_audits",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("event_id", sa.String(length=256), nullable=False),
        sa.Column("authorization_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("audit_ref", sa.String(length=256), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("audit_metadata", json_type, nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "event_id"),
        sa.CheckConstraint(
            "event_type IN ('ISSUED', 'REVOKED')",
            name="ck_ai_auth_audit_event_type",
        ),
    )
    op.create_index(
        "ix_ai_agent_authorization_audits_lookup",
        "ai_agent_authorization_audits",
        ["tenant_id", "family_id", "authorization_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_agent_authorization_audits_lookup",
        table_name="ai_agent_authorization_audits",
    )
    op.drop_table("ai_agent_authorization_audits")
    op.drop_index("ix_ai_agent_authorizations_expiry", table_name="ai_agent_authorizations")
    op.drop_index("ix_ai_agent_authorizations_scope", table_name="ai_agent_authorizations")
    op.drop_table("ai_agent_authorizations")
