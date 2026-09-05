from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.experience.outbox_worker import (
    DeliveryStatus,
    InMemoryExperienceDeadLetterSink,
)
from backend.intelligence.human_gate.contracts import GateScope
from backend.intelligence.tool_runtime import (
    PendingNamedAction,
    SqlAlchemyToolActionOutbox,
    ToolActionOutboxBase,
    ToolActionOutboxConflict,
    ToolActionOutboxError,
    ToolActionOutboxWorker,
    ToolCallResult,
    envelope_from_result,
)

NOW = datetime(2026, 8, 30, 2, 0, tzinfo=UTC)


@pytest.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(ToolActionOutboxBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def result(**overrides) -> ToolCallResult:
    values = {
        "call_id": "call-1",
        "tool_id": "create_growth_plan",
        "agent_id": "planner",
        "tenant_id": "tenant-1",
        "family_id": "family-1",
        "pending_action": PendingNamedAction(
            action_name="CREATE_GROWTH_PLAN",
            action_arguments={"goal": "家庭共读"},
            scope=GateScope(
                tenant_id="tenant-1",
                family_id="family-1",
                subject_ids=("child-1",),
                purpose="growth_planning",
                consent_version="consent-v1",
                correlation_id="call-1",
            ),
            provenance_ref="agent-run:1",
            risk_level="HIGH",
            expires_at=NOW + timedelta(minutes=15),
        ),
        "created_at": NOW,
    }
    values.update(overrides)
    return ToolCallResult(**values)


@pytest.mark.asyncio
async def test_append_persists_pending_gate_envelope_and_scope(session_factory) -> None:
    async with session_factory() as session:
        outbox = SqlAlchemyToolActionOutbox(session)
        async with session.begin():
            stored = await outbox.append(result(), use_case="growth_planning")

        assert stored.status == "PENDING_HUMAN_CONFIRMATION"
        assert stored.human_gate_state == "PENDING_HUMAN_CONFIRMATION"
        assert stored.may_mutate_business_state is False
        assert stored.scope.family_id == "family-1"
        assert stored.scope.subject_ids == ("child-1",)
        assert stored.provenance_ref == "agent-run:1"
        assert stored.event_type == "tool.named_action.pending"
        assert stored.payload["event_type"] == "tool.named_action.pending"
        assert stored.payload["action_name"] == "CREATE_GROWTH_PLAN"
        assert "decision_id" not in stored.payload
        assert "actor_id" not in stored.payload
        assert await outbox.pending() == (stored,)


@pytest.mark.asyncio
async def test_use_case_defaults_to_gate_scope_purpose(session_factory) -> None:
    async with session_factory() as session:
        outbox = SqlAlchemyToolActionOutbox(session)
        async with session.begin():
            stored = await outbox.append(result())
        assert stored.use_case == "growth_planning"


@pytest.mark.asyncio
async def test_same_call_id_replays_even_when_generated_timestamps_change(session_factory) -> None:
    async with session_factory() as session:
        outbox = SqlAlchemyToolActionOutbox(session)
        async with session.begin():
            first = await outbox.append(result(), use_case="growth_planning")
        await session.rollback()

        replay = result(
            created_at=NOW + timedelta(seconds=30),
            pending_action=PendingNamedAction(
                action_name="CREATE_GROWTH_PLAN",
                action_arguments={"goal": "家庭共读"},
                scope=first.scope,
                provenance_ref="agent-run:1",
                risk_level="HIGH",
                expires_at=NOW + timedelta(minutes=16),
            ),
        )
        async with session.begin():
            second = await outbox.append(replay, use_case="growth_planning")
        assert second.message_id == first.message_id
        assert second.created_at == first.created_at

        await session.rollback()
        changed = result(
            pending_action=PendingNamedAction(
                action_name="CREATE_GROWTH_PLAN",
                action_arguments={"goal": "家庭运动"},
                scope=first.scope,
                provenance_ref="agent-run:1",
                risk_level="HIGH",
                expires_at=NOW + timedelta(minutes=15),
            )
        )
        with pytest.raises(ToolActionOutboxConflict, match="REPLAY"):
            async with session.begin():
                await outbox.append(changed, use_case="growth_planning")


@pytest.mark.asyncio
async def test_scope_mismatch_fails_before_sql_write(session_factory) -> None:
    mismatched_scope = GateScope(
        tenant_id="tenant-1",
        family_id="family-other",
        subject_ids=("child-1",),
        purpose="growth_planning",
        consent_version="consent-v1",
        correlation_id="call-1",
    )
    mismatched = result(
        pending_action=PendingNamedAction(
            action_name="CREATE_GROWTH_PLAN",
            action_arguments={"goal": "家庭共读"},
            scope=mismatched_scope,
            provenance_ref="agent-run:1",
            risk_level="HIGH",
            expires_at=NOW + timedelta(minutes=15),
        )
    )
    async with session_factory() as session:
        outbox = SqlAlchemyToolActionOutbox(session)
        with pytest.raises(ToolActionOutboxError, match="SCOPE"):
            await outbox.append(mismatched, use_case="growth_planning")
        assert await outbox.pending() == ()


@pytest.mark.asyncio
async def test_purpose_mismatch_is_not_relabelled_at_the_outbox_boundary(session_factory) -> None:
    async with session_factory() as session:
        outbox = SqlAlchemyToolActionOutbox(session)
        with pytest.raises(ToolActionOutboxError, match="PURPOSE"):
            await outbox.append(result(), use_case="unrelated_use_case")
        assert await outbox.pending() == ()


def test_envelope_rejects_accepted_state_before_persistence() -> None:
    envelope = envelope_from_result(result())
    with pytest.raises(ToolActionOutboxError, match="PENDING"):
        type(envelope)(
            message_id=envelope.message_id,
            call_id=envelope.call_id,
            tool_id=envelope.tool_id,
            agent_id=envelope.agent_id,
            tenant_id=envelope.tenant_id,
            family_id=envelope.family_id,
            use_case=envelope.use_case,
            action_name=envelope.action_name,
            action_arguments=envelope.action_arguments,
            scope=envelope.scope,
            provenance_ref=envelope.provenance_ref,
            risk_level=envelope.risk_level,
            status="ACCEPTED",
            created_at=envelope.created_at,
            expires_at=envelope.expires_at,
        )


@pytest.mark.asyncio
async def test_shared_worker_acknowledges_only_after_human_gate_inbox_consumer(
    session_factory,
) -> None:
    class HumanGateInbox:
        def __init__(self) -> None:
            self.messages = []

        async def consume(self, message) -> None:
            self.messages.append(message)
            assert message.status == "PENDING_HUMAN_CONFIRMATION"
            assert message.may_mutate_business_state is False

    inbox = HumanGateInbox()
    sink = InMemoryExperienceDeadLetterSink()
    async with session_factory() as session:
        outbox = SqlAlchemyToolActionOutbox(session)
        async with session.begin():
            await outbox.append(result(), use_case="growth_planning")
        await session.rollback()
        worker = ToolActionOutboxWorker(outbox, inbox, dead_letter_sink=sink)
        async with session.begin():
            report = await worker.run_once()
        assert report.results[0].status is DeliveryStatus.PUBLISHED
        assert len(inbox.messages) == 1
        assert await outbox.pending() == ()
    assert sink.messages() == ()
