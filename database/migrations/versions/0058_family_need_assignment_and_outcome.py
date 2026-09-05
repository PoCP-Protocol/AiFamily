"""Persistence for the remaining Family Need aggregates: AssignmentPlan (N4)
and FamilyConfirmedOutcome (N6/N7).

``family_need_assignment_plans`` and ``family_need_confirmed_outcomes``
complete the durable persistence for
``backend/domains/family_need/domain/entities.py``; the other four aggregates
(need_signals / family_needs / need_profiles / solution_drafts) already have
tables from 0055. ``component_refs`` is a variable-length list of
``SolutionComponentRef`` and is stored as ``JSON`` (JSONB on PostgreSQL),
matching the existing "structure not queried directly, so no child table"
convention used by ``solution_drafts.components`` in 0055 and
``course_content.lessons`` in 0056. Enums are ``VARCHAR`` + ``CHECK``,
matching 0055/0056's style rather than a native ``CREATE TYPE ... AS ENUM``.

Revision ID: 0058_family_need_assignment_and_outcome
Revises: 0057_ai_growth_plan_draft_reviews
Create Date: 2026-09-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0058_family_need_assignment_and_outcome"
down_revision: str | None = "0057_ai_growth_plan_draft_reviews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FAMILY_OUTCOME_DECISION_VALUES = ("HELPED", "PARTIALLY_HELPED", "DID_NOT_HELP")


def _check_in(column: str, values: tuple[str, ...], name: str) -> sa.CheckConstraint:
    quoted = ",".join(f"'{value}'" for value in values)
    return sa.CheckConstraint(f"{column} in ({quoted})", name=name)


def upgrade() -> None:
    op.create_table(
        "family_need_assignment_plans",
        sa.Column("plan_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("need_id", sa.String(length=64), nullable=False),
        sa.Column("draft_id", sa.String(length=64), nullable=False),
        sa.Column("component_refs", sa.JSON(), nullable=False),
        sa.Column("authorization_basis", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "plan_id"),
    )
    op.create_index(
        "ix_family_need_assignment_plans_family_scope",
        "family_need_assignment_plans",
        ["tenant_id", "family_id", "need_id"],
    )

    op.create_table(
        "family_need_confirmed_outcomes",
        sa.Column("outcome_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("purpose", sa.String(length=128), nullable=False),
        sa.Column("consent_version", sa.String(length=160), nullable=False),
        sa.Column("data_class", sa.String(length=32), nullable=False),
        sa.Column("locale", sa.String(length=16), nullable=False),
        sa.Column("region", sa.String(length=8), nullable=False),
        sa.Column("subject_person_ids", sa.JSON(), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("environment", sa.String(length=32), nullable=False),
        sa.Column("provenance_ref", sa.String(length=256), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("causation_id", sa.String(length=128), nullable=True),
        sa.Column("need_id", sa.String(length=64), nullable=False),
        sa.Column("draft_id", sa.String(length=64), nullable=True),
        sa.Column("fulfillment_ref", sa.Text(), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("confirmed_by", sa.String(length=128), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("family_note", sa.Text(), nullable=True),
        _check_in(
            "data_class",
            (
                "PUBLIC",
                "INTERNAL",
                "FAMILY_PRIVATE",
                "SENSITIVE_PERSONAL_DATA",
                "MINOR_PERSONAL_DATA",
            ),
            "ck_family_need_confirmed_outcomes_data_class",
        ),
        _check_in(
            "actor_type",
            (
                "FAMILY_MEMBER",
                "FAMILY_GUARDIAN",
                "OPERATOR",
                "PROVIDER",
                "SYSTEM",
                "AI",
            ),
            "ck_family_need_confirmed_outcomes_actor_type",
        ),
        _check_in(
            "decision",
            _FAMILY_OUTCOME_DECISION_VALUES,
            "ck_family_need_confirmed_outcomes_decision",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "outcome_id"),
    )
    op.create_index(
        "ix_family_need_confirmed_outcomes_need_scope",
        "family_need_confirmed_outcomes",
        ["tenant_id", "family_id", "need_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_family_need_confirmed_outcomes_need_scope",
        table_name="family_need_confirmed_outcomes",
    )
    op.drop_table("family_need_confirmed_outcomes")

    op.drop_index(
        "ix_family_need_assignment_plans_family_scope",
        table_name="family_need_assignment_plans",
    )
    op.drop_table("family_need_assignment_plans")
