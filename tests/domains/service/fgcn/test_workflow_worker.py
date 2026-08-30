from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.domains.service.domain.errors import ServiceConflictError, ServiceForbiddenError
from backend.domains.service.fgcn.contracts import (
    BlueprintSnapshot,
    GateServiceScope,
    ServiceCase,
    ServiceTask,
    TaskStatus,
)
from backend.domains.service.fgcn.persistence import (
    FGCNBase,
    ServiceCaseRow,
    SqlAlchemyFGCNRepository,
    TaskAssignmentRow,
)
from backend.domains.service.fgcn.workflow_worker import consume_accepted_human_task
from backend.intelligence.human_gate import (
    ActionProposal,
    ActorType,
    DecisionOutcome,
    GateScope,
    HumanGateBase,
    SqlAlchemyHumanGate,
)
from backend.intelligence.human_gate.persistence import HumanTaskRow
from backend.platform.audit import AuditBase, AuditRecorder, read_all_events
from tests.domains.service.fgcn.admission_test_doubles import (
    AsyncProviderAdmissionStub,
    admitted_snapshot,
)

NOW = datetime(2026, 8, 30, 9, tzinfo=UTC)
TENANT = "00000000-0000-4000-8000-000000000001"
FAMILY = "00000000-0000-4000-8000-000000000002"
CHILD = "00000000-0000-4000-8000-000000000003"
CASE = "00000000-0000-4000-8000-000000000006"
TASK = "00000000-0000-4000-8000-000000000007"
ASSIGNMENT = "00000000-0000-4000-8000-000000000008"
_ADMITTED_PROVIDER = AsyncProviderAdmissionStub(
    admitted_snapshot(capability_keys=("family_guidance",))
)


def _service_scope() -> GateServiceScope:
    return GateServiceScope(
        tenant_id=TENANT,
        family_id=FAMILY,
        subject_person_id=CHILD,
        purpose="service_collaboration",
        consent_version="consent.v1",
        correlation_id="corr-worker-1",
    )


def _gate_scope() -> GateScope:
    return GateScope(
        tenant_id=TENANT,
        family_id=FAMILY,
        subject_ids=(CHILD,),
        purpose="service_collaboration",
        consent_version="consent.v1",
        correlation_id="corr-worker-1",
    )


def _blueprint() -> BlueprintSnapshot:
    return BlueprintSnapshot(
        blueprint_ref="communication-21day-service-collab",
        version=1,
        status="PUBLISHED",
        policy_ref="shadow-policy.v1",
        policy_version=1,
        checksum="checksum-v1",
        task_template_keys=("AI_GUIDANCE_DELIVERY",),
    )


def _case() -> ServiceCase:
    return ServiceCase(
        case_id=CASE,
        scope=_service_scope(),
        intent_ref="00000000-0000-4000-8000-000000000004",
        plan_ref="00000000-0000-4000-8000-000000000005",
        owner_id="steward-1",
        blueprint=_blueprint(),
        opened_at=NOW,
    )


def _task() -> ServiceTask:
    return ServiceTask(
        task_id=TASK,
        case_id=CASE,
        blueprint_ref=_blueprint().blueprint_ref,
        blueprint_version=1,
        task_key="AI_GUIDANCE_DELIVERY",
        title="Guidance delivery",
        description="Deliver the configured guidance activity.",
        role_key="DELIVERY_RESOURCE",
        acceptance_criteria=("Evidence reference is present",),
        required_capability_keys=("family_guidance",),
        task_weight=Decimal("1"),
        status=TaskStatus.PENDING,
        created_at=NOW,
    )


def _proposal(
    *,
    outcome_action: str = "CONFIRM_SERVICE_TASK_ASSIGNMENT",
    proposal_id: str = "proposal:worker-1",
) -> ActionProposal:
    return ActionProposal(
        proposal_id=proposal_id,
        draft_id="draft:worker-1",
        draft_status="DRAFT",
        action_name=outcome_action,
        action_arguments={
            "service_task_id": TASK,
            "provider_id": "expert-1",
            "assignee_kind": "EXPERT",
            "assignment_id": ASSIGNMENT,
        },
        scope=_gate_scope(),
        allowed_actor_types=(ActorType.GUARDIAN,),
        risk_level="HIGH",
        provenance_ref="model-draft:worker-1",
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
        await connection.run_sync(FGCNBase.metadata.create_all)
        await connection.run_sync(HumanGateBase.metadata.create_all)
        await connection.run_sync(AuditBase.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _seed_accepted_task(
    session_factory,
    *,
    human_task_id: str = "human-task:worker-1",
    proposal_id: str = "proposal:worker-1",
):
    recorder = AuditRecorder()
    async with session_factory() as session:
        fgcn = SqlAlchemyFGCNRepository(session)
        gate = SqlAlchemyHumanGate(session)
        await fgcn.save_case(_case())
        await fgcn.save_task(_task())
        task = await gate.submit(
            _proposal(proposal_id=proposal_id), recorder=recorder, task_id=human_task_id
        )
        _, request = await gate.decide(
            task.task_id,
            actor_id="guardian-1",
            actor_type=ActorType.GUARDIAN,
            outcome=DecisionOutcome.ACCEPT,
            recorder=recorder,
            now=NOW + timedelta(hours=1),
        )
        assert request is not None
        await gate.flush_audit(recorder)
        await session.commit()
    return task.task_id


@pytest.mark.asyncio
async def test_worker_consumes_after_restart_and_replay_is_safe(session_factory):
    task_id = await _seed_accepted_task(session_factory)

    async with session_factory() as session:
        assignment = await consume_accepted_human_task(
            SqlAlchemyHumanGate(session),
            SqlAlchemyFGCNRepository(session),
            task_id,
            recorder=AuditRecorder(),
            claim_owner="worker-a",
            provider_admission=_ADMITTED_PROVIDER,
            lease_ttl=timedelta(hours=4),
            claimed_at=NOW + timedelta(hours=2),
            completed_at=NOW + timedelta(hours=2),
            accepted_at=NOW + timedelta(hours=2),
        )

    # A fresh session represents a restarted worker.  The durable request id
    # makes this a replay, not a second assignment.
    async with session_factory() as session:
        replay = await consume_accepted_human_task(
            SqlAlchemyHumanGate(session),
            SqlAlchemyFGCNRepository(session),
            task_id,
            recorder=AuditRecorder(),
            claim_owner="worker-b",
            provider_admission=_ADMITTED_PROVIDER,
            lease_ttl=timedelta(hours=4),
            claimed_at=NOW + timedelta(hours=3),
            completed_at=NOW + timedelta(hours=3),
            accepted_at=NOW + timedelta(hours=3),
        )
        events = await read_all_events(session, tenant_id=TENANT)
        rows = (await session.execute(TaskAssignmentRow.__table__.select())).all()

    assert replay == assignment
    assert len(rows) == 1
    assert [event.action for event in events] == [
        "CREATE_HUMAN_TASK",
        "DECIDE_HUMAN_TASK",
        "CLAIM_HUMAN_TASK",
        "CONFIRM_SERVICE_TASK_ASSIGNMENT",
        "ACCEPT_SERVICE_TASK",
        "ASSIGN_SERVICE_CASE",
        "COMPLETE_HUMAN_TASK_CLAIM",
        "CLAIM_HUMAN_TASK",
        "COMPLETE_HUMAN_TASK_CLAIM",
    ]


@pytest.mark.asyncio
async def test_worker_refuses_rejected_task_and_rechecks_case_scope(session_factory):
    # A rejection is durable but has no executable Named Action.
    recorder = AuditRecorder()
    async with session_factory() as session:
        fgcn = SqlAlchemyFGCNRepository(session)
        gate = SqlAlchemyHumanGate(session)
        await fgcn.save_case(_case())
        await fgcn.save_task(_task())
        task = await gate.submit(_proposal(), recorder=recorder, task_id="human-task:reject-1")
        await gate.decide(
            task.task_id,
            actor_id="guardian-1",
            actor_type=ActorType.GUARDIAN,
            outcome=DecisionOutcome.REJECT,
            reason="provider is not available",
            recorder=recorder,
            now=NOW + timedelta(hours=1),
        )
        await gate.flush_audit(recorder)
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(ServiceConflictError, match="fgcn_human_task_has_no_accepted_action"):
            await consume_accepted_human_task(
                SqlAlchemyHumanGate(session),
                SqlAlchemyFGCNRepository(session),
                "human-task:reject-1",
                recorder=AuditRecorder(),
                claim_owner="worker-a",
                provider_admission=_ADMITTED_PROVIDER,
            )
        assert (
            await SqlAlchemyFGCNRepository(session).load_task(TASK)
        ).status is TaskStatus.PENDING

    # Change the persisted case scope after the gate decision.  The worker must
    # let the FGCN command reject the stale request before any assignment write.
    task_id = await _seed_accepted_task(
        session_factory,
        human_task_id="human-task:scope-1",
        proposal_id="proposal:scope-1",
    )
    async with session_factory() as session:
        row = await session.get(ServiceCaseRow, CASE)
        assert row is not None
        row.correlation_id = "corr-tampered"
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(ServiceForbiddenError, match="fgcn_correlation_scope_violation"):
            await consume_accepted_human_task(
                SqlAlchemyHumanGate(session),
                SqlAlchemyFGCNRepository(session),
                task_id,
                recorder=AuditRecorder(),
                claim_owner="worker-a",
                provider_admission=_ADMITTED_PROVIDER,
            )
        assert (await session.execute(TaskAssignmentRow.__table__.select())).all() == []


@pytest.mark.asyncio
async def test_worker_audit_failure_rolls_back_domain_command(session_factory):
    task_id = await _seed_accepted_task(session_factory)

    class FailingRecorder(AuditRecorder):
        def __init__(self):
            super().__init__()
            self.flush_calls = 0

        async def flush(self, session):
            self.flush_calls += 1
            if self.flush_calls == 2:
                raise RuntimeError("audit store unavailable")
            return await super().flush(session)

    async with session_factory() as session:
        with pytest.raises(RuntimeError, match="audit store unavailable"):
            await consume_accepted_human_task(
                SqlAlchemyHumanGate(session),
                SqlAlchemyFGCNRepository(session),
                task_id,
                recorder=FailingRecorder(),
                claim_owner="worker-a",
                provider_admission=_ADMITTED_PROVIDER,
                lease_ttl=timedelta(hours=4),
                claimed_at=NOW + timedelta(hours=2),
            )
        await session.rollback()

    async with session_factory() as session:
        fgcn = SqlAlchemyFGCNRepository(session)
        assert (await fgcn.load_task(TASK)).status is TaskStatus.PENDING
        assert (await session.execute(TaskAssignmentRow.__table__.select())).all() == []
        human_task = await session.get(HumanTaskRow, task_id)
        assert human_task is not None
        assert human_task.claim_owner == "worker-a"
        events = await read_all_events(session, tenant_id=TENANT)
        assert [event.action for event in events] == [
            "CREATE_HUMAN_TASK",
            "DECIDE_HUMAN_TASK",
            "CLAIM_HUMAN_TASK",
        ]
