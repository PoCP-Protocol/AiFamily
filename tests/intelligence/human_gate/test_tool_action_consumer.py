from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.experience.outbox_worker import (
    DeliveryStatus,
    InMemoryExperienceDeadLetterSink,
)
from backend.intelligence.human_gate import (
    HumanGateBase,
    HumanTaskRow,
    SqlAlchemyHumanGate,
    SqlAlchemyToolActionHumanGateConsumer,
)
from backend.intelligence.human_gate.contracts import GateScope, GateStatus
from backend.intelligence.tool_runtime import (
    PendingNamedAction,
    SqlAlchemyToolActionOutbox,
    ToolActionOutboxBase,
    ToolActionOutboxWorker,
    ToolCallResult,
)
from backend.platform.audit import AuditBase, read_all_events

NOW = datetime(2026, 8, 30, 2, tzinfo=UTC)


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(HumanGateBase.metadata.create_all)
        await connection.run_sync(ToolActionOutboxBase.metadata.create_all)
        await connection.run_sync(AuditBase.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _result() -> ToolCallResult:
    scope = GateScope(
        tenant_id="tenant-1",
        family_id="family-1",
        subject_ids=("child-1",),
        purpose="growth_planning",
        consent_version="consent-v1",
        correlation_id="corr-1",
    )
    return ToolCallResult(
        call_id="call-1",
        tool_id="growth-planner",
        agent_id="planner",
        tenant_id="tenant-1",
        family_id="family-1",
        pending_action=PendingNamedAction(
            action_name="CREATE_GROWTH_PLAN",
            action_arguments={"goal": "家庭共读"},
            scope=scope,
            provenance_ref="agent-run:1",
            risk_level="HIGH",
            expires_at=NOW + timedelta(days=2),
        ),
        created_at=NOW,
    )


@pytest.mark.asyncio
async def test_worker_atomically_delivers_task_audit_and_ack(session_factory):
    async with session_factory() as session:
        outbox = SqlAlchemyToolActionOutbox(session)
        consumer = SqlAlchemyToolActionHumanGateConsumer(session, clock=lambda: NOW)
        sink = InMemoryExperienceDeadLetterSink()
        async with session.begin():
            await outbox.append(_result(), use_case="growth_planning")
            report = await ToolActionOutboxWorker(
                outbox, consumer, dead_letter_sink=sink
            ).run_once()
        assert report.results[0].status is DeliveryStatus.PUBLISHED

    async with session_factory() as session:
        row = (await session.execute(select(HumanTaskRow))).scalar_one()
        task = await SqlAlchemyHumanGate(session).get(row.task_id)
        assert task.status is GateStatus.OPEN
        assert task.proposal.scope.tenant_id == "tenant-1"
        assert await SqlAlchemyToolActionOutbox(session).pending() == ()
        events = await read_all_events(session, tenant_id="tenant-1")
        assert [event.action for event in events] == ["CREATE_HUMAN_TASK"]
        assert sink.messages() == ()
