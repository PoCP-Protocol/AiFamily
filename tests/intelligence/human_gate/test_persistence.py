from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.human_gate import (
    ActionProposal,
    ActorType,
    DecisionOutcome,
    GateScope,
    GateStatus,
    HumanGateBase,
    HumanGateError,
    SqlAlchemyHumanGate,
)
from backend.intelligence.human_gate.persistence import HumanTaskRow
from backend.platform.audit import AuditBase, AuditRecorder, read_all_events

NOW = datetime(2026, 8, 30, 9, tzinfo=UTC)


def _scope() -> GateScope:
    return GateScope(
        tenant_id="tenant-1",
        family_id="family-1",
        subject_ids=("child-1",),
        purpose="service_collaboration",
        consent_version="consent.v1",
        correlation_id="corr-1",
    )


def _proposal(*, action_arguments: dict[str, object] | None = None) -> ActionProposal:
    return ActionProposal(
        proposal_id="proposal-1",
        draft_id="draft-1",
        draft_status="DRAFT",
        action_name="CONFIRM_SERVICE_TASK_ASSIGNMENT",
        action_arguments=action_arguments
        or {"service_task_id": "task-1", "provider_id": "provider-1"},
        scope=_scope(),
        allowed_actor_types=(ActorType.GUARDIAN,),
        risk_level="HIGH",
        provenance_ref="model-draft:request-1",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=24),
    )


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
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_human_task_decision_and_provenance_survive_a_new_session(session_factory):
    recorder = AuditRecorder()
    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        task = await gate.submit(_proposal(), recorder=recorder)
        decided, request = await gate.decide(
            task.task_id,
            actor_id="guardian-1",
            actor_type=ActorType.GUARDIAN,
            outcome=DecisionOutcome.ACCEPT,
            recorder=recorder,
            now=NOW + timedelta(hours=1),
        )
        assert await gate.flush_audit(recorder) == 2
        await gate.commit()

    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        loaded = await gate.get(task.task_id)
        events = await read_all_events(session, tenant_id="tenant-1")

    assert loaded == decided
    assert loaded.status is GateStatus.DECIDED
    assert loaded.decision is not None
    assert loaded.decision.actor_id == "guardian-1"
    assert loaded.action_request == request
    assert loaded.proposal.provenance_ref == "model-draft:request-1"
    assert loaded.proposal.scope == _scope()
    assert [event.action for event in events] == ["CREATE_HUMAN_TASK", "DECIDE_HUMAN_TASK"]


@pytest.mark.asyncio
async def test_human_gate_replay_is_exact_and_conflicting_content_is_rejected(session_factory):
    recorder = AuditRecorder()
    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        first = await gate.submit(_proposal(), recorder=recorder)
        await gate.flush_audit(recorder)
        await gate.commit()

    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        replay = await gate.submit(_proposal(), recorder=AuditRecorder())
        decided, request = await gate.decide(
            first.task_id,
            actor_id="guardian-1",
            actor_type="GUARDIAN",
            outcome="ACCEPT",
            recorder=AuditRecorder(),
            now=NOW + timedelta(hours=1),
        )
        assert replay == first
        assert decided.status is GateStatus.DECIDED
        assert request is not None
        await gate.flush_audit(AuditRecorder())

    # A proposal id is a durable idempotency key, not a mutable label.
    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        with pytest.raises(HumanGateError, match="PROPOSAL_REPLAY_MISMATCH"):
            await gate.submit(
                _proposal(action_arguments={"service_task_id": "different-task"}),
                recorder=AuditRecorder(),
            )


@pytest.mark.asyncio
async def test_uncommitted_human_gate_state_and_audit_are_rolled_back(session_factory):
    recorder = AuditRecorder()
    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        await gate.submit(_proposal(), recorder=recorder)
        await gate.flush_audit(recorder)
        # Deliberately omit commit: closing the session rolls both rows back.

    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        with pytest.raises(HumanGateError, match="TASK_NOT_FOUND"):
            await gate.get("human-task:tenant-1:proposal-1")
        assert await read_all_events(session, tenant_id="tenant-1") == []


@pytest.mark.asyncio
async def test_expiry_is_persisted_and_second_sweep_is_idempotent(session_factory):
    recorder = AuditRecorder()
    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        await gate.submit(_proposal(), recorder=recorder)
        await gate.flush_audit(recorder)
        await gate.commit()

    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        assert await gate.expire_due(recorder=recorder, now=NOW + timedelta(days=2)) == 1
        assert await gate.flush_audit(recorder) == 1
        await gate.commit()

    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        assert await gate.expire_due(
            recorder=AuditRecorder(), now=NOW + timedelta(days=2)
        ) == 0
        assert (
            await gate.get("human-task:tenant-1:proposal-1")
        ).status is GateStatus.EXPIRED


@pytest.mark.asyncio
async def test_expired_decision_does_not_create_a_named_action_request(session_factory):
    recorder = AuditRecorder()
    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        task = await gate.submit(_proposal(), recorder=recorder)
        with pytest.raises(HumanGateError, match="TASK_EXPIRED"):
            await gate.decide(
                task.task_id,
                actor_id="guardian-1",
                actor_type=ActorType.GUARDIAN,
                outcome=DecisionOutcome.ACCEPT,
                recorder=recorder,
                now=NOW + timedelta(days=2),
            )
        assert await gate.flush_audit(recorder) == 2
        await gate.commit()

    async with session_factory() as session:
        task = await SqlAlchemyHumanGate(session).get("human-task:tenant-1:proposal-1")
        assert task.status is GateStatus.EXPIRED
        assert task.decision is None
        assert task.action_request is None


@pytest.mark.asyncio
async def test_audit_flush_failure_does_not_claim_a_durable_human_task(session_factory):
    class FailingRecorder(AuditRecorder):
        async def flush(self, session):
            raise RuntimeError("audit store unavailable")

    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        await gate.submit(_proposal(), recorder=FailingRecorder())
        with pytest.raises(RuntimeError, match="audit store unavailable"):
            await gate.flush_audit(FailingRecorder())
        await gate.rollback()

    async with session_factory() as session:
        assert await session.get(HumanTaskRow, "human-task:tenant-1:proposal-1") is None
        assert await read_all_events(session, tenant_id="tenant-1") == []


@pytest.mark.asyncio
async def test_persisted_scalar_tampering_fails_closed(session_factory):
    recorder = AuditRecorder()
    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        await gate.submit(_proposal(), recorder=recorder)
        await gate.flush_audit(recorder)
        await gate.commit()

    async with session_factory() as session:
        row = await session.get(HumanTaskRow, "human-task:tenant-1:proposal-1")
        assert row is not None
        row.provenance_ref = "tampered-provenance"
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(HumanGateError, match="PERSISTED_SHAPE_INVALID"):
            await SqlAlchemyHumanGate(session).get("human-task:tenant-1:proposal-1")


@pytest.mark.asyncio
async def test_ai_actor_cannot_decide_a_persisted_task(session_factory):
    recorder = AuditRecorder()
    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        task = await gate.submit(_proposal(), recorder=recorder)
        with pytest.raises(HumanGateError, match="HUMAN_REVIEWER_REQUIRED"):
            await gate.decide(
                task.task_id,
                actor_id="AI:agent-1",
                actor_type=ActorType.AI,
                outcome=DecisionOutcome.ACCEPT,
                recorder=recorder,
                now=NOW + timedelta(hours=1),
            )
        assert (await gate.get(task.task_id)).status is GateStatus.OPEN


@pytest.mark.asyncio
async def test_active_claim_rejects_competing_worker_and_expired_claim_is_takeover_safe(
    session_factory,
):
    recorder = AuditRecorder()
    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        task = await gate.submit(_proposal(), recorder=recorder)
        await gate.decide(
            task.task_id,
            actor_id="guardian-1",
            actor_type=ActorType.GUARDIAN,
            outcome=DecisionOutcome.ACCEPT,
            recorder=recorder,
            now=NOW + timedelta(hours=1),
        )
        await gate.flush_audit(recorder)
        await gate.commit()

    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        with pytest.raises(HumanGateError, match="INVALID_CLAIM_OWNER"):
            await gate.claim_accepted(
                task.task_id,
                claim_owner="AI:worker",
                lease_ttl=timedelta(hours=2),
                recorder=AuditRecorder(),
                now=NOW + timedelta(hours=2),
            )
        claim = await gate.claim_accepted(
            task.task_id,
            claim_owner="worker-a",
            lease_ttl=timedelta(hours=2),
            recorder=recorder,
            now=NOW + timedelta(hours=2),
        )
        assert claim.claim_owner == "worker-a"
        assert claim.claim_expires_at == NOW + timedelta(hours=4)
        await gate.flush_audit(recorder)
        await gate.commit()

    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        with pytest.raises(HumanGateError, match="TASK_ALREADY_CLAIMED"):
            await gate.claim_accepted(
                task.task_id,
                claim_owner="worker-b",
                lease_ttl=timedelta(hours=2),
                recorder=AuditRecorder(),
                now=NOW + timedelta(hours=3),
            )

    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        takeover = await gate.claim_accepted(
            task.task_id,
            claim_owner="worker-b",
            lease_ttl=timedelta(hours=2),
            recorder=recorder,
            now=NOW + timedelta(hours=5),
        )
        assert takeover.claim_owner == "worker-b"
        await gate.flush_audit(recorder)
        await gate.commit()

    async with session_factory() as session:
        row = await session.get(HumanTaskRow, task.task_id)
        assert row is not None
        assert row.claim_owner == "worker-b"
        events = await read_all_events(session, tenant_id="tenant-1")
        assert [event.action for event in events] == [
            "CREATE_HUMAN_TASK",
            "DECIDE_HUMAN_TASK",
            "CLAIM_HUMAN_TASK",
            "CLAIM_HUMAN_TASK",
        ]


@pytest.mark.asyncio
async def test_claim_completion_is_owner_and_expiry_bound(session_factory):
    recorder = AuditRecorder()
    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        task = await gate.submit(_proposal(), recorder=recorder)
        await gate.decide(
            task.task_id,
            actor_id="guardian-1",
            actor_type=ActorType.GUARDIAN,
            outcome=DecisionOutcome.ACCEPT,
            recorder=recorder,
            now=NOW + timedelta(hours=1),
        )
        await gate.flush_audit(recorder)
        await gate.commit()

    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        await gate.claim_accepted(
            task.task_id,
            claim_owner="worker-a",
            lease_ttl=timedelta(hours=1),
            recorder=recorder,
            now=NOW + timedelta(hours=2),
        )
        await gate.flush_audit(recorder)
        await gate.commit()

    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        with pytest.raises(HumanGateError, match="CLAIM_NOT_OWNED"):
            await gate.complete_claim(
                task.task_id,
                claim_owner="worker-b",
                recorder=AuditRecorder(),
                now=NOW + timedelta(hours=2, minutes=30),
            )
        with pytest.raises(HumanGateError, match="CLAIM_EXPIRED"):
            await gate.complete_claim(
                task.task_id,
                claim_owner="worker-a",
                recorder=AuditRecorder(),
                now=NOW + timedelta(hours=4),
            )
        row = await session.get(HumanTaskRow, task.task_id)
        assert row is not None
        assert row.claim_owner == "worker-a"


@pytest.mark.asyncio
async def test_claim_audit_failure_does_not_persist_the_lease(session_factory):
    recorder = AuditRecorder()
    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        task = await gate.submit(_proposal(), recorder=recorder)
        await gate.decide(
            task.task_id,
            actor_id="guardian-1",
            actor_type=ActorType.GUARDIAN,
            outcome=DecisionOutcome.ACCEPT,
            recorder=recorder,
            now=NOW + timedelta(hours=1),
        )
        await gate.flush_audit(recorder)
        await gate.commit()

    class FailingRecorder(AuditRecorder):
        async def flush(self, session):
            raise RuntimeError("audit store unavailable")

    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        failing = FailingRecorder()
        await gate.claim_accepted(
            task.task_id,
            claim_owner="worker-a",
            lease_ttl=timedelta(hours=1),
            recorder=failing,
            now=NOW + timedelta(hours=2),
        )
        with pytest.raises(RuntimeError, match="audit store unavailable"):
            await gate.flush_audit(failing)
        await gate.rollback()

    async with session_factory() as session:
        row = await session.get(HumanTaskRow, task.task_id)
        assert row is not None
        assert row.claim_owner is None
        assert row.claim_expires_at is None
        events = await read_all_events(session, tenant_id="tenant-1")
        assert [event.action for event in events] == [
            "CREATE_HUMAN_TASK",
            "DECIDE_HUMAN_TASK",
        ]
