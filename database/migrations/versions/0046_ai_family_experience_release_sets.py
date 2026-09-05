"""Persist immutable atomic family-experience release sets."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0046_ai_experience_release_sets"
down_revision: str | None = "0045_ai_bundle_runtime_policies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_family_experience_release_sets",
        sa.Column("release_set_id", sa.String(length=64), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("use_case", sa.String(length=256), nullable=False),
        sa.Column("data_class", sa.String(length=64), nullable=False),
        sa.Column("provider_ids", sa.JSON(), nullable=False),
        sa.Column("bundle_ids", sa.JSON(), nullable=False),
        sa.Column("routing_policy_version", sa.String(length=128), nullable=False),
        sa.Column("route_config_digest", sa.String(length=64), nullable=False),
        sa.Column("rate_card_version", sa.String(length=128), nullable=False),
        sa.Column("rate_card_digest", sa.String(length=64), nullable=False),
        sa.Column("budget_policy_version", sa.String(length=128), nullable=False),
        sa.Column("budget_policy_digest", sa.String(length=64), nullable=False),
        sa.Column("agent_id", sa.String(length=256), nullable=False),
        sa.Column("prompt_ref", sa.String(length=256), nullable=False),
        sa.Column("prompt_version", sa.String(length=128), nullable=False),
        sa.Column("schema_ref", sa.String(length=256), nullable=False),
        sa.Column("schema_version", sa.String(length=128), nullable=False),
        sa.Column("safety_policy_version", sa.String(length=128), nullable=False),
        sa.Column("safety_policy_digest", sa.String(length=64), nullable=False),
        sa.Column("knowledge_refs", sa.JSON(), nullable=False),
        sa.Column("asset_digest", sa.String(length=64), nullable=False),
        sa.Column("runtime_config_digest", sa.String(length=64), nullable=False),
        sa.Column("draft_only", sa.Boolean(), nullable=False),
        sa.Column("may_mutate_business_state", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "draft_only = true AND may_mutate_business_state = false",
            name="ck_ai_family_experience_release_sets_draft_boundary",
        ),
        sa.PrimaryKeyConstraint("release_set_id"),
    )
    op.create_index(
        "ix_ai_family_experience_release_sets_scope",
        "ai_family_experience_release_sets",
        ["environment", "use_case", "data_class"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_family_experience_release_sets_scope",
        table_name="ai_family_experience_release_sets",
    )
    op.drop_table("ai_family_experience_release_sets")
