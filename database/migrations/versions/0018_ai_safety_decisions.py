"""Persist provider-neutral Safety Runtime decisions."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_ai_safety_decisions"
down_revision: str | None = "0017_ai_model_attempts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_safety_decisions",
        sa.Column("decision_id", sa.String(length=128), nullable=False),
        sa.Column("stage", sa.String(length=16), nullable=False),
        sa.Column("request_id", sa.String(length=256), nullable=True),
        sa.Column("session_id", sa.String(length=256), nullable=True),
        sa.Column("use_case", sa.String(length=128), nullable=False),
        sa.Column("data_class", sa.String(length=64), nullable=False),
        sa.Column("subject_is_minor", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("requires_human_gate", sa.Boolean(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("decision_id"),
    )
    op.create_index(
        "ix_ai_safety_decisions_request_stage",
        "ai_safety_decisions",
        ["request_id", "stage", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_safety_decisions_request_stage",
        table_name="ai_safety_decisions",
    )
    op.drop_table("ai_safety_decisions")
