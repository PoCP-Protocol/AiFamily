"""Add real-resolution columns to family_need_assignment_plans (N4).

``AssignmentPlan`` (0058) previously recorded only the family's authorization
for an assignment (``authorization_basis``), never the resource fulfilment
actually assigned it to. `resolved_slot_id` / `resolved_booking_ref` /
`resolved_order_intent_ref` are filled in exactly once, after
`need_fulfillment_flow.fulfil_confirmed_draft` succeeds, via
`AssignmentPlan.resolve()` — see
`backend/domains/family_need/api/routes.py::confirm_solution_draft` and
`backend/domains/family_need/domain/entities.py::AssignmentPlan`. All three
are nullable: a plan whose fulfilment has not (yet, or ever) succeeded keeps
them ``NULL`` rather than fabricating a value.

Revision ID: 0059_family_need_assignment_plan_resolution
Revises: 0058_family_need_assignment_and_outcome
Create Date: 2026-09-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0059_family_need_assignment_plan_resolution"
down_revision: str | None = "0058_family_need_assignment_and_outcome"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "family_need_assignment_plans",
        sa.Column("resolved_slot_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "family_need_assignment_plans",
        sa.Column("resolved_booking_ref", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "family_need_assignment_plans",
        sa.Column("resolved_order_intent_ref", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("family_need_assignment_plans", "resolved_order_intent_ref")
    op.drop_column("family_need_assignment_plans", "resolved_booking_ref")
    op.drop_column("family_need_assignment_plans", "resolved_slot_id")
