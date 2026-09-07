"""Persist versioned CourseSystem curriculum and courseware BOM contracts."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0068_course_system"
down_revision: str | None = "0067_family_support_needs_v4_item_bank"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "course_system",
        sa.Column("system_id", sa.String(length=128), nullable=False),
        sa.Column("tenant_scope", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("product_package_version_ref", sa.String(length=256), nullable=False),
        sa.Column("stages", sa.JSON(), nullable=False),
        sa.Column("bom", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_scope", "system_id"),
        sa.CheckConstraint("version >= 1", name="ck_course_system_version_positive"),
    )
    op.create_index(
        "ix_course_system_tenant_version",
        "course_system",
        ["tenant_scope", "version"],
    )
    op.add_column("course_content", sa.Column("course_system_version_ref", sa.String(length=256), nullable=True))


def downgrade() -> None:
    op.drop_column("course_content", "course_system_version_ref")
    op.drop_index("ix_course_system_tenant_version", table_name="course_system")
    op.drop_table("course_system")
