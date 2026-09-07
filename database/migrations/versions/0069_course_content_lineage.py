"""Add optional CourseSystem lineage to CourseContent."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0069_course_content_lineage"
down_revision: str | None = "0068_course_system"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "course_content",
        sa.Column("course_system_version_ref", sa.String(length=256), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("course_content", "course_system_version_ref")
