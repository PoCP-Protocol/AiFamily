"""Persist human-confirmed service blueprint proposal facts.

Revision ID: 0025_service_blueprint_proposals
Revises: 0024_ai_accepted_action_delivery
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_service_blueprint_proposals"
down_revision: str | None = "0024_ai_accepted_action_delivery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "family_service_blueprint_proposals",
        sa.Column("proposal_id", sa.String(length=192), nullable=False),
        sa.Column("request_id", sa.String(length=160), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=160), nullable=False),
        sa.Column("subject_ids", sa.JSON(), nullable=False),
        sa.Column("blueprint_ref", sa.String(length=256), nullable=False),
        sa.Column("primary_contradiction_ref", sa.String(length=256), nullable=False),
        sa.Column("action_refs", sa.JSON(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("provenance_ref", sa.String(length=256), nullable=False),
        sa.Column("correlation_id", sa.String(length=256), nullable=False),
        sa.Column("accepted_by_actor_id", sa.String(length=160), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stable_payload", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("proposal_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "request_id",
            name="uq_family_service_blueprint_proposal_request",
        ),
    )
    op.create_index(
        "ix_family_service_blueprint_proposals_tenant_id",
        "family_service_blueprint_proposals",
        ["tenant_id"],
    )
    op.create_index(
        "ix_family_service_blueprint_proposals_family_id",
        "family_service_blueprint_proposals",
        ["family_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_family_service_blueprint_proposals_family_id",
        table_name="family_service_blueprint_proposals",
    )
    op.drop_index(
        "ix_family_service_blueprint_proposals_tenant_id",
        table_name="family_service_blueprint_proposals",
    )
    op.drop_table("family_service_blueprint_proposals")
