"""product_improvement_candidates: cross-family, de-identified "did not
help" signals for product/content teams.

This table deliberately carries no family/tenant/child identity column — see
``backend/domains/product_intelligence/domain/improvement_candidate.py``'s
privacy invariant docstring. It is written from
``backend/domains/family_need/api/routes.py::confirm_family_outcome`` only
when a family's own N6/N7 verdict is ``DID_NOT_HELP``, and only the already
de-identified component/category/tier facts are copied across — never
``family_id``, ``tenant_id``, subject identity, or the family's free-text
note.

Revision ID: 0060_product_improvement_candidates
Revises: 0059_family_need_assignment_plan_resolution
Create Date: 2026-09-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0060_product_improvement_candidates"
down_revision: str | None = "0059_family_need_assignment_plan_resolution"
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
        "product_improvement_candidates",
        sa.Column("candidate_id", sa.String(length=64), nullable=False),
        sa.Column("component_id", sa.String(length=256), nullable=False),
        sa.Column("component_shape", sa.String(length=16), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("intervention_tier", sa.String(length=32), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        _check_in(
            "component_shape",
            _COMPONENT_SHAPE_VALUES,
            "ck_product_improvement_candidates_component_shape",
        ),
        _check_in("decision", _DECISION_VALUES, "ck_product_improvement_candidates_decision"),
        _check_in("category", _CATEGORY_VALUES, "ck_product_improvement_candidates_category"),
        _check_in(
            "intervention_tier",
            _INTERVENTION_TIER_VALUES,
            "ck_product_improvement_candidates_intervention_tier",
        ),
        sa.PrimaryKeyConstraint("candidate_id"),
    )
    op.create_index(
        "ix_product_improvement_candidates_component",
        "product_improvement_candidates",
        ["component_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_product_improvement_candidates_component",
        table_name="product_improvement_candidates",
    )
    op.drop_table("product_improvement_candidates")
