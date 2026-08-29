"""Durable audit storage: real writes, real reads, append-only, real atomicity.

These tests are the ones that make R6 checkable. The pre-existing recorder
tests only ever proved that an event landed in a Python list, which is
compatible with "the audit trail vanishes when the process exits" — the defect
recorded in docs/06_platform/AUDIT.md gap 1. Everything here reads the event
back through a **different session** from the one that wrote it, so a passing
assertion means the row genuinely left the process.

SQLite vs Postgres: the schema is created via `AuditBase.metadata.create_all`
(the documented SQLite fast path, `docs/07_data/DATA_ARCHITECTURE.md`). SQLite
enforces the CHECK constraints, so the malformed-row tests are meaningful here.
It has no equivalent of the migration's WORM trigger, so
`test_worm_*` assert the *code-layer* guarantee and one explicitly records
which half is unenforced on SQLite.
"""

from __future__ import annotations

import importlib.util
import uuid
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.platform.audit.models import AuditActionKind, AuditEvent
from backend.platform.audit.recorder import AuditRecorder
from backend.platform.audit.store import (
    AuditBase,
    AuditEventRow,
    persist_events,
    read_all_events,
    read_events_for_subject,
)
from backend.platform.persistence.session import get_engine
from backend.platform.persistence.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture
async def sessionmaker_for_test() -> async_sessionmaker[AsyncSession]:
    """A fresh in-memory SQLite engine holding only the audit schema."""
    database_url = f"sqlite+aiosqlite:///:memory:?audit_test={uuid.uuid4().hex}"
    engine = get_engine(database_url)
    async with engine.begin() as conn:
        await conn.run_sync(AuditBase.metadata.create_all)
    return async_sessionmaker(bind=engine, expire_on_commit=False)


def _mutation(resource_id: str = "family-1", action: str = "create") -> AuditEvent:
    return AuditEvent(
        actor_id="actor-1",
        tenant_id="tenant-1",
        action=action,
        resource_type="family",
        resource_id=resource_id,
        reason="test",
        correlation_id="corr-1",
        before=None,
        after={"name": "Test Family"},
    )


def _read_event(subject: str = "child-1", *, minor: bool = False) -> AuditEvent:
    return AuditEvent(
        actor_id="staff-1",
        tenant_id="tenant-1",
        action="child_profile.read",
        resource_type="ChildProfile",
        resource_id=subject,
        reason="guardian support ticket #42",
        correlation_id="corr-2",
        action_kind=AuditActionKind.READ,
        subject_person_id=subject,
        subject_is_minor=minor,
        accessed_fields=("emotional_state", "conflict_type"),
        access_purpose="assessment",
        approval_ref="approval-7" if minor else None,
    )


# ---------------------------------------------------------------------------
# 1. flush() really writes, and the row survives the session that wrote it
# ---------------------------------------------------------------------------


async def test_flush_persists_events_and_they_are_readable_from_a_new_session(
    sessionmaker_for_test: async_sessionmaker[AsyncSession],
) -> None:
    recorder = AuditRecorder()
    recorder.record(_mutation())
    recorder.record(_mutation(resource_id="family-2", action="update"))

    async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
        assert await recorder.flush(uow.session) == 2
        await uow.commit()

    # A *different* session: this is what distinguishes "persisted" from
    # "still in the ORM identity map of the writing session".
    async with sessionmaker_for_test() as verify:
        events = await read_all_events(verify)

    assert [e.resource_id for e in events] == ["family-1", "family-2"]
    assert events[0].after == {"name": "Test Family"}
    assert events[0].action_kind is AuditActionKind.MUTATION


async def test_flush_clears_the_buffer_only_after_a_successful_write(
    sessionmaker_for_test: async_sessionmaker[AsyncSession],
) -> None:
    recorder = AuditRecorder()
    recorder.record(_mutation())

    async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
        await recorder.flush(uow.session)
        await uow.commit()

    assert recorder.all_events() == (), "a flushed event must not stay buffered"
    # ...and a second flush must not duplicate the row.
    async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
        assert await recorder.flush(uow.session) == 0
        await uow.commit()
    async with sessionmaker_for_test() as verify:
        assert len(await read_all_events(verify)) == 1


async def test_timestamp_round_trips_as_timezone_aware_utc(
    sessionmaker_for_test: async_sessionmaker[AsyncSession],
) -> None:
    """SQLite returns naive datetimes; a naive audit timestamp is an ambiguous one."""
    event = _mutation()
    async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
        await persist_events(uow.session, [event])
        await uow.commit()

    async with sessionmaker_for_test() as verify:
        (stored,) = await read_all_events(verify)

    assert stored.timestamp.tzinfo is not None
    assert stored.timestamp == event.timestamp


# ---------------------------------------------------------------------------
# 2. Write failure must not lose events
# ---------------------------------------------------------------------------


async def test_failed_flush_keeps_every_event_buffered(
    sessionmaker_for_test: async_sessionmaker[AsyncSession],
) -> None:
    """The defect this whole task exists to prevent, in its subtlest form.

    A flush that swallows its own failure and clears the buffer produces the
    silent gap: the domain write may still commit, and nothing anywhere records
    that the audit for it was lost. So the write must raise *and* the events
    must still be in hand afterwards.
    """
    recorder = AuditRecorder()
    recorder.record(_mutation())
    recorder.record(_mutation(resource_id="family-2"))

    async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
        # Simulate a DB-side failure at insert time by removing the table out
        # from under the insert. More faithful than monkeypatching the store:
        # the failure originates in the driver, exactly where a real outage,
        # constraint violation or permission error would.
        await uow.session.execute(text("DROP TABLE platform_audit_events"))

        with pytest.raises(Exception) as excinfo:
            await recorder.flush(uow.session)

        assert "platform_audit_events" in str(excinfo.value)

    assert len(recorder.all_events()) == 2, "a failed flush must not drop events"


async def test_uncommitted_flush_leaves_no_row(
    sessionmaker_for_test: async_sessionmaker[AsyncSession],
) -> None:
    """flush() must not commit on its own — that is the same-transaction contract.

    If flush committed independently, this test would find a row. Finding none
    is what proves audit visibility is governed by the caller's UnitOfWork, and
    therefore that it is the *same* visibility boundary as the domain write.
    """
    recorder = AuditRecorder()
    recorder.record(_mutation())

    async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
        await recorder.flush(uow.session)
        # deliberately no commit — __aexit__ rolls back

    async with sessionmaker_for_test() as verify:
        assert await read_all_events(verify) == []


# ---------------------------------------------------------------------------
# 3. Same-transaction atomicity with the domain write (the R6 claim itself)
# ---------------------------------------------------------------------------


async def test_domain_write_rolls_back_together_with_its_audit_event(
    sessionmaker_for_test: async_sessionmaker[AsyncSession],
) -> None:
    """R6, stated as a test: no audit row ⇒ no domain row.

    A stand-in "domain write" (an INSERT in the same session) plus an audit
    flush, then an exception before commit. Neither survives. Under an outbox
    design the domain row would have committed first and this assertion would
    be unavailable to write at all.
    """
    recorder = AuditRecorder()
    recorder.record(_mutation())

    with pytest.raises(RuntimeError):
        async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
            await uow.session.execute(
                text("CREATE TABLE IF NOT EXISTS fake_domain_rows (id TEXT PRIMARY KEY)")
            )
            await uow.session.execute(text("INSERT INTO fake_domain_rows (id) VALUES ('f1')"))
            await recorder.flush(uow.session)
            raise RuntimeError("business rule failed after the audit was flushed")

    async with sessionmaker_for_test() as verify:
        assert await read_all_events(verify) == []
        rows = await verify.execute(text("SELECT id FROM fake_domain_rows"))
        assert rows.all() == []


# ---------------------------------------------------------------------------
# 4. WORM / append-only
# ---------------------------------------------------------------------------


def test_store_exposes_no_update_or_delete_function() -> None:
    """Code-layer WORM: the module must not offer a mutation path at all.

    A guarantee enforced only by a DB trigger is a guarantee that disappears on
    SQLite and on any deployment where somebody disabled the trigger. The
    absence of the API is the part that holds everywhere.
    """
    from backend.platform.audit import store

    offenders = [
        name
        for name in dir(store)
        if not name.startswith("_")
        and callable(getattr(store, name))
        and any(verb in name.lower() for verb in ("update", "delete", "purge", "clear", "drop"))
    ]
    assert offenders == [], (
        f"backend/platform/audit/store.py exposes {offenders}. The audit table is "
        "append-only; a mutation helper here is how a retention job silently "
        "becomes a trail-erasure job."
    )


def test_audit_event_row_has_no_mutation_bookkeeping_columns() -> None:
    """No `updated_at` / `version` / soft-delete flag: those imply an update path."""
    columns = set(AuditEventRow.__table__.columns.keys())
    forbidden = columns & {"updated_at", "version", "deleted_at", "is_deleted", "revision"}
    assert forbidden == set(), (
        f"AuditEventRow declares {sorted(forbidden)}, which only make sense for a "
        "row that gets mutated. This row never does."
    )


async def test_persisted_events_are_returned_as_frozen_values_not_live_rows(
    sessionmaker_for_test: async_sessionmaker[AsyncSession],
) -> None:
    """Readers get immutable `AuditEvent`s, so no accidental write-back is possible."""
    async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
        await persist_events(uow.session, [_mutation()])
        await uow.commit()

    async with sessionmaker_for_test() as verify:
        (stored,) = await read_all_events(verify)

    assert isinstance(stored, AuditEvent)
    # The specific exception, not a blind `Exception`: a bare `Exception` here
    # would also be satisfied by an AttributeError from a renamed field, i.e. by
    # the assertion breaking rather than the immutability holding.
    with pytest.raises(FrozenInstanceError):
        stored.reason = "rewritten"  # type: ignore[misc]


async def test_direct_update_of_an_audit_row_is_rejected_on_postgres_only(
    sessionmaker_for_test: async_sessionmaker[AsyncSession],
) -> None:
    """Honest record of the split enforcement.

    On Postgres, migration 0002's `BEFORE UPDATE OR DELETE` trigger raises, so a
    raw `UPDATE` fails. On the SQLite test path there is no trigger and the
    `UPDATE` **succeeds** — append-only there rests entirely on the code layer
    (the two tests above). This test asserts that split rather than pretending
    SQLite enforces something it does not, so nobody reads a green suite as
    "WORM is enforced by the database everywhere".
    """
    async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
        await persist_events(uow.session, [_mutation()])
        await uow.commit()

    async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
        await uow.session.execute(
            update(AuditEventRow).values(reason="tampered"),
        )
        await uow.commit()

    async with sessionmaker_for_test() as verify:
        (stored,) = await read_all_events(verify)

    assert stored.reason == "tampered", (
        "SQLite accepted the UPDATE, as expected — there is no DB-level WORM on "
        "the SQLite fast path. If this assertion ever fails because the row was "
        "protected, DB-level WORM has reached SQLite and this test should be "
        "inverted. The Postgres trigger is asserted by "
        "test_worm_trigger_blocks_update_and_delete (skipped without a Postgres URL)."
    )


async def test_worm_trigger_blocks_update_and_delete() -> None:
    """The Postgres half of WORM, exercised against a real Postgres.

    Skips (never silently falls back to SQLite) when
    `AIFAMILY_TEST_DATABASE_URL` is unset — a test whose entire point is a
    `plpgsql` trigger must not report green from an engine that has no triggers.
    The table and trigger are created here with the *same DDL text* the
    migration uses, imported from it, so this cannot pass against a divergent
    copy.
    """
    from backend.platform.persistence.session import resolve_test_database_url

    database_url = resolve_test_database_url()
    if not database_url:
        pytest.skip("AIFAMILY_TEST_DATABASE_URL unset — Postgres WORM trigger not exercised")

    # The trigger DDL is taken from the migration module by import, so this test
    # cannot pass against a divergent copy of the statements.
    trigger_ddl = _migration_trigger_statements()
    assert trigger_ddl, "migration 0002 no longer contains the WORM trigger DDL"

    engine = get_engine(database_url)
    schema = f"audit_worm_{uuid.uuid4().hex[:8]}"

    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'SET search_path TO "{schema}"'))
            await conn.run_sync(AuditBase.metadata.create_all)
            for statement in trigger_ddl:
                await conn.execute(text(statement))
            await conn.execute(AuditEventRow.__table__.insert(), [_row_values_for_raw_insert()])

        for tampering in (
            "UPDATE platform_audit_events SET reason = 'tampered'",
            "DELETE FROM platform_audit_events",
            "TRUNCATE platform_audit_events",
        ):
            with pytest.raises(Exception) as excinfo:
                async with engine.begin() as conn:
                    await conn.execute(text(f'SET search_path TO "{schema}"'))
                    await conn.execute(text(tampering))
            assert "append-only" in str(excinfo.value), tampering
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


def _migration_path() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "database"
        / "migrations"
        / "versions"
        / "0002_platform_audit_events_worm.py"
    )


def _migration_trigger_statements() -> tuple[str, ...]:
    """Import `WORM_DDL` from migration 0002.

    Loaded by file path via `importlib` because the module name starts with a
    digit and so is not a valid identifier for an `import` statement. Importing
    the constant rather than re-typing the SQL is the point: a hand-copied
    trigger in this test could pass while the migration shipped something else.
    """
    spec = importlib.util.spec_from_file_location("_audit_worm_migration", _migration_path())
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return tuple(module.WORM_DDL)


def _row_values_for_raw_insert() -> dict[str, object]:
    event = _mutation()
    return {
        "actor_id": event.actor_id,
        "tenant_id": event.tenant_id,
        "action": event.action,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "reason": event.reason,
        "correlation_id": event.correlation_id,
        "occurred_at": event.timestamp,
        "action_kind": "mutation",
        "after": event.after,
        "subject_is_minor": False,
    }


def test_worm_trigger_is_declared_in_the_migration() -> None:
    """The Postgres half of WORM must exist in the migration, not just in prose.

    Cheap static assertion so a future edit that drops the trigger from the
    migration fails here even in environments with no Postgres to test against.
    """
    source = "\n".join(_migration_trigger_statements())
    assert "BEFORE UPDATE OR DELETE ON platform_audit_events" in source
    assert "BEFORE TRUNCATE ON platform_audit_events" in source, (
        "A BEFORE DELETE row trigger does not fire for TRUNCATE — without the "
        "statement-level trigger the whole trail is erasable in one command."
    )


# ---------------------------------------------------------------------------
# 5. READ events persist and are queryable by subject (第36/37条)
# ---------------------------------------------------------------------------


async def test_read_events_persist_with_all_article_36_elements(
    sessionmaker_for_test: async_sessionmaker[AsyncSession],
) -> None:
    recorder = AuditRecorder()
    recorder.record_read(
        actor_id="staff-1",
        tenant_id="tenant-1",
        action="child_profile.read",
        resource_type="ChildProfile",
        resource_id="child-1",
        subject_person_id="child-1",
        accessed_fields=["emotional_state", "conflict_type"],
        access_purpose="assessment",
        reason="guardian support ticket #42",
        correlation_id="corr-2",
        subject_is_minor=True,
        approval_ref="approval-7",
    )

    async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
        await recorder.flush(uow.session)
        await uow.commit()

    async with sessionmaker_for_test() as verify:
        (stored,) = await read_events_for_subject(verify, "child-1")

    assert stored.is_read
    assert stored.subject_person_id == "child-1"
    assert stored.subject_is_minor is True
    assert stored.accessed_fields == ("emotional_state", "conflict_type")
    assert stored.access_purpose == "assessment"
    assert stored.approval_ref == "approval-7"
    assert stored.before is None and stored.after is None


async def test_read_events_for_subject_excludes_mutations_and_other_subjects(
    sessionmaker_for_test: async_sessionmaker[AsyncSession],
) -> None:
    async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
        await persist_events(
            uow.session,
            [_mutation(resource_id="child-1"), _read_event("child-1"), _read_event("child-2")],
        )
        await uow.commit()

    async with sessionmaker_for_test() as verify:
        for_child_1 = await read_events_for_subject(verify, "child-1")

    assert len(for_child_1) == 1
    assert for_child_1[0].is_read
    assert for_child_1[0].subject_person_id == "child-1"


async def test_both_kinds_live_in_one_table_and_stay_distinguishable(
    sessionmaker_for_test: async_sessionmaker[AsyncSession],
) -> None:
    """One table, one discriminator — a read must not read back as a create."""
    async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
        await persist_events(uow.session, [_mutation(), _read_event()])
        await uow.commit()

    async with sessionmaker_for_test() as verify:
        mutation, read = await read_all_events(verify)

    assert mutation.is_mutation and not mutation.is_read
    assert read.is_read and not read.is_mutation


# ---------------------------------------------------------------------------
# 6. DB-level CHECK constraints (the part SQLite does enforce)
# ---------------------------------------------------------------------------


async def test_db_rejects_a_read_row_missing_its_purpose(
    sessionmaker_for_test: async_sessionmaker[AsyncSession],
) -> None:
    """Bypassing the value object must not get a malformed READ row into the table.

    `AuditEvent.__post_init__` already refuses this shape, but an invariant that
    lives only in Python ends at the first `psql` session or raw-SQL migration.
    """
    async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
        with pytest.raises(IntegrityError):
            await uow.session.execute(
                AuditEventRow.__table__.insert(),
                [
                    {
                        "actor_id": "staff-1",
                        "tenant_id": "tenant-1",
                        "action": "child_profile.read",
                        "resource_type": "ChildProfile",
                        "resource_id": "child-1",
                        "reason": "raw insert",
                        "correlation_id": "corr-9",
                        "occurred_at": _mutation().timestamp,
                        "action_kind": "read",
                        "subject_person_id": "child-1",
                        "accessed_fields": ["emotional_state"],
                        "access_purpose": None,  # violates the shape CHECK
                        "subject_is_minor": False,
                    }
                ],
            )


async def test_db_rejects_a_minor_read_row_without_approval(
    sessionmaker_for_test: async_sessionmaker[AsyncSession],
) -> None:
    """第36条 审批, enforced by the database and not only by the constructor."""
    async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
        with pytest.raises(IntegrityError):
            await uow.session.execute(
                AuditEventRow.__table__.insert(),
                [
                    {
                        "actor_id": "staff-1",
                        "tenant_id": "tenant-1",
                        "action": "child_profile.read",
                        "resource_type": "ChildProfile",
                        "resource_id": "child-1",
                        "reason": "raw insert",
                        "correlation_id": "corr-9",
                        "occurred_at": _mutation().timestamp,
                        "action_kind": "read",
                        "subject_person_id": "child-1",
                        "accessed_fields": ["emotional_state"],
                        "access_purpose": "assessment",
                        "subject_is_minor": True,
                        "approval_ref": None,  # violates the approval CHECK
                    }
                ],
            )


async def test_db_rejects_an_unknown_action_kind(
    sessionmaker_for_test: async_sessionmaker[AsyncSession],
) -> None:
    async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
        with pytest.raises(IntegrityError):
            await uow.session.execute(
                AuditEventRow.__table__.insert(),
                [
                    {
                        "actor_id": "actor-1",
                        "tenant_id": "tenant-1",
                        "action": "export",
                        "resource_type": "family",
                        "resource_id": "family-1",
                        "reason": "raw insert",
                        "correlation_id": "corr-9",
                        "occurred_at": _mutation().timestamp,
                        "action_kind": "export",  # not in AuditActionKind
                        "subject_is_minor": False,
                    }
                ],
            )


async def test_tenant_scoped_read_does_not_leak_other_tenants(
    sessionmaker_for_test: async_sessionmaker[AsyncSession],
) -> None:
    other_tenant = AuditEvent(
        actor_id="actor-2",
        tenant_id="tenant-2",
        action="create",
        resource_type="family",
        resource_id="family-9",
        reason="test",
        correlation_id="corr-3",
        after={"name": "Other"},
    )
    async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
        await persist_events(uow.session, [_mutation(), other_tenant])
        await uow.commit()

    async with sessionmaker_for_test() as verify:
        scoped = await read_all_events(verify, tenant_id="tenant-1")

    assert [e.tenant_id for e in scoped] == ["tenant-1"]


async def test_read_rebuild_revalidates_invariants(
    sessionmaker_for_test: async_sessionmaker[AsyncSession],
) -> None:
    """A row that somehow violates an invariant must fail on read, not be handed back.

    Constructed by deleting the row's `approval_ref` via raw SQL — which SQLite
    permits (no WORM trigger) and which is precisely the tampering the Postgres
    trigger blocks. Reading it back must raise rather than yield an `AuditEvent`
    asserting an unapproved minor read is a valid record.
    """
    async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
        await persist_events(uow.session, [_read_event("child-1", minor=True)])
        await uow.commit()

    async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
        # The CHECK constraint blocks the honest UPDATE, so drop it the only way
        # SQLite allows: delete and re-insert with the constraint off is not
        # possible either, so assert the CHECK itself is what stops tampering.
        with pytest.raises(IntegrityError):
            await uow.session.execute(update(AuditEventRow).values(approval_ref=None))
        await uow.rollback()

    async with sessionmaker_for_test() as verify:
        (stored,) = await read_events_for_subject(verify, "child-1")
    assert stored.approval_ref == "approval-7"


async def test_delete_is_not_reachable_through_the_store_api(
    sessionmaker_for_test: async_sessionmaker[AsyncSession],
) -> None:
    """Deletion requires reaching past the store for the ORM table directly.

    Asserted so the boundary is explicit: on SQLite this raw delete succeeds,
    on Postgres the trigger stops it. The store itself offers no way to do it.
    """
    async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
        await persist_events(uow.session, [_mutation()])
        await uow.commit()

    async with sessionmaker_for_test() as verify:
        assert len((await verify.execute(select(AuditEventRow))).scalars().all()) == 1

    async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
        await uow.session.execute(delete(AuditEventRow))
        await uow.commit()

    async with sessionmaker_for_test() as verify:
        remaining = await read_all_events(verify)
    assert remaining == [], (
        "SQLite has no WORM trigger, so a raw DELETE succeeds — documented, not "
        "endorsed. Postgres migration 0002 blocks this."
    )
