"""service booking — the private check-in draft table and two 0035 additions

Revision ID: 0003_service_booking_additions
Revises: 0002_platform_audit_events_worm
Create Date: 2026-08-29

Scope, and why it is this small
-------------------------------
The service booking chain (`ServiceProvider` → `ServiceOffering` →
`AvailabilitySlot` → `BookingRequest` → `ServiceRecord`) already exists in the
schema: `database/baseline/0035_family_service_booking_objects.sql` creates all
five tables and the customer projection view, and revision 0001 replays that
file verbatim. This revision therefore creates **nothing that 0035 already
has**, and does not touch 0035 — that baseline's whole value is being
checksum-identical to the legacy SQL, asserted by
`database/tests/test_baseline_linearisation.py`.

What is added, and why each one is unavoidable:

1. ``family_service_private_checkin_drafts`` — a genuinely new table. The
   `createPrivateCheckinDraft` endpoint (UI-06 §4.1, one of the six published
   SERVICE endpoints) has no table in 0035 at all. It is append-only and has no
   free-text column: `action_ref` is constrained to the three allow-listed
   values, because an allow-list cannot carry an unreviewed fact about a child
   and a free-text box can. Widening it is an ADR, not an `ALTER TABLE`.

2. ``family_booking_service_records.service_quality_rating`` — evaluates the
   *provider's delivered session*. R9 forbids scoring families and children; a
   customer evaluating a purchased service is the opposite direction of power
   and is not what that red line protects against. The CHECK below pins the
   closed vocabulary, so the column cannot quietly become a numeric score.

3. ``family_service_availability_slots.attributes_schema_version`` — 0035 gave
   four of its five tables an `attributes_schema_version` alongside `attributes`
   and omitted it on this one. That is an inconsistency in the legacy DDL rather
   than a design, and the ORM models version extensibility uniformly across the
   chain.

The T-03 lesson this revision exists to respect
------------------------------------------------
`product_intelligence` kept a private SQL copy inside its domain directory, so
its ORM required three columns the Alembic baseline never created — and its
tests did not catch it because they built their own schema with
`Base.metadata.create_all`. Every column in
`backend/domains/service/infrastructure/sqlalchemy_models.py` therefore either
exists in baselined 0035 or is added here. There is no third source, and no SQL
file under `backend/domains/service/`.

`ALTER TABLE ... ADD COLUMN` on the two existing tables is nullable-with-no-
default on purpose: adding a NOT NULL column with a default rewrites the table
on older Postgres, and neither column has a meaningful value for the rows that
already exist. `attributes_schema_version` gets a server default so new inserts
that omit it behave like the other four tables; existing rows are backfilled in
the same step, which is cheap because this is fixture-only supply.

Revision numbering note
-----------------------
Authored as `0003_...`, briefly renumbered to `0004_...` behind
`0003_membership_lifecycle_v2` when that landed from a concurrent session (two
revisions both pointing at `0002` made `alembic heads` report a branch, which
`alembic upgrade head` refuses), then restored to `0003_...` on `0002` when that
session withdrew its revision. `alembic_version.version_num` is `varchar(32)`,
so the id has to stay inside 32 characters — the first draft was
`0003_service_booking_domain_additions` (37 chars) and the upgrade failed on the
version stamp *after* running the DDL, which is a confusing place to discover a
naming limit.

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_service_booking_additions"
down_revision: str | None = "0002_platform_audit_events_worm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECKIN_DRAFTS_TABLE = "family_service_private_checkin_drafts"

#: Mirrors `backend/domains/service/domain/value_objects.py::CHECKIN_ACTION_REFS`.
#: Named here rather than inlined so the constraint and the Python literal are
#: visibly the same list.
CHECKIN_ACTION_REFS = ("WEEKLY_ACTION_SEE", "WEEKLY_ACTION_ADJUST", "PAUSE_AND_RETURN")

#: Mirrors `ServiceQualityRating`. Not numeric, and not extensible without a
#: migration — which is the point: a free numeric column is one refactor away
#: from being a score.
SERVICE_QUALITY_RATINGS = ("POSITIVE", "NEUTRAL", "NEEDS_FOLLOW_UP")


def _in_list(column: str, values: Sequence[str]) -> str:
    rendered = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({rendered})"


def upgrade() -> None:
    op.create_table(
        CHECKIN_DRAFTS_TABLE,
        # `String` rather than `UUID`: the domain generates prefixed ids
        # (`svccheckin-<uuid4>`) so a value is self-describing in a log line, and
        # the same models must map on SQLite for the fast test path.
        sa.Column("private_checkin_draft_id", sa.String(length=128), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("actor_person_id", sa.String(length=128), nullable=False),
        sa.Column("onboarding_id", sa.String(length=128), nullable=False),
        sa.Column("action_ref", sa.String(length=48), nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column(
            "source_system", sa.String(length=32), nullable=False, server_default="TEST_FIXTURE"
        ),
        sa.Column("external_effect", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("attributes_schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("attributes", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        # Allow-list in the database, not only in Python: a row written by any
        # client still cannot carry an action this domain never defined.
        sa.CheckConstraint(
            _in_list("action_ref", CHECKIN_ACTION_REFS),
            name="ck_family_service_private_checkin_draft_action_ref",
        ),
        # R5 fixture boundary, same shape as the 0035 tables.
        sa.CheckConstraint(
            "environment IN ('DEV','TEST')",
            name="ck_family_service_private_checkin_draft_environment",
        ),
        sa.CheckConstraint(
            "external_effect = false",
            name="ck_family_service_private_checkin_draft_external_effect",
        ),
        sa.CheckConstraint(
            "attributes_schema_version > 0",
            name="ck_family_service_private_checkin_draft_attributes_version",
        ),
    )
    # Partial unique index on the idempotency key, matching
    # `uq_family_booking_idempotency` in 0035: a NULL key must not collide with
    # another NULL key, so the index has to exclude them.
    op.create_index(
        "uq_family_service_private_checkin_draft_idempotency",
        CHECKIN_DRAFTS_TABLE,
        ["tenant_id", "family_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_index(
        "idx_family_service_private_checkin_draft_scope",
        CHECKIN_DRAFTS_TABLE,
        ["tenant_id", "family_id", "onboarding_id", "occurred_at"],
    )

    op.add_column(
        "family_booking_service_records",
        sa.Column("service_quality_rating", sa.String(length=32), nullable=True),
    )
    op.create_check_constraint(
        "ck_family_booking_service_record_quality_rating",
        "family_booking_service_records",
        "service_quality_rating IS NULL OR "
        + _in_list("service_quality_rating", SERVICE_QUALITY_RATINGS),
    )

    op.add_column(
        "family_service_availability_slots",
        sa.Column("attributes_schema_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_family_service_availability_slot_attributes_version",
        "family_service_availability_slots",
        "attributes_schema_version > 0",
    )


def downgrade() -> None:
    """Reversible, unlike revision 0001.

    This revision created its own objects and added its own columns, so undoing
    it removes only what it added. Dropping `service_quality_rating` does lose
    data — the ratings families gave — which is why a downgrade is a deliberate
    operator action and not something a deploy pipeline should run
    automatically.
    """
    op.drop_constraint(
        "ck_family_service_availability_slot_attributes_version",
        "family_service_availability_slots",
        type_="check",
    )
    op.drop_column("family_service_availability_slots", "attributes_schema_version")

    op.drop_constraint(
        "ck_family_booking_service_record_quality_rating",
        "family_booking_service_records",
        type_="check",
    )
    op.drop_column("family_booking_service_records", "service_quality_rating")

    op.drop_index("idx_family_service_private_checkin_draft_scope", table_name=CHECKIN_DRAFTS_TABLE)
    op.drop_index(
        "uq_family_service_private_checkin_draft_idempotency", table_name=CHECKIN_DRAFTS_TABLE
    )
    op.drop_table(CHECKIN_DRAFTS_TABLE)
