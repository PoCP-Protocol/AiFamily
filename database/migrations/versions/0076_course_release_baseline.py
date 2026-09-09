"""Persist immutable course ReleaseBaseline PLM manifests."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0076_course_release_baseline"
down_revision: str | None = "0075_course_content_lineage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "course_release_baseline",
        sa.Column("release_id", sa.String(length=256), nullable=False),
        sa.Column("tenant_scope", sa.String(length=128), nullable=False),
        sa.Column("package_id", sa.String(length=256), nullable=False),
        sa.Column("package_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("component_refs", sa.JSON(), nullable=False),
        sa.Column("skill_refs", sa.JSON(), nullable=False),
        sa.Column("blueprint_version_id", sa.String(length=256), nullable=False),
        sa.Column("model_refs", sa.JSON(), nullable=False),
        sa.Column("prompt_refs", sa.JSON(), nullable=False),
        sa.Column("schema_refs", sa.JSON(), nullable=False),
        sa.Column("knowledge_refs", sa.JSON(), nullable=False),
        sa.Column("migration_refs", sa.JSON(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("runbook_ref", sa.String(length=256), nullable=False),
        sa.Column("rollback_ref", sa.String(length=256), nullable=False),
        sa.Column("rollback_target_ref", sa.String(length=256), nullable=True),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("generated_by", sa.String(length=128), nullable=True),
        sa.Column("approved_by", sa.String(length=128), nullable=True),
        sa.Column("human_gate_ref", sa.String(length=256), nullable=True),
        sa.PrimaryKeyConstraint("tenant_scope", "release_id"),
        sa.CheckConstraint(
            "status in ('DRAFT','REVIEWED','RELEASED','PAUSED','RETIRED')",
            name="ck_course_release_baseline_status",
        ),
    )
    op.create_index(
        "ix_course_release_baseline_tenant_package",
        "course_release_baseline",
        ["tenant_scope", "package_id", "package_version"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_course_release_baseline_tenant_package",
        table_name="course_release_baseline",
    )
    op.drop_table("course_release_baseline")
