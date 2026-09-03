"""Persist atomic release-set deployment and rollback transitions."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0047_ai_release_set_deployments"
down_revision: str | None = "0046_ai_experience_release_sets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_family_experience_release_set_deployments",
        sa.Column("sequence", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("receipt_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("release_set_id", sa.String(length=64), nullable=False),
        sa.Column("target_release_set_id", sa.String(length=64), nullable=True),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("use_case", sa.String(length=256), nullable=False),
        sa.Column("data_class", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("phase", sa.String(length=16), nullable=False),
        sa.Column("rollout_percent", sa.Integer(), nullable=False),
        sa.Column("control_id", sa.String(length=128), nullable=False),
        sa.Column("actor_id", sa.String(length=256), nullable=False),
        sa.Column("applied_config_digest", sa.String(length=64), nullable=False),
        sa.Column("acknowledged_release_set_id", sa.String(length=64), nullable=False),
        sa.Column("external_ref", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "operation IN ('APPLY', 'ROLLBACK')",
            name="ck_ai_experience_release_set_deploy_operation",
        ),
        sa.CheckConstraint(
            "phase IN ('CANARY', 'ACTIVE', 'ROLLED_BACK')",
            name="ck_ai_experience_release_set_deploy_phase",
        ),
        sa.CheckConstraint(
            "(phase = 'CANARY' AND rollout_percent BETWEEN 1 AND 99) OR "
            "(phase = 'ACTIVE' AND rollout_percent = 100) OR "
            "(phase = 'ROLLED_BACK' AND rollout_percent = 0)",
            name="ck_ai_experience_release_set_deploy_rollout",
        ),
        sa.CheckConstraint(
            "(operation = 'APPLY' AND phase IN ('CANARY', 'ACTIVE') "
            "AND target_release_set_id IS NULL "
            "AND acknowledged_release_set_id = release_set_id) OR "
            "(operation = 'ROLLBACK' AND phase = 'ROLLED_BACK' "
            "AND target_release_set_id IS NOT NULL "
            "AND target_release_set_id <> release_set_id "
            "AND acknowledged_release_set_id = target_release_set_id)",
            name="ck_ai_experience_release_set_deploy_transition",
        ),
        sa.PrimaryKeyConstraint("sequence"),
        sa.UniqueConstraint("receipt_id"),
    )
    op.create_index(
        "uq_ai_experience_release_set_deploy_idempotency",
        "ai_family_experience_release_set_deployments",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_ai_experience_release_set_deploy_scope_sequence",
        "ai_family_experience_release_set_deployments",
        ["environment", "use_case", "data_class", "sequence"],
    )


def downgrade() -> None:
    table = "ai_family_experience_release_set_deployments"
    op.drop_index("ix_ai_experience_release_set_deploy_scope_sequence", table_name=table)
    op.drop_index("uq_ai_experience_release_set_deploy_idempotency", table_name=table)
    op.drop_table(table)
