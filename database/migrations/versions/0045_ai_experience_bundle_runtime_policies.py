"""Bind experience release bundles to route, rate and budget policy versions."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045_ai_bundle_runtime_policies"
down_revision: str | None = "0044_ai_model_budget_reservations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table = "ai_family_experience_release_bundles"
    legacy_default = "legacy-unbound"
    op.add_column(
        table,
        sa.Column(
            "routing_policy_version",
            sa.String(length=128),
            nullable=False,
            server_default=legacy_default,
        ),
    )
    op.add_column(
        table,
        sa.Column(
            "rate_card_version",
            sa.String(length=128),
            nullable=False,
            server_default=legacy_default,
        ),
    )
    op.add_column(
        table,
        sa.Column(
            "budget_policy_version",
            sa.String(length=128),
            nullable=False,
            server_default=legacy_default,
        ),
    )


def downgrade() -> None:
    table = "ai_family_experience_release_bundles"
    op.drop_column(table, "budget_policy_version")
    op.drop_column(table, "rate_card_version")
    op.drop_column(table, "routing_policy_version")
