"""Attach active release-set evidence to model attempts and budget holds."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048_ai_runtime_release_evidence"
down_revision: str | None = "0047_ai_release_set_deployments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("ai_model_attempts", "ai_model_budget_reservations"):
        op.add_column(table, sa.Column("release_set_id", sa.String(length=64)))
        op.add_column(table, sa.Column("bundle_id", sa.String(length=64)))
        op.add_column(table, sa.Column("deployment_receipt_id", sa.String(length=64)))
    op.add_column(
        "ai_model_budget_reservations",
        sa.Column("runtime_config_digest", sa.String(length=64)),
    )
    op.create_index(
        "ix_ai_model_attempts_release_set_id",
        "ai_model_attempts",
        ["release_set_id"],
    )
    op.create_index(
        "ix_ai_model_budget_reservations_release_set_id",
        "ai_model_budget_reservations",
        ["release_set_id"],
    )
    for column in (
        "routing_policy_version",
        "rate_card_version",
        "budget_policy_version",
    ):
        op.alter_column(
            "ai_family_experience_release_bundles",
            column,
            server_default=None,
        )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_model_budget_reservations_release_set_id",
        table_name="ai_model_budget_reservations",
    )
    op.drop_index(
        "ix_ai_model_attempts_release_set_id",
        table_name="ai_model_attempts",
    )
    op.drop_column("ai_model_budget_reservations", "runtime_config_digest")
    for table in ("ai_model_budget_reservations", "ai_model_attempts"):
        op.drop_column(table, "deployment_receipt_id")
        op.drop_column(table, "bundle_id")
        op.drop_column(table, "release_set_id")
