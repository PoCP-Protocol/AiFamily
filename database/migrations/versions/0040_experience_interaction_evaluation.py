"""Allow evaluation interactions while keeping downgrade data-safe.

Revision ID: 0040_interaction_evaluation
Revises: 0039_competitor_evidence
Create Date: 2026-09-03

Evaluation receipts are append-only AI-runtime evidence, not business facts.
The upgrade only widens the existing interaction-type check constraint.  The
downgrade fails closed when evaluation evidence exists: silently deleting or
rewriting that evidence would make the audit trail dishonest.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040_interaction_evaluation"
down_revision: str | None = "0039_competitor_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "ck_experience_run_interaction_type"
_OLD_TYPES = "'decision', 'feedback', 'human_review', 'delete'"
_NEW_TYPES = f"{_OLD_TYPES}, 'evaluation'"


def _replace_constraint(allowed_types: str) -> None:
    op.drop_constraint(
        _CONSTRAINT,
        "experience_run_interactions",
        type_="check",
    )
    op.create_check_constraint(
        _CONSTRAINT,
        "experience_run_interactions",
        f"interaction_type IN ({allowed_types})",
    )


def upgrade() -> None:
    _replace_constraint(_NEW_TYPES)


def downgrade() -> None:
    has_evaluation = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS ("
                "SELECT 1 FROM experience_run_interactions "
                "WHERE interaction_type = 'evaluation'"
                ")"
            )
        )
        .scalar_one()
    )
    if has_evaluation:
        raise RuntimeError(
            "0040 downgrade refused: evaluation interactions exist; "
            "preserve or explicitly migrate the evidence before retrying"
        )
    _replace_constraint(_OLD_TYPES)
