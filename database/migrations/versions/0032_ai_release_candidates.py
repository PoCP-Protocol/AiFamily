"""Persist the AI candidate release catalog projection."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_ai_release_candidates"
down_revision: str | None = "0031_ai_release_controls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_release_candidates",
        sa.Column("candidate_id", sa.String(length=256), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("provider_id", sa.String(length=256), nullable=False),
        sa.Column("model", sa.String(length=256), nullable=False),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("report_ref", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("last_control_id", sa.String(length=64), nullable=True),
        sa.Column("rollback_target_candidate_id", sa.String(length=256), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('BLOCKED', 'ADMITTED', 'APPROVED', 'ROLLED_BACK')",
            name="ck_ai_release_candidates_status",
        ),
        sa.PrimaryKeyConstraint("candidate_id", "environment"),
    )
    op.create_index(
        "ix_ai_release_candidates_environment_status",
        "ai_release_candidates",
        ["environment", "status", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_release_candidates_environment_status",
        table_name="ai_release_candidates",
    )
    op.drop_table("ai_release_candidates")
