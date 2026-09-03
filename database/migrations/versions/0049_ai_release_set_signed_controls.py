"""Persist signed controls for exact atomic ReleaseSet transitions."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0049_ai_release_set_signed_controls"
down_revision: str | None = "0048_ai_runtime_release_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_family_experience_release_set_controls",
        sa.Column("control_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("phase", sa.String(length=16), nullable=False),
        sa.Column("rollout_percent", sa.Integer(), nullable=False),
        sa.Column("source_release_set_id", sa.String(length=64), nullable=False),
        sa.Column("target_release_set_id", sa.String(length=64), nullable=True),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("use_case", sa.String(length=256), nullable=False),
        sa.Column("data_class", sa.String(length=64), nullable=False),
        sa.Column("runtime_config_digest", sa.String(length=64), nullable=False),
        sa.Column("expected_effective_sequence", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.String(length=256), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("signature_ref", sa.String(length=64), nullable=False),
        sa.Column("signature_algorithm", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('APPLY', 'ROLLBACK')",
            name="ck_ai_release_set_control_kind",
        ),
        sa.CheckConstraint(
            "(kind = 'APPLY' AND phase = 'CANARY' "
            "AND rollout_percent BETWEEN 1 AND 99) OR "
            "(kind = 'APPLY' AND phase = 'ACTIVE' AND rollout_percent = 100) OR "
            "(kind = 'ROLLBACK' AND phase = 'ROLLED_BACK' AND rollout_percent = 0)",
            name="ck_ai_release_set_control_phase",
        ),
        sa.CheckConstraint(
            "(kind = 'APPLY' AND target_release_set_id IS NULL) OR "
            "(kind = 'ROLLBACK' AND target_release_set_id IS NOT NULL "
            "AND target_release_set_id <> source_release_set_id)",
            name="ck_ai_release_set_control_target",
        ),
        sa.PrimaryKeyConstraint("control_id"),
    )
    op.create_index(
        "uq_ai_release_set_control_idempotency",
        "ai_family_experience_release_set_controls",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_ai_release_set_control_idempotency",
        table_name="ai_family_experience_release_set_controls",
    )
    op.drop_table("ai_family_experience_release_set_controls")
