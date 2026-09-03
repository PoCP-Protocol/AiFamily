"""family_experience_signals: cross-family, de-identified "did this help a
family like mine" signals — every verdict (HELPED/PARTIALLY_HELPED/
DID_NOT_HELP), not only the negative half `product_improvement_candidates`
tracks.

This table deliberately carries no family/tenant/child identity column — see
``backend/domains/product_intelligence/domain/family_experience_signal.py``'s
privacy invariant docstring. It is written from
``backend/domains/family_need/api/routes.py::confirm_family_outcome`` for
every decision the family confirms, and only the already de-identified
component/category/tier facts are copied across — never ``family_id``,
``tenant_id``, subject identity, or the family's free-text note.

Revision ID: 0064_family_experience_signals
Revises: 0063_achievement_feedback_human_gate
Create Date: 2026-09-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0064_family_experience_signals"
down_revision: str | None = "0063_achievement_feedback_human_gate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMPONENT_SHAPE_VALUES = ("PRODUCT", "SERVICE", "SOLUTION")
_DECISION_VALUES = ("HELPED", "PARTIALLY_HELPED", "DID_NOT_HELP")
_CATEGORY_VALUES = (
    "EDUCATION",
    "FAMILY_RELATIONSHIP",
    "GROWTH_COMPANIONSHIP",
    "LIFE_SUPPORT",
    "SERVICE_SUPPORT",
    "OTHER",
)
_INTERVENTION_TIER_VALUES = (
    "UNIVERSAL",
    "LIGHT_GUIDANCE",
    "BRIEF_CONSULTATION",
    "INTENSIVE_SUPPORT",
    "ENHANCED_SUPPORT",
)


def _check_in(column: str, values: tuple[str, ...], name: str) -> sa.CheckConstraint:
    quoted = ",".join(f"'{value}'" for value in values)
    return sa.CheckConstraint(f"{column} in ({quoted})", name=name)


def upgrade() -> None:
    op.create_table(
        "family_experience_signals",
        sa.Column("signal_id", sa.String(length=64), nullable=False),
        sa.Column("component_id", sa.String(length=256), nullable=False),
        sa.Column("component_shape", sa.String(length=16), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("intervention_tier", sa.String(length=32), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        _check_in(
            "component_shape",
            _COMPONENT_SHAPE_VALUES,
            "ck_family_experience_signals_component_shape",
        ),
        _check_in("decision", _DECISION_VALUES, "ck_family_experience_signals_decision"),
        _check_in("category", _CATEGORY_VALUES, "ck_family_experience_signals_category"),
        _check_in(
            "intervention_tier",
            _INTERVENTION_TIER_VALUES,
            "ck_family_experience_signals_intervention_tier",
        ),
        sa.PrimaryKeyConstraint("signal_id"),
    )
    op.create_index(
        "ix_family_experience_signals_category_component",
        "family_experience_signals",
        ["category", "component_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_family_experience_signals_category_component",
        table_name="family_experience_signals",
    )
    op.drop_table("family_experience_signals")
