"""Persist assessment AI interpretation run metadata.

Creates the `ai_run_ledger` table written to by
`backend/domains/assessment/infrastructure/ai_run_ledger.py`
(`SqlAlchemyAiRunLedger`). This is a deliberately domain-neutral,
runtime-diagnostic audit trail for individual AI Runtime calls (one row per
`interpret()` call, keyed by an opaque `run_id`) — distinct in purpose and
shape from `family_assessment_ai_runs` (baseline 0049), which stores the
tenant/family-scoped derived-draft *content* of an AI interpretation
(`output_body`, `source_refs`, evidence linkage) for UI-03. `ai_run_ledger`
has no tenant/family/evidence foreign keys by design: it exists purely to
answer "did this AI call succeed, and how many tokens did it cost", not to
carry family-facing derived content, so it does not follow this repo's
`<domain>_<what>` naming convention that baseline tables use.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0069_ai_run_ledger"
down_revision: str | None = "0068_reviewed_understanding_signal"
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
