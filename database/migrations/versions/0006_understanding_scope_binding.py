"""Bind reviewed understanding to its canonical scope session.

Revision ID: 0006_understanding_scope_binding
Revises: 0005_reviewed_signal
Create Date: 2026-09-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_understanding_scope_binding"
down_revision: str | None = "0005_reviewed_signal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "assessment_reviewed_understanding_signals"
SCOPE_CHECK = "ck_reviewed_understanding_scope_binding"
RUN_INDEX = "idx_reviewed_understanding_run_timeline"


def upgrade() -> None:
    op.alter_column(
        TABLE_NAME,
        "assessment_session_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.add_column(
        TABLE_NAME,
        sa.Column("understanding_run_ref", sa.String(length=256), nullable=True),
    )
    op.create_check_constraint(
        SCOPE_CHECK,
        TABLE_NAME,
        "(scope_ref = 'family://' || tenant_id::text || '/' || family_id::text "
        "|| '/assessment' AND assessment_session_id IS NOT NULL "
        "AND understanding_run_ref IS NULL) OR "
        "(scope_ref = 'family://' || tenant_id::text || '/' || family_id::text "
        "|| '/problem-understanding' AND assessment_session_id IS NULL "
        "AND NULLIF(BTRIM(understanding_run_ref), '') IS NOT NULL)",
    )
    op.create_index(
        RUN_INDEX,
        TABLE_NAME,
        ["tenant_id", "family_id", "understanding_run_ref", sa.text("reviewed_at DESC")],
        postgresql_where=sa.text("understanding_run_ref IS NOT NULL"),
    )


def downgrade() -> None:
    # The parent schema cannot represent independent problem-understanding
    # bindings. Removing those rows is the explicit rollback boundary; existing
    # Assessment-scoped receipts remain intact.
    op.execute(sa.text(f"DELETE FROM {TABLE_NAME} WHERE assessment_session_id IS NULL"))
    op.drop_index(RUN_INDEX, table_name=TABLE_NAME)
    op.drop_constraint(SCOPE_CHECK, TABLE_NAME, type_="check")
    op.drop_column(TABLE_NAME, "understanding_run_ref")
    op.alter_column(
        TABLE_NAME,
        "assessment_session_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
