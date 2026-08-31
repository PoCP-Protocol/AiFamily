"""Persist one completed Assessment AI run per interpretation call.

Revision ID: 0004_ai_run_ledger
Revises: 0003_service_booking_additions
Create Date: 2026-09-01

The Assessment adapter introduced a real PostgreSQL writer for
``ai_run_ledger``, but the table never entered the canonical Alembic chain.
This revision owns only that missing persistence object.  It deliberately
does not alter the immutable 62-file legacy baseline.

``assessment_session_id`` remains a bounded string because the Python
Assessment contract currently carries opaque identifiers (including prefixed
and test identifiers), not the UUID-only key used by the later UI assessment
tables in the legacy snapshot.  Adding a foreign key would therefore reject
valid values already accepted by the domain contract.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_ai_run_ledger"
down_revision: str | None = "0003_service_booking_additions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "ai_run_ledger"


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column("run_id", sa.String(length=128), primary_key=True),
        sa.Column("assessment_session_id", sa.String(length=128), nullable=False),
        sa.Column("service_depth", sa.String(length=48), nullable=False),
        sa.Column("generator", sa.String(length=32), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "service_depth IN ('BASIC_SELF_CHECK', 'DEEP_AI_INTERPRETATION')",
            name="ck_ai_run_ledger_service_depth",
        ),
        sa.CheckConstraint(
            "generator IN ('deterministic', 'gateway')",
            name="ck_ai_run_ledger_generator",
        ),
        sa.CheckConstraint(
            "outcome IN ('success', 'boundary_violation', 'provider_error')",
            name="ck_ai_run_ledger_outcome",
        ),
        sa.CheckConstraint(
            "completed_at >= started_at",
            name="ck_ai_run_ledger_completion_order",
        ),
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_ai_run_ledger_input_tokens",
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_ai_run_ledger_output_tokens",
        ),
    )
    op.create_index(
        "idx_ai_run_ledger_session_started",
        TABLE_NAME,
        ["assessment_session_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_ai_run_ledger_session_started", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
