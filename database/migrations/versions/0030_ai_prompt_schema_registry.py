"""Persist immutable Prompt/Schema registry versions.

Revision ID: 0030_ai_prompt_schema_registry
Revises: 0029_ai_experience_feedback_projections
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_ai_prompt_schema_registry"
down_revision: str | None = "0029_ai_experience_feedback_projections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_prompt_bundles",
        sa.Column("prompt_ref", sa.String(length=256), nullable=False),
        sa.Column("version", sa.String(length=128), nullable=False),
        sa.Column("use_case", sa.String(length=128), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("system_policy_ref", sa.String(length=256), nullable=False),
        sa.Column("knowledge_refs", sa.JSON(), nullable=False),
        sa.Column("input_contract_ref", sa.String(length=256), nullable=False),
        sa.Column("output_schema_ref", sa.String(length=256), nullable=False),
        sa.Column("safety_policy_version", sa.String(length=128), nullable=False),
        sa.Column("locale", sa.String(length=32), nullable=False),
        sa.Column("author", sa.String(length=128), nullable=False),
        sa.Column("reviewer", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("change_reason", sa.String(length=512), nullable=False),
        sa.Column("superseded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("prompt_ref", "version"),
    )
    op.create_index(
        "ix_ai_prompt_bundles_binding",
        "ai_prompt_bundles",
        ["use_case", "agent_id", "status", "effective_at"],
    )

    op.create_table(
        "ai_schema_definitions",
        sa.Column("schema_ref", sa.String(length=256), nullable=False),
        sa.Column("version", sa.String(length=128), nullable=False),
        sa.Column("use_case", sa.String(length=128), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("object_type", sa.String(length=128), nullable=False),
        sa.Column("required_fields", sa.JSON(), nullable=False),
        sa.Column("evidence_refs_non_empty", sa.Boolean(), nullable=False),
        sa.Column("forbidden_fields", sa.JSON(), nullable=False),
        sa.Column("allowed_fields", sa.JSON(), nullable=False),
        sa.Column("enum_constraints", sa.JSON(), nullable=False),
        sa.Column("boundary_labels", sa.JSON(), nullable=False),
        sa.Column("human_gate_rule", sa.String(length=32), nullable=False),
        sa.Column("json_schema", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("author", sa.String(length=128), nullable=False),
        sa.Column("reviewer", sa.String(length=128), nullable=True),
        sa.Column("change_reason", sa.String(length=512), nullable=False),
        sa.Column("evidence_refs_field", sa.String(length=128), nullable=False),
        sa.Column("visibility", sa.String(length=64), nullable=False),
        sa.Column("write_back_target", sa.String(length=128), nullable=False),
        sa.Column("validator_ref", sa.String(length=256), nullable=False),
        sa.Column("text_equivalent_required", sa.Boolean(), nullable=False),
        sa.Column("superseded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("schema_ref", "version"),
    )
    op.create_index(
        "ix_ai_schema_definitions_binding",
        "ai_schema_definitions",
        ["use_case", "agent_id", "status", "effective_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_schema_definitions_binding", table_name="ai_schema_definitions")
    op.drop_table("ai_schema_definitions")
    op.drop_index("ix_ai_prompt_bundles_binding", table_name="ai_prompt_bundles")
    op.drop_table("ai_prompt_bundles")
