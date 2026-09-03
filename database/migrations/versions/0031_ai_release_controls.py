"""Persist human approval and rollback control events for AI releases."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_ai_release_controls"
down_revision: str | None = "0030_ai_prompt_schema_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_release_controls",
        sa.Column("control_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("candidate_id", sa.String(length=256), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=256), nullable=False),
        sa.Column("target_candidate_id", sa.String(length=256), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("signature_ref", sa.String(length=64), nullable=False),
        sa.Column("signature_algorithm", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('APPROVAL', 'ROLLBACK')", name="ck_ai_release_controls_kind"),
        sa.PrimaryKeyConstraint("control_id"),
    )
    op.create_index(
        "uq_ai_release_controls_idempotency",
        "ai_release_controls",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_ai_release_controls_candidate_environment",
        "ai_release_controls",
        ["candidate_id", "environment", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_release_controls_candidate_environment", table_name="ai_release_controls")
    op.drop_index("uq_ai_release_controls_idempotency", table_name="ai_release_controls")
    op.drop_table("ai_release_controls")
