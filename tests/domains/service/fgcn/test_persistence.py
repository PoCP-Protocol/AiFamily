from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.domains.service.domain.errors import (
    ServiceConflictError,
    ServiceForbiddenError,
    ServiceNotFoundError,
    ServiceValidationError,
)
from backend.domains.service.fgcn.contracts import (
    AllocationBucket,
    AllocationLine,
    AllocationReleaseState,
    AllocationStatement,
    BlueprintSnapshot,
    CaseStatus,
    ContributionQualityState,
    GateServiceScope,
    ServiceCase,
    ServiceContribution,
    ServiceDelivery,
    ServiceTask,
    TaskAssignment,
    TaskAssignmentStatus,
    TaskQualityReview,
    TaskQualityState,
    TaskStatus,
)
from backend.domains.service.fgcn.persistence import (
    AllocationLineRow,
    FGCNBase,
    ServiceCaseRow,
    ServiceContributionRow,
    SqlAlchemyFGCNRepository,
)
from backend.platform.audit import AuditBase, AuditEvent, AuditRecorder, read_all_events
from backend.platform.persistence.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.postgres import SKIP_REASON, postgres_test_url

NOW = datetime(2026, 8, 30, 9, tzinfo=UTC)
TENANT = "00000000-0000-4000-8000-000000000001"
FAMILY = "00000000-0000-4000-8000-000000000002"
CHILD = "00000000-0000-4000-8000-000000000003"
INTENT = "00000000-0000-4000-8000-000000000004"
PLAN = "00000000-0000-4000-8000-000000000005"
CASE = "00000000-0000-4000-8000-000000000006"
TASK = "00000000-0000-4000-8000-000000000007"
ASSIGNMENT = "00000000-0000-4000-8000-000000000008"
CONTRIBUTION = "00000000-0000-4000-8000-000000000009"
ALLOCATION_RUN = "00000000-0000-4000-8000-000000000010"


def _scope() -> GateServiceScope:
    return GateServiceScope(
        tenant_id=TENANT,
        family_id=FAMILY,
        subject_person_id=CHILD,
        purpose="service_collaboration",
        consent_version="consent.v1",
        correlation_id="corr-persistence-1",
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


def _case(*, status: CaseStatus = CaseStatus.OPEN) -> ServiceCase:
    return ServiceCase(
        case_id=CASE,
        scope=_scope(),
        intent_ref=INTENT,
        plan_ref=PLAN,
        owner_id="steward-1",
        blueprint=_blueprint(),
        status=status,
        opened_at=NOW,
        closed_at=NOW + timedelta(hours=3) if status is CaseStatus.COMPLETED else None,
    )


def _task(*, status: TaskStatus = TaskStatus.VERIFIED) -> ServiceTask:
    is_verified = status is TaskStatus.VERIFIED
    has_delivery = status in {TaskStatus.DELIVERED, TaskStatus.VERIFIED}
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
        task_weight=Decimal("1"),
        status=status,
        responsible_ref="expert-1" if status is not TaskStatus.PENDING else None,
        deliverable_ref="evidence:delivery-1" if has_delivery else None,
        verified_at=NOW + timedelta(hours=2) if is_verified else None,
        created_at=NOW,
    )


def _assignment() -> TaskAssignment:
    return TaskAssignment(
        assignment_id=ASSIGNMENT,
        case_id=CASE,
        task_id=TASK,
        assignee_ref="expert-1",
        assignee_kind="EXPERT",
        status=TaskAssignmentStatus.ACCEPTED,
        accepted_by_actor_id="guardian-1",
        source_request_id="named-action-request:1",
        accepted_at=NOW + timedelta(minutes=1),
    )


def _delivery() -> ServiceDelivery:
    return ServiceDelivery(
        delivery_id="delivery-1",
        case_id=CASE,
        task_id=TASK,
        assignee_ref="expert-1",
        evidence_ref="evidence:delivery-1",
        delivered_at=NOW + timedelta(hours=1),
    )


def _review() -> TaskQualityReview:
    return TaskQualityReview(
        quality_review_id="00000000-0000-4000-8000-000000000011",
        case_id=CASE,
        task_id=TASK,
        reviewer_ref="quality-1",
        quality_state=TaskQualityState.PASSED,
        review_note="criteria passed",
        reviewed_at=NOW + timedelta(hours=2),
    )


def _contribution() -> ServiceContribution:
    return ServiceContribution(
        contribution_id=CONTRIBUTION,
        case_id=CASE,
        task_id=TASK,
        provider_ref="expert-1",
        role_key="DELIVERY_RESOURCE",
        delivery_id="delivery-1",
        quality_state=ContributionQualityState.VERIFIED,
        started_at=NOW,
        completed_at=NOW + timedelta(hours=1),
    )


def _statement() -> AllocationStatement:
    policy_ref = _blueprint().policy_ref
    common = {
        "allocation_run_id": ALLOCATION_RUN,
        "case_id": CASE,
        "policy_ref": policy_ref,
        "policy_version": 1,
    }
    lines = (
        AllocationLine(
            allocation_id="00000000-0000-4000-8000-000000000012",
            allocation_bucket=AllocationBucket.PLATFORM,
            units=Decimal("20"),
            beneficiary_ref="platform",
            beneficiary_kind="PLATFORM",
            role_key="PLATFORM",
            basis_type="CASE",
            basis_ref=CASE,
            release_state=AllocationReleaseState.RELEASED,
            **common,
        ),
        AllocationLine(
            allocation_id="00000000-0000-4000-8000-000000000013",
            allocation_bucket=AllocationBucket.CONTENT_RESOURCE,
            units=Decimal("15"),
            beneficiary_ref="content-resource",
            beneficiary_kind="INTERNAL_ACTOR",
            role_key="CONTENT_RESOURCE",
            basis_type="CASE",
            basis_ref=CASE,
            release_state=AllocationReleaseState.RELEASED,
            **common,
        ),
        AllocationLine(
            allocation_id="00000000-0000-4000-8000-000000000014",
            allocation_bucket=AllocationBucket.CASE_STEWARD,
            units=Decimal("15"),
            beneficiary_ref="steward-1",
            beneficiary_kind="INTERNAL_ACTOR",
            role_key="CASE_STEWARD",
            basis_type="CASE",
            basis_ref=CASE,
            release_state=AllocationReleaseState.RELEASED,
            **common,
        ),
        AllocationLine(
            allocation_id="00000000-0000-4000-8000-000000000015",
            allocation_bucket=AllocationBucket.QUALITY_RESERVE,
            units=Decimal("10"),
            beneficiary_ref="quality-reserve",
            beneficiary_kind="PLATFORM",
            role_key="QUALITY_RESERVE",
            basis_type="CASE",
            basis_ref=CASE,
            release_state=AllocationReleaseState.HELD,
            **common,
        ),
        AllocationLine(
            allocation_id="00000000-0000-4000-8000-000000000016",
            allocation_bucket=AllocationBucket.DELIVERY_RESOURCE,
            units=Decimal("40"),
            beneficiary_ref="expert-1",
            beneficiary_kind="ADMITTED_PROVIDER",
            role_key="DELIVERY_RESOURCE",
            basis_type="CONTRIBUTION_WEIGHT",
            basis_ref=CONTRIBUTION,
            release_state=AllocationReleaseState.RELEASED,
            **common,
        ),
    )
    return AllocationStatement(
        allocation_run_id=ALLOCATION_RUN,
        case_id=CASE,
        policy_ref=policy_ref,
        policy_version=1,
        triggered_by_actor_id="operator-1",
        total_units=Decimal("100"),
        lines=lines,
        created_at=NOW + timedelta(hours=4),
    )


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(FGCNBase.metadata.create_all)
        await connection.run_sync(AuditBase.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@asynccontextmanager
async def _postgres_fgcn_engine():
    database_url = postgres_test_url()
    if database_url is None:  # pragma: no cover - guarded by the fixture
        raise RuntimeError(SKIP_REASON)
    schema = f"t_fgcn_{uuid4().hex[:16]}"
    bootstrap = create_async_engine(database_url, connect_args={"statement_cache_size": 0})
    try:
        async with bootstrap.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(
            database_url,
            connect_args={
                "statement_cache_size": 0,
                "server_settings": {"search_path": schema},
            },
        )
        try:
            async with engine.begin() as connection:
                for type_name, values in (
                    (
                        "service_case_status",
                        "'OPEN','ASSIGNED','IN_PROGRESS','WAITING_FAMILY','ESCALATED','COMPLETED','CANCELLED'",
                    ),
                    (
                        "service_task_status",
                        "'PENDING','OFFERED','ACCEPTED','IN_PROGRESS','DELIVERED','VERIFIED','CLOSED','CANCELLED','REWORK_REQUESTED'",
                    ),
                    (
                        "task_assignment_status",
                        "'OFFERED','ACCEPTED','DECLINED','REVOKED','COMPLETED'",
                    ),
                    (
                        "task_quality_state",
                        "'PENDING','PASSED','REWORK_REQUIRED','REJECTED'",
                    ),
                ):
                    await connection.execute(text(f"CREATE TYPE {type_name} AS ENUM ({values})"))
                await connection.run_sync(FGCNBase.metadata.create_all)
            yield engine
        finally:
            await engine.dispose()
    finally:
        async with bootstrap.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await bootstrap.dispose()


@pytest_asyncio.fixture
async def postgres_session_factory():
    if postgres_test_url() is None:
        pytest.skip(SKIP_REASON)
    async with _postgres_fgcn_engine() as engine:
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.mark.asyncio
async def test_fgcn_facts_round_trip_with_audit_in_one_committed_session(session_factory):
    recorder = AuditRecorder()
    recorder.record(
        AuditEvent(
            actor_id="steward-1",
            tenant_id=TENANT,
            action="OPEN_SERVICE_CASE",
            resource_type="ServiceCase",
            resource_id=CASE,
            reason="persisted FGCN case",
            correlation_id="corr-persistence-1",
            after={"status": "OPEN"},
        )
    )
    async with session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        await repo.save_case(_case())
        await repo.save_task(_task(status=TaskStatus.ACCEPTED))
        await repo.save_assignment(_assignment())
        await repo.save_delivery(_delivery())
        await repo.save_task(_task(status=TaskStatus.DELIVERED))
        await repo.save_quality_review(_review())
        await repo.save_contribution(_contribution())
        await repo.save_case(_case(status=CaseStatus.COMPLETED))
        await repo.save_allocation_statement(_statement())
        await repo.save_allocation_statement(_statement())
        assert await recorder.flush(session) == 1
        await session.commit()

    async with session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        loaded_case = await repo.load_case(CASE)
        loaded_task = await repo.load_task(TASK)
        loaded_assignment = await repo.load_assignment(ASSIGNMENT)
        loaded_delivery = await repo.load_delivery(TASK)
        loaded_review = await repo.load_quality_review(_review().quality_review_id)
        loaded_contribution = await repo.load_contribution(CONTRIBUTION)
        loaded_statement = await repo.load_allocation_statement(CASE)
        events = await read_all_events(session, tenant_id=TENANT)

    assert loaded_case.scope == _scope()
    assert loaded_case.blueprint == _blueprint()
    assert loaded_task.acceptance_criteria == ("Evidence reference is present",)
    assert loaded_task.status is TaskStatus.VERIFIED
    assert loaded_assignment == _assignment()
    assert loaded_delivery.evidence_ref == "evidence:delivery-1"
    assert loaded_review == _review()
    assert loaded_contribution == _contribution()
    assert loaded_statement.total_units == Decimal("100.00")
    assert len(loaded_statement.lines) == 5
    assert (
        next(
            line
            for line in loaded_statement.lines
            if line.allocation_bucket is AllocationBucket.QUALITY_RESERVE
        ).release_state
        is AllocationReleaseState.HELD
    )
    assert len(events) == 1


@pytest.mark.asyncio
async def test_domain_and_audit_roll_back_together_when_uow_is_not_committed(session_factory):
    recorder = AuditRecorder()
    recorder.record(
        AuditEvent(
            actor_id="steward-1",
            tenant_id=TENANT,
            action="OPEN_SERVICE_CASE",
            resource_type="ServiceCase",
            resource_id=CASE,
            reason="transaction rollback probe",
            correlation_id="corr-rollback-1",
        )
    )
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.session is not None
        repo = SqlAlchemyFGCNRepository(uow.session)
        await repo.save_case(_case())
        await recorder.flush(uow.session)

    async with session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        with pytest.raises(ServiceNotFoundError, match="fgcn_service_case_not_found"):
            await repo.load_case(CASE)
        assert await read_all_events(session, tenant_id=TENANT) == []


@pytest.mark.asyncio
async def test_case_level_allocation_does_not_fabricate_a_task_basis(session_factory):
    async with session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        await repo.save_case(_case())
        await repo.save_task(_task(status=TaskStatus.ACCEPTED))
        await repo.save_delivery(_delivery())
        await repo.save_quality_review(_review())
        await repo.save_contribution(_contribution())
        await repo.save_case(_case(status=CaseStatus.COMPLETED))
        await repo.save_allocation_statement(_statement())
        await session.commit()
        row = await session.get(AllocationLineRow, "00000000-0000-4000-8000-000000000012")

    assert row is not None
    assert row.task_ref is None
    assert row.contribution_ref is None


@pytest.mark.asyncio
async def test_persistence_refuses_contribution_basis_without_a_durable_contribution(
    session_factory,
):
    statement = _statement()
    async with session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        await repo.save_case(_case(status=CaseStatus.COMPLETED))
        with pytest.raises(ServiceNotFoundError, match="fgcn_allocation_contribution_not_found"):
            await repo.save_allocation_statement(statement)
        await session.rollback()


@pytest.mark.asyncio
async def test_persistence_rejects_legacy_case_without_scope_metadata(session_factory):
    async with session_factory() as session:
        session.add(
            ServiceCaseRow(
                case_id=CASE,
                tenant_id=None,
                family_id=FAMILY,
                subject_person_id=CHILD,
                intent_ref=INTENT,
                plan_ref=PLAN,
                status="OPEN",
                owner="steward-1",
                opened_at=NOW,
                next_action_at=None,
                closed_at=None,
                scope_purpose=None,
                consent_version=None,
                correlation_id=None,
                collaboration_blueprint_ref=None,
                collaboration_blueprint_version=None,
                collaboration_blueprint_snapshot=None,
                shadow_allocation_finalized_at=None,
                shadow_allocation_policy_ref=None,
                shadow_allocation_policy_version=None,
            )
        )
        await session.commit()
        repo = SqlAlchemyFGCNRepository(session)
        with pytest.raises(ServiceValidationError, match="fgcn_case_tenant_required"):
            await repo.load_case(CASE)


@pytest.mark.asyncio
async def test_persistence_rejects_case_reuse_with_changed_scope(session_factory):
    changed_scope = replace(_scope(), purpose="different_declared_purpose")
    changed_case = replace(_case(), scope=changed_scope)
    async with session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        await repo.save_case(_case())
        with pytest.raises(ServiceConflictError, match="fgcn_case_id_reuse_mismatch"):
            await repo.save_case(changed_case)


@pytest.mark.asyncio
async def test_persistence_rejects_conflicting_allocation_replay(session_factory):
    async with session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        await repo.save_case(_case())
        await repo.save_task(_task(status=TaskStatus.ACCEPTED))
        await repo.save_delivery(_delivery())
        await repo.save_quality_review(_review())
        await repo.save_contribution(_contribution())
        await repo.save_case(_case(status=CaseStatus.COMPLETED))
        await repo.save_allocation_statement(_statement())
        await session.commit()

    changed_delivery_line = replace(
        next(
            line
            for line in _statement().lines
            if line.allocation_bucket is AllocationBucket.DELIVERY_RESOURCE
        ),
        beneficiary_ref="another-provider",
    )
    changed_lines = tuple(
        changed_delivery_line
        if line.allocation_bucket is AllocationBucket.DELIVERY_RESOURCE
        else line
        for line in _statement().lines
    )
    changed_statement = replace(_statement(), lines=changed_lines)
    async with session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        with pytest.raises(ServiceForbiddenError, match="fgcn_allocation_contribution_mismatch"):
            await repo.save_allocation_statement(changed_statement)


@pytest.mark.asyncio
async def test_persistence_load_rejects_tampered_allocation_row(session_factory):
    async with session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        await repo.save_case(_case())
        await repo.save_task(_task(status=TaskStatus.ACCEPTED))
        await repo.save_delivery(_delivery())
        await repo.save_quality_review(_review())
        await repo.save_contribution(_contribution())
        await repo.save_case(_case(status=CaseStatus.COMPLETED))
        await repo.save_allocation_statement(_statement())
        await session.commit()

    async with session_factory() as session:
        row = await session.get(AllocationLineRow, "00000000-0000-4000-8000-000000000012")
        assert row is not None
        row.reason = "tampered outside repository"
        await session.commit()

    async with session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        with pytest.raises(ServiceValidationError, match="fgcn_allocation_persisted_row_mismatch"):
            await repo.load_allocation_statement(CASE)


@pytest.mark.asyncio
async def test_persistence_rejects_delivery_after_completed_case(session_factory):
    async with session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        await repo.save_case(_case(status=CaseStatus.COMPLETED))
        await repo.save_task(_task(status=TaskStatus.ACCEPTED))
        with pytest.raises(ServiceConflictError, match="fgcn_delivery_case_is_terminal"):
            await repo.save_delivery(_delivery())
        await session.rollback()


@pytest.mark.asyncio
async def test_persistence_replays_delivery_and_contribution_without_duplicates(session_factory):
    async with session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        await repo.save_case(_case())
        await repo.save_task(_task(status=TaskStatus.ACCEPTED))
        await repo.save_delivery(_delivery())
        await repo.save_delivery(_delivery())
        await repo.save_task(_task(status=TaskStatus.DELIVERED))
        await repo.save_quality_review(_review())
        await repo.save_contribution(_contribution())
        await repo.save_contribution(_contribution())
        contribution_rows = (
            await session.execute(sa.select(ServiceContributionRow))
        ).scalars().all()
        assert len(contribution_rows) == 1


@pytest.mark.asyncio
async def test_persistence_rejects_contribution_without_durable_delivery_payload(session_factory):
    async with session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        await repo.save_case(_case())
        # This fixture has a VERIFIED task and only the legacy evidence_ref.
        # It must not be upgraded into a made-up DeliveryRecord when a
        # contribution is recorded after a process restart.
        await repo.save_task(_task(status=TaskStatus.VERIFIED))
        with pytest.raises(ServiceValidationError, match="fgcn_delivery_persisted_shape_invalid"):
            await repo.save_contribution(_contribution())
        await session.rollback()


@pytest.mark.asyncio
async def test_fgcn_repository_round_trips_on_real_postgres(postgres_session_factory):
    """The production dialect must preserve UUID, enum, JSON and partial-index behavior."""
    async with postgres_session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        await repo.save_case(_case())
        await repo.save_task(_task(status=TaskStatus.ACCEPTED))
        await repo.save_assignment(_assignment())
        await repo.save_delivery(_delivery())
        await repo.save_task(_task(status=TaskStatus.DELIVERED))
        await repo.save_quality_review(_review())
        await repo.save_contribution(_contribution())
        await repo.save_case(_case(status=CaseStatus.COMPLETED))
        await repo.save_allocation_statement(_statement())
        await session.commit()

    async with postgres_session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        assert (await repo.load_assignment(ASSIGNMENT)).assignee_ref == "expert-1"
        assert (await repo.load_contribution(CONTRIBUTION)).delivery_id == "delivery-1"
        assert (await repo.load_allocation_statement(CASE)).total_units == Decimal("100.00")
