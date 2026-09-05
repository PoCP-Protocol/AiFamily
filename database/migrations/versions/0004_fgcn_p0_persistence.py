"""FGCN P0 persistence columns and case-level allocation correction.

Revision ID: 0004_fgcn_p0_persistence
Revises: 0003_service_booking_additions
Create Date: 2026-08-30

The historical FGCN tables are already present in the baseline.  This
post-baseline revision adds only information the executable P0 contracts need:

* ``service_tasks.acceptance_criteria`` preserves the frozen criteria instead
  of making them an in-memory-only claim;
* ``task_assignments`` records the Human Gate request and confirming actor;
* ``service_contributions.delivery_ref`` preserves which delivery produced a
  contribution (the historical contribution table did not retain that link);
* ``service_cases`` retains tenant/scope metadata required to re-establish the
  Human Gate boundary after a process restart;
* ``service_contribution_allocations.task_ref`` becomes nullable because the
  case-level PLATFORM/CONTENT_RESOURCE/CASE_STEWARD/QUALITY_RESERVE lines have
  no task basis; using a fabricated task would corrupt the allocation meaning.

The baseline files remain immutable historical artefacts.  Existing rows are
backfilled with an empty acceptance-criteria list and therefore fail closed
when loaded through the P0 repository until a real task configuration is
provided.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_fgcn_p0_persistence"
down_revision: str | None = "0003_service_booking_additions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "service_cases",
        sa.Column("tenant_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "service_cases",
        sa.Column("scope_purpose", sa.String(length=96), nullable=True),
    )
    op.add_column(
        "service_cases",
        sa.Column("consent_version", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "service_cases",
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "service_tasks",
        sa.Column(
            "acceptance_criteria",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_check_constraint(
        "ck_service_tasks_acceptance_criteria_array",
        "service_tasks",
        "jsonb_typeof(acceptance_criteria) = 'array'",
    )
    op.add_column(
        "task_assignments",
        sa.Column("accepted_by_actor_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "task_assignments",
        sa.Column("source_request_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "service_contributions",
        sa.Column("delivery_ref", sa.String(length=160), nullable=True),
    )
    op.create_index(
        "uq_service_contributions_delivery_ref",
        "service_contributions",
        ["delivery_ref"],
        unique=True,
        postgresql_where=sa.text("delivery_ref IS NOT NULL"),
        sqlite_where=sa.text("delivery_ref IS NOT NULL"),
    )
    op.alter_column(
        "service_contribution_allocations",
        "task_ref",
        existing_type=postgresql.UUID(),
        nullable=True,
    )


def downgrade() -> None:
    """Reverse the additive columns; nullable task_ref cannot be tightened if used."""

    op.alter_column(
        "service_contribution_allocations",
        "task_ref",
        existing_type=postgresql.UUID(),
        nullable=False,
    )
    op.drop_column("service_cases", "correlation_id")
    op.drop_column("service_cases", "consent_version")
    op.drop_column("service_cases", "scope_purpose")
    op.drop_column("service_cases", "tenant_id")
    op.drop_column("task_assignments", "source_request_id")
    op.drop_column("task_assignments", "accepted_by_actor_id")
    op.drop_index("uq_service_contributions_delivery_ref", table_name="service_contributions")
    op.drop_column("service_contributions", "delivery_ref")
    op.drop_constraint("ck_service_tasks_acceptance_criteria_array", "service_tasks", type_="check")
    op.drop_column("service_tasks", "acceptance_criteria")
