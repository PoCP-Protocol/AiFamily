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
    HumanGateBase,
    HumanGateError,
    SqlAlchemyHumanGate,
)
from backend.platform.audit import AuditBase, AuditRecorder

NOW = datetime(2026, 8, 30, 9, tzinfo=UTC)


def _proposal(proposal_id: str) -> ActionProposal:
    scope = GateScope(
        tenant_id="tenant-queue",
        family_id="family-queue",
        subject_ids=("child-queue",),
        purpose="service_collaboration",
        consent_version="consent.v1",
        correlation_id=f"corr-{proposal_id}",
    )
    return ActionProposal(
        proposal_id=proposal_id,
        draft_id=f"draft-{proposal_id}",
        draft_status="DRAFT",
        action_name="CONFIRM_SERVICE_TASK_ASSIGNMENT",
        action_arguments={"service_task_id": f"task-{proposal_id}"},
        scope=scope,
        allowed_actor_types=(ActorType.GUARDIAN,),
        risk_level="HIGH",
        provenance_ref=f"model:{proposal_id}",
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
async def test_queue_read_returns_only_accepted_tasks_in_stable_order(session_factory) -> None:
    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        first = await gate.submit(_proposal("proposal-a"), recorder=AuditRecorder())
        second = await gate.submit(_proposal("proposal-b"), recorder=AuditRecorder())
        await gate.decide(
            first.task_id,
            actor_id="guardian-queue",
            actor_type=ActorType.GUARDIAN,
            outcome=DecisionOutcome.ACCEPT,
            recorder=AuditRecorder(),
            now=NOW + timedelta(minutes=1),
        )
        await session.commit()

    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        assert await gate.pending_accepted_task_ids(limit=100) == (first.task_id,)
        assert await gate.pending_accepted_task_ids(limit=0) == ()
        with pytest.raises(HumanGateError, match="INVALID_QUEUE_LIMIT"):
            await gate.pending_accepted_task_ids(limit=-1)
        assert second.task_id not in await gate.pending_accepted_task_ids(limit=100)
