"""Persist reviewed content-addressed system policy and knowledge materials."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0052_ai_execution_materials"
down_revision: str | None = "0051_ai_release_transition_state_machine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    lifecycle = "status IN ('DRAFT', 'REVIEW', 'PUBLISHED', 'RETIRED')"
    op.create_table(
        "ai_system_policy_materials",
        sa.Column("policy_ref", sa.String(length=256), nullable=False),
        sa.Column("use_case", sa.String(length=256), nullable=False),
        sa.Column("agent_id", sa.String(length=256), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("locale", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reviewer", sa.String(length=256), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_digest", sa.String(length=64), nullable=False),
        sa.CheckConstraint(lifecycle, name="ck_ai_system_policy_material_status"),
        sa.CheckConstraint(
            "status <> 'PUBLISHED' OR (reviewer IS NOT NULL AND effective_at IS NOT NULL)",
            name="ck_ai_system_policy_material_publish_gate",
        ),
        sa.PrimaryKeyConstraint("policy_ref"),
        sa.UniqueConstraint("content_digest"),
    )
    op.create_index(
        "ix_ai_system_policy_materials_use_case",
        "ai_system_policy_materials",
        ["use_case"],
    )
    op.create_table(
        "ai_knowledge_execution_materials",
        sa.Column("knowledge_ref", sa.String(length=256), nullable=False),
        sa.Column("use_case", sa.String(length=256), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.String(length=256), nullable=False),
        sa.Column("license_ref", sa.String(length=256), nullable=False),
        sa.Column("evidence_level", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reviewer", sa.String(length=256), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_digest", sa.String(length=64), nullable=False),
        sa.CheckConstraint(lifecycle, name="ck_ai_knowledge_material_status"),
        sa.CheckConstraint(
            "scope = 'SHARED'",
            name="ck_ai_knowledge_material_shared_only",
        ),
        sa.CheckConstraint(
            "status <> 'PUBLISHED' OR (reviewer IS NOT NULL AND effective_at IS NOT NULL)",
            name="ck_ai_knowledge_material_publish_gate",
        ),
        sa.PrimaryKeyConstraint("knowledge_ref"),
        sa.UniqueConstraint("content_digest"),
    )
    op.create_index(
        "ix_ai_knowledge_execution_materials_use_case",
        "ai_knowledge_execution_materials",
        ["use_case"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_knowledge_execution_materials_use_case",
        table_name="ai_knowledge_execution_materials",
    )
    op.drop_table("ai_knowledge_execution_materials")
    op.drop_index(
        "ix_ai_system_policy_materials_use_case",
        table_name="ai_system_policy_materials",
    )
    op.drop_table("ai_system_policy_materials")
