"""Widen `family_growth_hypothesis_decisions.decision_type` for ADR-0158
Slice A's `FAMILY_DECISION` node.

Baseline 0044 (`database/baseline/0044_ui03_growth_hypothesis_confirmation.sql`)
created `family_growth_hypothesis_decisions` with
`decision_type varchar(24) CHECK (decision_type IN ('CONFIRM','DISMISS'))`.
The frontend UI-03/UI-04 candidate work already ships a five-value contract
(`CONFIRM | EDIT | PARTIAL | DISMISS | LATER`) for the growth-hypothesis
decision endpoint — see
`backend/domains/assessment/application/growth_hypothesis_commands.py`
module docstring for what each of the three new values writes.

This migration:

1. Drops and recreates the `decision_type` CHECK constraint to allow the
   three new values, matching the widened
   `GrowthHypothesisDecisionType` Literal in
   `backend/domains/assessment/domain/value_objects.py`.
2. Adds a nullable `parent_note text` column. It carries the guardian's
   free-text note: for EDIT this *is* the rewritten understanding statement
   that becomes `growth_intents.goal_text` instead of the AI's draft; for
   PARTIAL/LATER it optionally records which part was accepted / why the
   guardian is deferring. Nullable because CONFIRM/DISMISS never populate it
   and existing CONFIRM/DISMISS rows have no such note to backfill.

Downgrade drops the column and restores the original two-value CHECK. It
fails closed (raises) if any row already holds one of the three new
decision_type values or a non-null parent_note, rather than silently
discarding that data.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0072_growth_hypothesis_decision_partial_edit_later"
down_revision: str | None = "0071_identity_sessions_family_scope_ref"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "family_growth_hypothesis_decisions"
_CHECK_NAME = f"{_TABLE}_decision_type_check"
_OLD_VALUES = ("CONFIRM", "DISMISS")
_NEW_VALUES = ("CONFIRM", "EDIT", "PARTIAL", "DISMISS", "LATER")


def upgrade() -> None:
    op.drop_constraint(_CHECK_NAME, _TABLE, type_="check")
    op.create_check_constraint(
        _CHECK_NAME,
        _TABLE,
        sa.column("decision_type").in_(_NEW_VALUES),
    )
    op.add_column(_TABLE, sa.Column("parent_note", sa.Text(), nullable=True))


def downgrade() -> None:
    """Reverse the widening. Fails closed if any row already uses a new
    decision_type value or has a non-null parent_note — reversing this
    migration would otherwise silently discard that data.
    """

    conn = op.get_bind()
    new_only = tuple(v for v in _NEW_VALUES if v not in _OLD_VALUES)
    blocking = conn.execute(
        sa.text(
            f"select count(*) from {_TABLE} "
            "where decision_type = any(:new_only) or parent_note is not null"
        ),
        {"new_only": list(new_only)},
    ).scalar_one()
    if blocking:
        raise RuntimeError(
            f"cannot downgrade {revision}: {blocking} row(s) in {_TABLE} use a "
            "PARTIAL/EDIT/LATER decision_type or a non-null parent_note"
        )

    op.drop_column(_TABLE, "parent_note")
    op.drop_constraint(_CHECK_NAME, _TABLE, type_="check")
    op.create_check_constraint(
        _CHECK_NAME,
        _TABLE,
        sa.column("decision_type").in_(_OLD_VALUES),
    )
