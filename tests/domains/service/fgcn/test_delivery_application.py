"""Tests for the durable FGCN assignment -> delivery application command."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.domains.service.domain.errors import (
    ServiceConflictError,
    ServiceForbiddenError,
    ServiceValidationError,
)
from backend.domains.service.fgcn.contracts import (
    BlueprintSnapshot,
    CaseStatus,
    GateServiceScope,
    ServiceCase,
    ServiceTask,
    TaskStatus,
)
from backend.domains.service.fgcn.delivery_application import submit_service_delivery
from backend.domains.service.fgcn.persistence import FGCNBase, SqlAlchemyFGCNRepository
from backend.platform.audit import AuditBase, AuditRecorder, read_all_events

NOW = datetime(2026, 8, 30, 14, tzinfo=UTC)
TENANT = "00000000-0000-4000-8000-000000000201"
FAMILY = "00000000-0000-4000-8000-000000000202"
CHILD = "00000000-0000-4000-8000-000000000203"
CASE = "00000000-0000-4000-8000-000000000204"
TASK = "00000000-0000-4000-8000-000000000205"


def _scope(*, family_id: str = FAMILY) -> GateServiceScope:
    return GateServiceScope(
        tenant_id=TENANT,
        family_id=family_id,
        subject_person_id=CHILD,
        purpose="service_collaboration",
        consent_version="consent.v1",
        correlation_id="corr-delivery-application",
    )


def _case(*, status: CaseStatus = CaseStatus.OPEN) -> ServiceCase:
    return ServiceCase(
        case_id=CASE,
        scope=_scope(),
        intent_ref="00000000-0000-4000-8000-000000000206",
        plan_ref="00000000-0000-4000-8000-000000000207",
        owner_id="steward-delivery",
        blueprint=BlueprintSnapshot(
            blueprint_ref="blueprint-delivery-application",
            version=1,
            status="PUBLISHED",
            policy_ref="shadow-policy.v1",
            policy_version=1,
            checksum="delivery-checksum-v1",
            task_template_keys=("GUIDANCE_DELIVERY",),
        ),
        status=status,
        opened_at=NOW,
        closed_at=NOW + timedelta(hours=3) if status is CaseStatus.COMPLETED else None,
    )


def _task(*, status: TaskStatus = TaskStatus.ACCEPTED) -> ServiceTask:
    return ServiceTask(
        task_id=TASK,
        case_id=CASE,
        blueprint_ref="blueprint-delivery-application",
        blueprint_version=1,
        task_key="GUIDANCE_DELIVERY",
        title="Guidance delivery",
        description="Deliver one approved guidance activity.",
        role_key="DELIVERY_RESOURCE",
        acceptance_criteria=("Evidence reference is present",),
        task_weight=Decimal("1"),
        status=status,
        responsible_ref="expert-delivery" if status is not TaskStatus.PENDING else None,
        created_at=NOW,
    )


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(FGCNBase.metadata.create_all)
        await connection.run_sync(AuditBase.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _seed(factory: async_sessionmaker[AsyncSession], *, task_status: TaskStatus) -> None:
    async with factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        await repo.save_case(_case())
        await repo.save_task(_task(status=task_status))
        await session.commit()


@pytest.mark.asyncio
async def test_delivery_command_persists_state_and_audit_in_one_commit(session_factory):
    await _seed(session_factory, task_status=TaskStatus.ACCEPTED)

    async with session_factory() as session:
        recorder = AuditRecorder()
        delivery = await submit_service_delivery(
            SqlAlchemyFGCNRepository(session),
            task_id=TASK,
            delivery_id="delivery-application-1",
            evidence_ref="evidence:delivery-application-1",
            actor_id="expert-delivery",
            scope=_scope(),
            recorder=recorder,
            delivered_at=NOW + timedelta(hours=1),
        )

    async with session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        loaded_delivery = await repo.load_delivery(TASK)
        loaded_task = await repo.load_task(TASK)
        loaded_case = await repo.load_case(CASE)
        events = await read_all_events(session, tenant_id=TENANT)

    assert delivery == loaded_delivery
    assert loaded_task.status is TaskStatus.DELIVERED
    assert loaded_task.deliverable_ref == "evidence:delivery-application-1"
    assert loaded_case.status is CaseStatus.IN_PROGRESS
    assert [event.action for event in events] == [
        "SUBMIT_SERVICE_DELIVERY",
        "DELIVER_SERVICE_TASK",
        "PROGRESS_SERVICE_CASE",
    ]


@pytest.mark.asyncio
async def test_delivery_replay_is_idempotent_and_ignores_new_server_timestamp(session_factory):
    await _seed(session_factory, task_status=TaskStatus.ACCEPTED)
    first_time = NOW + timedelta(hours=1)

    async with session_factory() as session:
        first = await submit_service_delivery(
            SqlAlchemyFGCNRepository(session),
            task_id=TASK,
            delivery_id="delivery-replay-1",
            evidence_ref="evidence:replay-1",
            actor_id="expert-delivery",
            scope=_scope(),
            recorder=AuditRecorder(),
            delivered_at=first_time,
        )

    async with session_factory() as session:
        replay = await submit_service_delivery(
            SqlAlchemyFGCNRepository(session),
            task_id=TASK,
            delivery_id="delivery-replay-1",
            evidence_ref="evidence:replay-1",
            actor_id="expert-delivery",
            scope=_scope(),
            recorder=AuditRecorder(),
            delivered_at=first_time + timedelta(hours=2),
        )
        events = await read_all_events(session, tenant_id=TENANT)

    assert replay == first
    assert len(events) == 3

    async with session_factory() as session:
        with pytest.raises(
            ServiceConflictError, match="fgcn_delivery_idempotency_replay_mismatch"
        ):
            await submit_service_delivery(
                SqlAlchemyFGCNRepository(session),
                task_id=TASK,
                delivery_id="delivery-replay-1",
                evidence_ref="evidence:changed",
                actor_id="expert-delivery",
                scope=_scope(),
                recorder=AuditRecorder(),
            )


@pytest.mark.asyncio
async def test_delivery_rejects_foreign_scope_and_ai_actor_without_writes(session_factory):
    await _seed(session_factory, task_status=TaskStatus.ACCEPTED)

    async with session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        with pytest.raises(ServiceForbiddenError, match="fgcn_family_scope_violation"):
            await submit_service_delivery(
                repo,
                task_id=TASK,
                delivery_id="delivery-foreign-family",
                evidence_ref="evidence:foreign-family",
                actor_id="expert-delivery",
                scope=_scope(family_id="00000000-0000-4000-8000-000000000299"),
                recorder=AuditRecorder(),
            )
        assert (await repo.load_task(TASK)).status is TaskStatus.ACCEPTED
        with pytest.raises(ServiceForbiddenError, match="fgcn_delivery_requires_human_actor"):
            await submit_service_delivery(
                repo,
                task_id=TASK,
                delivery_id="delivery-ai-actor",
                evidence_ref="evidence:ai-actor",
                actor_id="AI:delivery-agent",
                scope=_scope(),
                recorder=AuditRecorder(),
            )
        with pytest.raises(ServiceForbiddenError, match="fgcn_delivery_actor_mismatch"):
            await submit_service_delivery(
                repo,
                task_id=TASK,
                delivery_id="delivery-other-provider",
                evidence_ref="evidence:other-provider",
                actor_id="expert-other",
                scope=_scope(),
                recorder=AuditRecorder(),
            )
        assert await read_all_events(session, tenant_id=TENANT) == []


@pytest.mark.asyncio
async def test_delivery_rejects_pending_or_terminal_tasks(session_factory):
    await _seed(session_factory, task_status=TaskStatus.PENDING)
    async with session_factory() as session:
        with pytest.raises(
            ServiceConflictError, match="fgcn_delivery_requires_assigned_responsible_person"
        ):
            await submit_service_delivery(
                SqlAlchemyFGCNRepository(session),
                task_id=TASK,
                delivery_id="delivery-pending",
                evidence_ref="evidence:pending",
                actor_id="expert-delivery",
                scope=_scope(),
                recorder=AuditRecorder(),
            )

    await _seed(session_factory, task_status=TaskStatus.ACCEPTED)
    async with session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        await repo.save_case(_case(status=CaseStatus.COMPLETED))
        await session.commit()
    async with session_factory() as session:
        with pytest.raises(ServiceConflictError, match="fgcn_delivery_case_is_terminal"):
            await submit_service_delivery(
                SqlAlchemyFGCNRepository(session),
                task_id=TASK,
                delivery_id="delivery-terminal",
                evidence_ref="evidence:terminal",
                actor_id="expert-delivery",
                scope=_scope(),
                recorder=AuditRecorder(),
            )


@pytest.mark.asyncio
async def test_delivery_does_not_claim_success_when_audit_flush_fails(session_factory):
    await _seed(session_factory, task_status=TaskStatus.ACCEPTED)

    class _FailingAuditRecorder(AuditRecorder):
        async def flush(self, session):
            raise RuntimeError("audit store unavailable")

    async with session_factory() as session:
        with pytest.raises(RuntimeError, match="audit store unavailable"):
            await submit_service_delivery(
                SqlAlchemyFGCNRepository(session),
                task_id=TASK,
                delivery_id="delivery-audit-failure",
                evidence_ref="evidence:audit-failure",
                actor_id="expert-delivery",
                scope=_scope(),
                recorder=_FailingAuditRecorder(),
            )
        await session.rollback()

    async with session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        loaded_task = await repo.load_task(TASK)
        assert loaded_task.status is TaskStatus.ACCEPTED
        assert loaded_task.deliverable_ref is None
        assert await read_all_events(session, tenant_id=TENANT) == []
        with pytest.raises(ServiceValidationError, match="fgcn_delivery_task_state_invalid"):
            await repo.load_delivery(TASK)


@pytest.mark.asyncio
async def test_delivery_accepts_only_the_assigned_actor(session_factory):
    await _seed(session_factory, task_status=TaskStatus.ACCEPTED)
    async with session_factory() as session:
        with pytest.raises(ServiceForbiddenError, match="fgcn_delivery_actor_mismatch"):
            await submit_service_delivery(
                SqlAlchemyFGCNRepository(session),
                task_id=TASK,
                delivery_id="delivery-unauthorized",
                evidence_ref="evidence:unauthorized",
                actor_id="guardian-not-provider",
                scope=_scope(),
                recorder=AuditRecorder(),
            )
