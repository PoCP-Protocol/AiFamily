from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.human_gate import (
    ActorType,
    HumanGateBase,
    HumanGateError,
    SqlAlchemyHumanGate,
    ToolActionHumanGateInbox,
)
from backend.intelligence.human_gate.contracts import GateScope
from backend.intelligence.tool_runtime import (
    PendingNamedAction,
    SqlAlchemyToolActionOutbox,
    ToolActionOutboxBase,
    ToolCallResult,
)
from backend.platform.audit import AuditBase, AuditRecorder

NOW = datetime(2026, 8, 30, 2, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(HumanGateBase.metadata.create_all)
        await connection.run_sync(AuditBase.metadata.create_all)
        await connection.run_sync(ToolActionOutboxBase.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _result(*, expires_at: datetime = NOW + timedelta(hours=1)) -> ToolCallResult:
    scope = GateScope(
        tenant_id="tenant-1",
        family_id="family-1",
        subject_ids=("child-1",),
        purpose="growth_planning",
        consent_version="consent-v1",
        correlation_id="call-1",
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
            expires_at=expires_at,
        ),
        created_at=NOW,
    )


async def _stored(session_factory):
    async with session_factory() as session, session.begin():
        return await SqlAlchemyToolActionOutbox(session).append(
            _result(), use_case="growth_planning"
        )


@pytest.mark.asyncio
async def test_deliver_creates_durable_open_task_with_scope_and_provenance(session_factory):
    stored = await _stored(session_factory)
    async with session_factory() as session:
        recorder = AuditRecorder()
        async with session.begin():
            task = await ToolActionHumanGateInbox(SqlAlchemyHumanGate(session)).deliver(
                stored, recorder=recorder, now=NOW + timedelta(minutes=1)
            )
            assert len(recorder.all_events()) == 1
            await recorder.flush(session)

        assert task.status.value == "OPEN"
        assert task.proposal.action_name == "CREATE_GROWTH_PLAN"
        assert task.proposal.scope == stored.scope
        assert task.proposal.provenance_ref == stored.provenance_ref
        assert task.proposal.allowed_actor_types == (ActorType.GUARDIAN,)


@pytest.mark.asyncio
async def test_delivery_replay_is_idempotent_by_tenant_and_call_id(session_factory):
    stored = await _stored(session_factory)
    async with session_factory() as session, session.begin():
        first = await ToolActionHumanGateInbox(SqlAlchemyHumanGate(session)).deliver(
            stored, recorder=AuditRecorder(), now=NOW + timedelta(minutes=1)
        )
    async with session_factory() as session, session.begin():
        replay = await ToolActionHumanGateInbox(SqlAlchemyHumanGate(session)).deliver(
            stored, recorder=AuditRecorder(), now=NOW + timedelta(minutes=2)
        )
    assert replay == first


@pytest.mark.asyncio
async def test_delivery_rejects_tampered_payload_and_expired_message(session_factory):
    stored = await _stored(session_factory)
    tampered = replace(stored, payload={**stored.payload, "action_name": "DELETE"})
    async with session_factory() as session:
        with pytest.raises(HumanGateError, match="INVALID_TOOL_ACTION_MESSAGE"):
            await ToolActionHumanGateInbox(SqlAlchemyHumanGate(session)).deliver(
                tampered, recorder=AuditRecorder(), now=NOW
            )

    expired = replace(stored, expires_at=NOW - timedelta(seconds=1))
    async with session_factory() as session:
        with pytest.raises(HumanGateError, match="TOOL_ACTION_EXPIRED"):
            await ToolActionHumanGateInbox(SqlAlchemyHumanGate(session)).deliver(
                expired, recorder=AuditRecorder(), now=NOW
            )
