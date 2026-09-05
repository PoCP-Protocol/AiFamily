"""Persist pre-external ReleaseSet transition ownership and recovery state."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0051_ai_release_transition_state_machine"
down_revision: str | None = "0050_ai_release_projection_invocation_fence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_family_experience_release_set_transitions",
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("use_case", sa.String(length=256), nullable=False),
        sa.Column("data_class", sa.String(length=64), nullable=False),
        sa.Column("transition_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("control_id", sa.String(length=128), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("phase", sa.String(length=16), nullable=False),
        sa.Column("rollout_percent", sa.Integer(), nullable=False),
        sa.Column("source_release_set_id", sa.String(length=64), nullable=False),
        sa.Column("target_release_set_id", sa.String(length=64), nullable=True),
        sa.Column("runtime_config_digest", sa.String(length=64), nullable=False),
        sa.Column("expected_effective_sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("acknowledged_release_set_id", sa.String(length=64), nullable=True),
        sa.Column("applied_config_digest", sa.String(length=64), nullable=True),
        sa.Column("external_ref", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('PREPARED', 'ACKNOWLEDGED', 'COMMITTED', 'UNKNOWN')",
            name="ck_ai_release_set_transition_status",
        ),
        sa.CheckConstraint(
            "expected_effective_sequence >= 0",
            name="ck_ai_release_set_transition_sequence",
        ),
        sa.CheckConstraint(
            "(operation = 'APPLY' AND phase IN ('CANARY', 'ACTIVE') "
            "AND target_release_set_id IS NULL) OR "
            "(operation = 'ROLLBACK' AND phase = 'ROLLED_BACK' "
            "AND target_release_set_id IS NOT NULL "
            "AND target_release_set_id <> source_release_set_id)",
            name="ck_ai_release_set_transition_shape",
        ),
        sa.ForeignKeyConstraint(
            ["control_id"],
            ["ai_family_experience_release_set_controls.control_id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_release_set_id"],
            ["ai_family_experience_release_sets.release_set_id"],
        ),
        sa.ForeignKeyConstraint(
            ["target_release_set_id"],
            ["ai_family_experience_release_sets.release_set_id"],
        ),
        sa.PrimaryKeyConstraint("environment", "use_case", "data_class"),
        sa.UniqueConstraint("transition_id"),
    )
    op.create_index(
        "uq_ai_release_set_transition_idempotency",
        "ai_family_experience_release_set_transitions",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_ai_release_set_transition_idempotency",
        table_name="ai_family_experience_release_set_transitions",
    )
    op.drop_table("ai_family_experience_release_set_transitions")
