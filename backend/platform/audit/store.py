"""Durable, append-only storage for :class:`AuditEvent` — the mechanism R6 needs.

Why this module exists
---------------------
R6 says "任何对权威业务状态的写入，必须产生 AuditEvent". Before this module,
`AuditRecorder.flush()` was a no-op and no audit table existed anywhere in
`database/`, so a domain write could commit while its audit record died with
the process. R6 was an intention, not a mechanism.

Transaction model: **same transaction as the domain write. Not an outbox.**
--------------------------------------------------------------------------
The repository has an outbox precedent (`outbox_events` in
`database/baseline/0002_platform_foundation.sql`) and it is the right pattern
for *integration events*: those describe something that already happened, and
delivering them late is a latency problem, not a correctness problem.

Audit is not that. An outbox for audit means the sequence "domain row
committed → process dies → audit row never written" is reachable, and that
sequence is precisely the state R6 forbids: authoritative state changed with no
record of who changed it. A window that "usually" closes is still a window, and
《未成年人网络保护条例》第37条's annual audit has to be able to state that the
trail is complete, not complete-modulo-crashes.

So :func:`persist_events` writes through the **caller's** `AsyncSession` — the
one the domain repositories are already writing through, owned by
`backend.platform.persistence.unit_of_work.SqlAlchemyUnitOfWork`. It issues no
commit of its own. Consequences, accepted deliberately:

* If the audit insert fails, the whole transaction fails and the domain write
  rolls back with it. That is the correct direction of failure for R6: no
  audit, no state change. The opposite trade (keep the business write, lose the
  record) is the one that is not available to us.
* The audit table participates in business transactions, so it is on the hot
  path and its locks matter. It is insert-only with no unique constraint other
  than the primary key, so concurrent inserts do not contend on a shared row;
  the cost is index maintenance, not lock waiting.
* Long-running business transactions hold their audit rows invisible until
  commit. That is the same visibility rule as the domain rows they describe,
  which is what makes "the row exists ⇒ the change exists" true in both
  directions.

WORM (append-only)
-----------------
Enforced at two levels, with an honest gap:

* **Code layer (always in force).** This module exposes exactly two operations:
  insert (:func:`persist_events`) and read (:func:`read_events_for_subject`,
  :func:`read_all_events`). There is no update or delete function, and
  `AuditEventRow` instances are never returned to callers as live ORM objects —
  queries return frozen :class:`AuditEvent` values, so a caller cannot mutate a
  row and have a session flush the change back. Asserted by
  `test_store_exposes_no_update_or_delete_function` and
  `test_audit_event_row_has_no_mutation_bookkeeping_columns`.
* **DB layer (Postgres only).** Migration
  `0002_platform_audit_events_worm` installs a `BEFORE UPDATE OR DELETE`
  trigger that raises. That is the only enforcement that survives a caller with
  a raw connection.
* **Honest gap: SQLite has no such guard.** The trigger is Postgres syntax
  (`plpgsql`); the SQLite fast test path creates the table via
  `Base.metadata.create_all` and therefore has *no* DB-level WORM. On SQLite,
  append-only rests on the code layer alone. Production is Postgres
  (`docs/07_data/DATA_ARCHITECTURE.md`), which is where the trigger applies.
  Neither layer defends against a DBA with superuser rights — WORM against the
  database owner needs storage-level immutability (WAL archiving to
  object-lock storage, or an external hash-chain anchor), which is not built.

Why a new table rather than the legacy ``audit_logs``
----------------------------------------------------
`database/baseline/0002_platform_foundation.sql` already ships `audit_logs`,
replayed verbatim by the Alembic baseline. It cannot hold an `AuditEvent`: it
has no `before`/`after` columns (R6 names both), and none of 第36条's four
read-access elements. Widening it would mean editing a baseline whose entire
value is being checksum-identical to the legacy SQL (T-03's
`test_baseline_linearisation.py` asserts that). So `platform_audit_events` is a
new table in a new revision, and `audit_logs` is left alone as legacy history.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    MetaData,
    String,
    Text,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

from backend.platform.audit.models import AuditActionKind, AuditEvent

#: Table name, exported so the migration and the tests name the same string
#: once rather than twice.
AUDIT_EVENTS_TABLE = "platform_audit_events"

#: `timezone=True` instance rather than the bare class: `AuditEvent.timestamp`
#: is always tz-aware UTC, and a `timezone=False` column is silently accepted
#: by SQLite but rejected by Postgres on the first insert. Same reasoning as
#: `backend/domains/product_intelligence/infrastructure/sqlalchemy_models.py`.
_TZ_DATETIME = DateTime(timezone=True)

#: `none_as_null=True` is load-bearing, not a style choice.
#:
#: SQLAlchemy's `JSON` defaults to `none_as_null=False`, which renders a Python
#: `None` as the JSON **literal** `null` — a non-NULL value as far as SQL is
#: concerned. Every kind-shape CHECK in this table and in migration 0002 is
#: written in terms of `before IS NULL` / `accessed_fields IS NULL`, so with the
#: default a perfectly well-formed MUTATION (no `accessed_fields`) or READ (no
#: `before`/`after`) is rejected by the constraint that exists to protect it.
#: `JSON.NULL` would be the opposite mistake for the same reason.
#:
#: Postgres shows the same behaviour, so this is not a SQLite artefact: the
#: default would fail identically against the migrated table in production.
#: Anything mapping a nullable JSON column in this table must use this type.
_NULLABLE_JSON = JSON(none_as_null=True)


class AuditBase(DeclarativeBase):
    """Declarative base owned by the audit kernel.

    Separate from any domain `Base` on purpose: audit must be creatable
    (`AuditBase.metadata.create_all`) without dragging in a domain's schema,
    because the audit table is the one table every domain depends on.
    """

    metadata = MetaData()


class AuditEventRow(AuditBase):
    """One persisted audit event.

    Deliberately has **no** `updated_at`, no `version`, and no soft-delete
    flag. Those columns exist to record mutation of a row; this row is never
    mutated. Adding any of them would imply an update path that must not
    exist (see module docstring, WORM).

    One table holds both `AuditActionKind`s rather than one table per kind.
    The discriminator is `action_kind`, mirroring the single-type-with-
    discriminator decision argued in `models.py`: two tables would let a read
    access be recorded in the mutation table with the 第36条 columns simply
    absent, which is the exact degradation the discriminator exists to prevent.
    The kind-specific columns are nullable at the DB level and constrained by
    `AuditEvent.__post_init__` on the way in — the invariant lives in the type,
    which is where it can produce a useful error message, and the column
    nullability just reflects that a read genuinely has no `before`.
    """

    __tablename__ = AUDIT_EVENTS_TABLE

    # Kept byte-for-byte in step with
    # `database/migrations/versions/0002_platform_audit_events_worm.py`, so the
    # SQLite fast path rejects the same malformed rows Postgres does. SQLite
    # does enforce CHECK constraints (it just has no trigger for WORM), so
    # these are the one part of the DB-level guarantee that holds on both.
    __table_args__ = (
        CheckConstraint(
            "action_kind IN ('mutation', 'read')", name="ck_platform_audit_events_action_kind"
        ),
        CheckConstraint(
            """
    (action_kind = 'read' AND before IS NULL AND after IS NULL
        AND subject_person_id IS NOT NULL AND accessed_fields IS NOT NULL
        AND access_purpose IS NOT NULL)
    OR
    (action_kind = 'mutation' AND subject_person_id IS NULL
        AND accessed_fields IS NULL AND access_purpose IS NULL
        AND approval_ref IS NULL)
""",
            name="ck_platform_audit_events_kind_shape",
        ),
        CheckConstraint(
            "NOT (subject_is_minor AND approval_ref IS NULL)",
            name="ck_platform_audit_events_minor_approval",
        ),
    )

    # Surrogate autoincrement key doubling as the append order within a
    # partition of equal timestamps. Not a UUID: this table is only ever
    # written by one code path (persist_events) inside a single database, so
    # there is no cross-shard id-generation problem to solve, and a monotonic
    # key makes "the events after event N" a cheap range scan for the 第37条
    # annual export.
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # --- R6 required elements -------------------------------------------
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(_TZ_DATETIME, nullable=False)

    # `action_kind` is stored as its string value rather than a native enum
    # type. A Postgres `CREATE TYPE ... AS ENUM` would have to be extended by
    # migration before a new kind could be written, which sounds like a
    # feature until the new kind is EXPORT and the audit write fails closed in
    # production. The closed set is enforced by `AuditActionKind` on the way
    # in and on the way out (see `_row_to_event`).
    action_kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    # --- MUTATION-only ---------------------------------------------------
    # JSON (not JSONB) so the same model works against SQLite and Postgres.
    # Postgres maps SQLAlchemy `JSON` to `json`; the queries this table
    # supports filter on scalar columns only and never index into the payload,
    # so `jsonb`'s operator support buys nothing here.
    before: Mapped[dict | None] = mapped_column(_NULLABLE_JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(_NULLABLE_JSON, nullable=True)

    # --- READ-only (《未成年人网络保护条例》第36条) -----------------------
    subject_person_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    subject_is_minor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Stored as a JSON array. `accessed_fields` is a tuple on the value object
    # and a set-like list here; it is read back as a whole and never queried
    # element-wise, so a JSON array beats both a Postgres ARRAY (no SQLite
    # equivalent) and a delimiter-joined string (which breaks on field names
    # containing the delimiter).
    accessed_fields: Mapped[list | None] = mapped_column(_NULLABLE_JSON, nullable=True)
    access_purpose: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approval_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)


def _event_to_values(event: AuditEvent) -> dict[str, object]:
    return {
        "actor_id": event.actor_id,
        "tenant_id": event.tenant_id,
        "action": event.action,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "reason": event.reason,
        "correlation_id": event.correlation_id,
        "occurred_at": event.timestamp,
        "action_kind": str(event.action_kind),
        "before": event.before,
        "after": event.after,
        "subject_person_id": event.subject_person_id,
        "subject_is_minor": event.subject_is_minor,
        # `()` and `None` must not both round-trip to `()` by accident: a READ
        # always has a non-empty tuple (invariant), a MUTATION always has an
        # empty one, so storing empty-as-NULL loses nothing and keeps the
        # column honest about "this event has no accessed fields".
        "accessed_fields": list(event.accessed_fields) or None,
        "access_purpose": event.access_purpose,
        "approval_ref": event.approval_ref,
    }


def _row_to_event(row: AuditEventRow) -> AuditEvent:
    """Rebuild the frozen value object from a row.

    Reconstructing through `AuditEvent.__init__` means every invariant in
    `__post_init__` is re-checked on read. If a row ever violates one (a READ
    of a minor with no `approval_ref`, say — only reachable by writing around
    this module), the read raises rather than handing back a value object that
    the type system claims cannot exist.
    """
    timestamp = row.occurred_at
    if timestamp.tzinfo is None:
        # SQLite has no real datetime type and returns naive values. The write
        # side always stores UTC, so attaching UTC restores the original
        # instant rather than guessing.
        timestamp = timestamp.replace(tzinfo=UTC)
    return AuditEvent(
        actor_id=row.actor_id,
        tenant_id=row.tenant_id,
        action=row.action,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        reason=row.reason,
        correlation_id=row.correlation_id,
        before=row.before,
        after=row.after,
        action_kind=AuditActionKind(row.action_kind),
        subject_person_id=row.subject_person_id,
        subject_is_minor=bool(row.subject_is_minor),
        accessed_fields=tuple(row.accessed_fields or ()),
        access_purpose=row.access_purpose,
        approval_ref=row.approval_ref,
        timestamp=timestamp,
    )


async def persist_events(session: AsyncSession, events: Iterable[AuditEvent]) -> int:
    """Insert `events` through the caller's session. Returns the row count.

    **Does not commit.** The caller's `UnitOfWork.commit()` decides when these
    rows become visible, which is what makes them atomic with the domain write
    they describe (see module docstring). Raising propagates, so a failed audit
    insert aborts the caller's transaction.
    """
    rows = [_event_to_values(event) for event in events]
    if not rows:
        return 0
    await session.execute(AuditEventRow.__table__.insert(), rows)
    return len(rows)


async def read_all_events(
    session: AsyncSession, *, tenant_id: str | None = None
) -> Sequence[AuditEvent]:
    """Every persisted event, oldest first. Optionally scoped to one tenant."""
    stmt = select(AuditEventRow).order_by(AuditEventRow.id)
    if tenant_id is not None:
        stmt = stmt.where(AuditEventRow.tenant_id == tenant_id)
    result = await session.execute(stmt)
    return [_row_to_event(row) for row in result.scalars().all()]


async def read_events_for_subject(
    session: AsyncSession, subject_person_id: str
) -> Sequence[AuditEvent]:
    """Persisted READ events for one person, oldest first.

    The durable counterpart of `AuditRecorder.read_events_for_subject`, and the
    query 第36/37条 reporting actually needs: "who accessed this minor's
    information, when, for what purpose, under whose approval" must be
    answerable after the process that served those reads is long gone.
    """
    stmt = (
        select(AuditEventRow)
        .where(
            AuditEventRow.subject_person_id == subject_person_id,
            AuditEventRow.action_kind == str(AuditActionKind.READ),
        )
        .order_by(AuditEventRow.id)
    )
    result = await session.execute(stmt)
    return [_row_to_event(row) for row in result.scalars().all()]


async def create_audit_schema(session: AsyncSession) -> None:
    """Create the audit table on the session's connection if absent.

    For the SQLite fast test path only (`docs/07_data/DATA_ARCHITECTURE.md`:
    SQLite bypasses Alembic via `create_all`). Postgres deployments get this
    table from `database/migrations/versions/0002_platform_audit_events_worm.py`,
    which also installs the WORM trigger this function cannot express.
    """
    connection = await session.connection()
    await connection.run_sync(AuditBase.metadata.create_all)
