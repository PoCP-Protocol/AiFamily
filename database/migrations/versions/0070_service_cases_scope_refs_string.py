"""Widen service_cases scope/reference columns from uuid+FK to plain String.

Revision ID: 0068_service_cases_scope_refs_string
Revises: 0067_service_feedback_playbook
Create Date: 2026-09-07

Why this exists
----------------
``service_cases`` is a baseline (0020) table whose ``family_id``,
``subject_person_id``, ``intent_ref`` and ``plan_ref`` columns are ``uuid``
with hard foreign keys to ``families``, ``persons``, ``growth_intents`` and
``orchestration_plans`` respectively. Those four referenced tables belong to
the *original* growth-orchestration design, where a family/person/intent/plan
always exists as a real row before a service case can reference it.

The FGCN P0 durable adapter added in 0004
(`backend/domains/service/fgcn/persistence.py::ServiceCaseRow`) writes to this
same table from a completely different, already-shipped identity model: the
dev/test account-session issuer (`backend/domains/assessment/api/dev_auth.py`)
mints `family_id` as a bare, human-readable slug taken straight from
`external_ref` (e.g. ``family-need-e2e-fgcn-escalation``), never a UUID, and
never inserts a row into `families`. The same flow
(`backend/apps/family_api/orchestration/need_fulfillment_flow.py`) passes
`draft.need_id` as `intent_ref` and a subject/person reference minted by the
`family_need` domain as `subject_person_id` — again both opaque strings, never
rows in `persons` or `growth_intents`, and `plan_ref` has no producer in this
flow at all today.

This is not a bug introduced by a test: it is the documented, repo-wide
convention. Every other domain that stores `family_id` — `family_need`
(0055, `sa.String(length=128)`), `commerce`, `loyalty_points`, `membership`,
and this very P0 revision's own additive columns on `service_cases`
(`tenant_id`, `scope_purpose`, `consent_version`, `correlation_id`, all
`String`, no FK) — already treats `family_id` (and sibling scope references)
as an opaque string identifier, not a UUID tied to a live `families` row.
`service_cases`' original four uuid+FK columns are the *outlier*, not the
target state.

Fixing the ORM side instead (requiring real UUIDs) would mean either (a)
minting throwaway `families`/`persons`/`growth_intents`/`orchestration_plans`
rows nobody else in this system creates, purely to satisfy a legacy FK that
predates the P0 adapter, or (b) forcing every caller of the FGCN P0 durable
path to invent and thread real UUIDs where none currently exist. Both are
worse than acknowledging that this table now serves two eras of design and
loosening the legacy typing to match the convention its own extension
(0004) already established.

`case_id` itself stays `uuid` — it is a `ServiceCaseRow`-generated primary key
(`gen_random_uuid()` default) and every dependent table already keys off it
correctly; only the four *incoming* scope/reference columns are widened.

Downgrade recreates the four foreign keys. It will fail if any row written
through the P0 durable path (a non-UUID slug in any of the four columns)
exists at downgrade time — that data loss potential is inherent to reversing
a type-widening migration and is not silently swallowed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0070_service_cases_scope_refs_string"
down_revision: str | None = "0069_ai_run_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WIDENED_COLUMNS = ("family_id", "subject_person_id", "intent_ref", "plan_ref")

_FOREIGN_KEYS = (
    ("service_cases_family_id_fkey", "family_id"),
    ("service_cases_subject_person_id_fkey", "subject_person_id"),
    ("service_cases_intent_ref_fkey", "intent_ref"),
    ("service_cases_plan_ref_fkey", "plan_ref"),
)

_REFERENCED = {
    "family_id": ("families", "family_id"),
    "subject_person_id": ("persons", "person_id"),
    "intent_ref": ("growth_intents", "intent_id"),
    "plan_ref": ("orchestration_plans", "plan_id"),
}


def upgrade() -> None:
    for fk_name, _column in _FOREIGN_KEYS:
        op.drop_constraint(fk_name, "service_cases", type_="foreignkey")
    for column in _WIDENED_COLUMNS:
        op.alter_column(
            "service_cases",
            column,
            existing_type=sa.dialects.postgresql.UUID(),
            type_=sa.String(length=128),
            nullable=False,
            postgresql_using=f"{column}::text",
        )


def downgrade() -> None:
    """Reverse the widening. Fails closed if any row holds a non-UUID value."""

    for column in _WIDENED_COLUMNS:
        op.alter_column(
            "service_cases",
            column,
            existing_type=sa.String(length=128),
            type_=sa.dialects.postgresql.UUID(),
            nullable=False,
            postgresql_using=f"{column}::uuid",
        )
    for fk_name, column in _FOREIGN_KEYS:
        referenced_table, referenced_column = _REFERENCED[column]
        op.create_foreign_key(
            fk_name,
            "service_cases",
            referenced_table,
            [column],
            [referenced_column],
        )
