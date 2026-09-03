"""Persist AI release/admission decisions for governance audit."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_ai_release_decisions"
down_revision: str | None = "0019_ai_runtime_scope_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_release_decisions",
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("candidate_id", sa.String(length=256), nullable=False),
        sa.Column("provider_id", sa.String(length=256), nullable=False),
        sa.Column("model", sa.String(length=256), nullable=False),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("report_ref", sa.Text(), nullable=False),
        sa.Column("failures", sa.JSON(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("decision_id"),
    )
    op.create_index(
        "ix_ai_release_decisions_candidate_environment",
        "ai_release_decisions",
        ["candidate_id", "environment", "evaluated_at"],
    )
    op.create_index(
        "ix_ai_release_decisions_provider_environment",
        "ai_release_decisions",
        ["provider_id", "environment", "evaluated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_release_decisions_provider_environment",
        table_name="ai_release_decisions",
    )
    op.drop_index(
        "ix_ai_release_decisions_candidate_environment",
        table_name="ai_release_decisions",
    )
    op.drop_table("ai_release_decisions")
