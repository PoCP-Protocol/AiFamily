from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.human_gate import (
    ActionProposal,
    ActorType,
    DecisionOutcome,
    GateScope,
    HumanGateBase,
    HumanGateError,
    SqlAlchemyHumanGate,
)
from backend.intelligence.human_gate.contracts import NamedActionRequest
from backend.intelligence.tool_runtime.accepted_delivery import (
    AcceptedActionDeliveryBase,
    AcceptedActionDeliveryRow,
    AcceptedActionDeliveryStatus,
    SqlAlchemyAcceptedActionDeliveryStore,
)
from backend.intelligence.tool_runtime.accepted_dispatch import (
    AcceptedNamedActionDispatcher,
    ActionExecutionReceipt,
)
from backend.intelligence.tool_runtime.accepted_worker import (
    AcceptedActionWorkerStatus,
    AcceptedNamedActionWorker,
)
from backend.platform.audit import AuditBase, AuditRecorder

NOW = datetime(2026, 8, 30, 10, tzinfo=UTC)


def _request() -> NamedActionRequest:
    scope = GateScope(
        tenant_id="tenant-takeover",
        family_id="family-takeover",
        subject_ids=("child-takeover",),
        purpose="service_collaboration",
        consent_version="consent.v1",
        correlation_id="corr-takeover",
    )
    return NamedActionRequest(
        request_id="request-takeover-001",
        action_name="CONFIRM_SERVICE_TASK_ASSIGNMENT",
        action_arguments={"service_task_id": "task-takeover", "provider_id": "expert-1"},
        task_id="human-task-takeover",
        proposal_id="proposal-takeover",
        decision_id="decision-takeover",
        actor_id="guardian-takeover",
        actor_type=ActorType.GUARDIAN,
        scope=scope,
        provenance_ref="human-gate:takeover",
        idempotency_key="idem-takeover",
    )


def _proposal(request: NamedActionRequest) -> ActionProposal:
    return ActionProposal(
        proposal_id=request.proposal_id,
        draft_id="draft-takeover",
        draft_status="DRAFT",
        action_name=request.action_name,
        action_arguments=request.action_arguments,
        scope=request.scope,
        allowed_actor_types=(ActorType.GUARDIAN,),
        risk_level="HIGH",
        provenance_ref=request.provenance_ref,
        created_at=NOW,
        expires_at=NOW + timedelta(days=1),
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
        await connection.run_sync(AcceptedActionDeliveryBase.metadata.create_all)
        await connection.run_sync(AuditBase.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _seed(factory, request: NamedActionRequest) -> NamedActionRequest:
    async with factory() as session:
        gate = SqlAlchemyHumanGate(session)
        recorder = AuditRecorder()
        task = await gate.submit(
            _proposal(request), recorder=recorder, task_id=request.task_id
        )
        _, accepted_request = await gate.decide(
            task.task_id,
            actor_id=request.actor_id,
            actor_type=ActorType.GUARDIAN,
            outcome=DecisionOutcome.ACCEPT,
            recorder=recorder,
            now=NOW + timedelta(minutes=1),
        )
        await gate.flush_audit(recorder)
        await gate.commit()
        assert accepted_request is not None
        return accepted_request


@pytest.mark.asyncio
async def test_worker_takes_over_expired_claim_and_replays_idempotently(session_factory) -> None:
    request = await _seed(session_factory, _request())

    # Simulate worker A crashing after committing its claim but before running
    # the dispatcher.  Worker B must be blocked until the lease expires.
    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        recorder = AuditRecorder()
        await gate.claim_accepted(
            request.task_id,
            claim_owner="worker-a",
            lease_ttl=timedelta(hours=1),
            recorder=recorder,
            now=NOW,
        )
        await gate.flush_audit(recorder)
        await gate.commit()

    calls = 0

    async def handler(value):
        nonlocal calls
        calls += 1
        return ActionExecutionReceipt(
            request_id=value.request_id,
            action_name=value.action_name,
            result_ref="assignment-takeover",
        )

    async with session_factory() as session:
        worker = AcceptedNamedActionWorker(
            SqlAlchemyHumanGate(session),
            SqlAlchemyAcceptedActionDeliveryStore(session),
            AcceptedNamedActionDispatcher({request.action_name: handler}),
        )
        with pytest.raises(HumanGateError, match="TASK_ALREADY_CLAIMED"):
            await worker.consume(
                request.task_id,
                claim_owner="worker-b",
                lease_ttl=timedelta(hours=1),
                claimed_at=NOW + timedelta(minutes=30),
            )

    async with session_factory() as session:
        worker = AcceptedNamedActionWorker(
            SqlAlchemyHumanGate(session),
            SqlAlchemyAcceptedActionDeliveryStore(session),
            AcceptedNamedActionDispatcher({request.action_name: handler}),
        )
        result = await worker.consume(
            request.task_id,
            claim_owner="worker-b",
            lease_ttl=timedelta(hours=1),
            claimed_at=NOW + timedelta(hours=2),
            completed_at=NOW + timedelta(hours=2),
        )
        assert result.status is AcceptedActionWorkerStatus.SUCCEEDED
        persisted = await SqlAlchemyAcceptedActionDeliveryStore(session).get(
            request.request_id
        )
        rows = (await session.execute(select(AcceptedActionDeliveryRow))).scalars().all()
        assert [row.request_id for row in rows] == [request.request_id]
        assert persisted is not None

    # A new process/session sees the durable receipt and must not call the
    # handler a second time, even though the HumanTask itself remains decided.
    async with session_factory() as session:
        worker = AcceptedNamedActionWorker(
            SqlAlchemyHumanGate(session),
            SqlAlchemyAcceptedActionDeliveryStore(session),
            AcceptedNamedActionDispatcher({request.action_name: handler}),
        )
        replay = await worker.consume(
            request.task_id,
            claim_owner="worker-c",
            lease_ttl=timedelta(hours=1),
            claimed_at=NOW + timedelta(hours=3),
            completed_at=NOW + timedelta(hours=3),
        )
        delivery = await SqlAlchemyAcceptedActionDeliveryStore(session).get(request.request_id)
        assert replay.status is AcceptedActionWorkerStatus.SUCCEEDED
        assert delivery is not None
        assert delivery.status is AcceptedActionDeliveryStatus.SUCCEEDED
        assert delivery.attempts == 1

    assert calls == 1
