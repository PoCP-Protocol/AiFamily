"""Persistence for the Product Intelligence Course Content aggregate.

One table, ``course_content``, for the aggregate root defined in
``backend/domains/product_intelligence/domain/course_content.py``. The
aggregate's variable-length nested structure (``lessons``, each carrying its
own ``media_asset_ids``/``tool_refs``) is stored as a single ``JSONB`` column
rather than normalized into child tables: lessons are never queried or
joined against independently of their owning course (the repository's own
interface only ever loads/saves a whole ``CourseContent``), so a child table
would buy referential integrity this domain does not need at the cost of a
reconstruction join on every read. ``assessment_criteria`` /
``outcome_metrics`` / ``content_accuracy_claim_refs`` are simple string-tuple
fields and stored as ``JSONB`` for the same reason.

Enums are stored as ``VARCHAR`` + ``CHECK`` constraints, matching this
repository's existing style (see e.g. 0055's ``status`` check) rather than
native ``CREATE TYPE ... AS ENUM``, so a future status value is a
constraint-only migration and never a type-alteration migration.

Multi-tenant scope mirrors 0055: every row carries ``tenant_scope`` and the
primary key is ``(tenant_scope, id)`` so a PostgreSQL adapter can enforce the
same visibility rule the in-memory fake already enforces (``course.tenant_scope
== tenant_scope``).

Revision ID: 0056_course_content
Revises: 0055_family_need_domain
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0056_course_content"
down_revision: str | None = "0055_family_need_domain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_VALUES = ("DRAFT", "UNDER_REVIEW", "PUBLISHED", "RETIRED")


def _check_in(column: str, values: tuple[str, ...], name: str) -> sa.CheckConstraint:
    quoted = ",".join(f"'{value}'" for value in values)
    return sa.CheckConstraint(f"{column} in ({quoted})", name=name)


def upgrade() -> None:
    op.create_table(
        "course_content",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_scope", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("product_component_id", sa.String(length=64), nullable=True),
        sa.Column("problem_statement", sa.Text(), nullable=False),
        sa.Column("assessment_criteria", sa.JSON(), nullable=False),
        sa.Column("learning_goal", sa.Text(), nullable=False),
        sa.Column("lessons", sa.JSON(), nullable=False),
        sa.Column("ai_coach_prompt_ref", sa.String(length=256), nullable=True),
        sa.Column("review_cadence", sa.String(length=256), nullable=False),
        sa.Column("outcome_metrics", sa.JSON(), nullable=False),
        sa.Column("content_accuracy_claim_refs", sa.JSON(), nullable=False),
        sa.Column("reviewed_by", sa.String(length=128), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        _check_in("status", _STATUS_VALUES, "ck_course_content_status"),
        sa.CheckConstraint("version >= 1", name="ck_course_content_version_positive"),
        sa.PrimaryKeyConstraint("tenant_scope", "id"),
    )
    op.create_index(
        "ix_course_content_tenant_status",
        "course_content",
        ["tenant_scope", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_course_content_tenant_status", table_name="course_content")
    op.drop_table("course_content")
