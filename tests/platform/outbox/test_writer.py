"""Canonical Outbox append, replay, restart, and transaction contracts."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import Column, MetaData, String, Table, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.platform.audit import AuditBase, AuditEvent, AuditRecorder
from backend.platform.outbox import (
    OutboxConflictError,
    OutboxEvent,
    OutboxMetadata,
    SqlAlchemyOutboxWriter,
    read_outbox_event,
)
from backend.platform.persistence import SqlAlchemyUnitOfWork
from backend.platform.persistence.session import get_engine
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url

business_metadata = MetaData()
confirmations = Table(
    "plt02_confirmations",
    business_metadata,
    Column("confirmation_id", String, primary_key=True),
)


def _event(*, payload_suffix: str = "v1") -> OutboxEvent:
    return OutboxEvent.create(
        tenant_id="tenant-a",
        family_id="family-a",
        aggregate_type="GuardianDecision",
        aggregate_id="decision-1",
        event_name="GuardianDecisionConfirmed",
        event_version=1,
        idempotency_key="confirm-1",
        request_hash="request-hash-v1",
        correlation_id="correlation-1",
        payload={
            "scope_ref": "scope-1",
            "signal_ref": "signal-1",
            "signal_version": 2,
            "reviewed_draft_ref": "draft-1",
            "draft_version": 3,
            "provenance_ref": "provenance-1",
            "human_gate_receipt_ref": "gate-1",
            "boundary": "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME",
            "payload_suffix": payload_suffix,
        },
        occurred_at=datetime(2026, 9, 1, tzinfo=UTC),
    )


def _audit() -> AuditRecorder:
    recorder = AuditRecorder()
    recorder.record(
        AuditEvent(
            actor_id="guardian-a",
            tenant_id="tenant-a",
            action="guardian.confirm",
            resource_type="GuardianDecision",
            resource_id="decision-1",
            reason="adult confirmed the displayed understanding",
            correlation_id="correlation-1",
            after={"status": "CONFIRMED"},
        )
    )
    return recorder


async def _create_schema(engine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(AuditBase.metadata.create_all)
        await connection.run_sync(OutboxMetadata.create_all)
        await connection.run_sync(business_metadata.create_all)


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = get_engine(f"sqlite+aiosqlite:///:memory:?plt02={uuid.uuid4().hex}")
    await _create_schema(engine)
    yield async_sessionmaker(bind=engine, expire_on_commit=False)
    await engine.dispose()


async def _count(session: AsyncSession, table: Table) -> int:
    return int((await session.execute(select(func.count()).select_from(table))).scalar_one())


async def test_business_audit_and_outbox_commit_and_read_back_together(session_factory) -> None:
    writer = SqlAlchemyOutboxWriter()
    event = _event()
    recorder = _audit()
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        await uow.session.execute(confirmations.insert().values(confirmation_id="decision-1"))
        await recorder.flush(uow.session)
        result = await writer.append(uow.session, event)
        await uow.commit()

    assert result.replayed is False
    async with session_factory() as verify:
        assert await _count(verify, confirmations) == 1
        assert await _count(verify, AuditBase.metadata.tables["platform_audit_events"]) == 1
        assert await _count(verify, OutboxMetadata.tables["outbox_events"]) == 1
        stored = await read_outbox_event(verify, event.event_id)
    assert stored == event
    assert stored.payload["human_gate_receipt_ref"] == "gate-1"
    assert stored.request_hash == "request-hash-v1"


async def test_append_does_not_commit_and_outer_rollback_removes_event(session_factory) -> None:
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        await SqlAlchemyOutboxWriter().append(uow.session, _event())

    async with session_factory() as verify:
        assert await _count(verify, OutboxMetadata.tables["outbox_events"]) == 0


async def test_duplicate_append_replays_but_changed_payload_conflicts(session_factory) -> None:
    writer = SqlAlchemyOutboxWriter()
    event = _event()
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        await writer.append(uow.session, event)
        await uow.commit()
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        replay = await writer.append(uow.session, event)
        assert replay.replayed is True
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        with pytest.raises(OutboxConflictError, match="outbox_event_id_payload_mismatch"):
            await writer.append(uow.session, _event(payload_suffix="changed"))


async def test_outbox_failure_rolls_business_and_audit_back(session_factory) -> None:
    recorder = _audit()
    with pytest.raises(RuntimeError, match="injected_outbox_failure"):
        async with SqlAlchemyUnitOfWork(session_factory) as uow:
            await uow.session.execute(confirmations.insert().values(confirmation_id="decision-1"))
            await recorder.flush(uow.session)
            raise RuntimeError("injected_outbox_failure")

    async with session_factory() as verify:
        assert await _count(verify, confirmations) == 0
        assert await _count(verify, AuditBase.metadata.tables["platform_audit_events"]) == 0


async def test_event_survives_engine_restart(tmp_path) -> None:
    path = tmp_path / "outbox.sqlite3"
    first = get_engine(f"sqlite+aiosqlite:///{path}?run=first")
    await _create_schema(first)
    async with SqlAlchemyUnitOfWork(async_sessionmaker(first, expire_on_commit=False)) as uow:
        await SqlAlchemyOutboxWriter().append(uow.session, _event())
        await uow.commit()
    await first.dispose()

    restarted = get_engine(f"sqlite+aiosqlite:///{path}?run=restarted")
    async with async_sessionmaker(restarted, expire_on_commit=False)() as session:
        stored = await read_outbox_event(session, _event().event_id)
    assert stored == _event()
    await restarted.dispose()


async def test_real_postgres_append_replay_and_rollback() -> None:
    if postgres_test_url() is None:
        pytest.skip(SKIP_REASON)
    combined = MetaData()
    AuditBase.metadata.tables["platform_audit_events"].to_metadata(combined)
    OutboxMetadata.tables["outbox_events"].to_metadata(combined)
    confirmations.to_metadata(combined)
    async with postgres_schema_engine(combined) as engine:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        await test_business_audit_and_outbox_commit_and_read_back_together(factory)
        await test_duplicate_append_replays_but_changed_payload_conflicts(factory)
