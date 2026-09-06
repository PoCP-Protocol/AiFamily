"""Tests for durable FGCN quality and contribution application commands."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.domains.service.domain.errors import (
    ServiceConflictError,
    ServiceForbiddenError,
    ServiceNotFoundError,
)
from backend.domains.service.fgcn.contracts import (
    BlueprintSnapshot,
    CaseStatus,
    GateServiceScope,
    ServiceCase,
    ServiceTask,
    TaskQualityState,
    TaskStatus,
    rework_task_id_for,
)
from backend.domains.service.fgcn.delivery_application import submit_service_delivery
from backend.domains.service.fgcn.persistence import (
    FGCNBase,
    ServiceTaskRow,
    SqlAlchemyFGCNRepository,
)
from backend.domains.service.fgcn.quality_contribution_application import (
    record_service_contribution,
    verify_service_delivery,
)
from backend.domains.service.fgcn.scenario import (
    S01_OUTCOME_OBSERVATION,
    S01_QUALITY_VERIFICATION_MARKER,
    S01_REWORK_QUALITY_MARKER,
    S01_SCENARIO,
    S01_TASK_ACCEPTANCE_CRITERION,
)
from backend.platform.audit import AuditBase, AuditRecorder, read_all_events

NOW = datetime(2026, 8, 30, 16, tzinfo=UTC)
TENANT = "00000000-0000-4000-8000-000000000301"
FAMILY = "00000000-0000-4000-8000-000000000302"
CHILD = "00000000-0000-4000-8000-000000000303"
CASE = "00000000-0000-4000-8000-000000000304"
TASK = "00000000-0000-4000-8000-000000000305"
REVIEW_QUALITY_1 = "00000000-0000-4000-8000-000000000308"
REVIEW_QUALITY_2 = "00000000-0000-4000-8000-000000000309"
REVIEW_REPLAY = "00000000-0000-4000-8000-000000000310"
REVIEW_SELF = "00000000-0000-4000-8000-000000000311"
REVIEW_REWORK = "00000000-0000-4000-8000-000000000312"
REVIEW_AI = "00000000-0000-4000-8000-000000000313"
REVIEW_BEFORE_CONTRIBUTION = "00000000-0000-4000-8000-000000000314"
CONTRIBUTION_QUALITY = "00000000-0000-4000-8000-000000000315"
CONTRIBUTION_BEFORE_REVIEW = "00000000-0000-4000-8000-000000000316"
CONTRIBUTION_WRONG_PROVIDER = "00000000-0000-4000-8000-000000000317"
CONTRIBUTION_AI = "00000000-0000-4000-8000-000000000318"
CONTRIBUTION_REPLAY = "00000000-0000-4000-8000-000000000319"
CONTRIBUTION_AUDIT_FAILURE = "00000000-0000-4000-8000-000000000320"


def _scope(*, family_id: str = FAMILY) -> GateServiceScope:
    return GateServiceScope(
        tenant_id=TENANT,
        family_id=family_id,
        subject_person_id=CHILD,
        purpose="service_collaboration",
        consent_version="consent.v1",
        correlation_id="corr-quality-contribution",
    )


def _case(*, status: CaseStatus = CaseStatus.OPEN) -> ServiceCase:
    return ServiceCase(
        case_id=CASE,
        scope=_scope(),
        intent_ref="00000000-0000-4000-8000-000000000306",
        plan_ref="00000000-0000-4000-8000-000000000307",
        owner_id="steward-quality",
        blueprint=BlueprintSnapshot(
            blueprint_ref="blueprint-quality-contribution",
            version=1,
            status="PUBLISHED",
            policy_ref="shadow-policy.v1",
            policy_version=1,
            checksum="quality-contribution-checksum-v1",
            task_template_keys=("QUALITY_DELIVERY",),
            scenario=S01_SCENARIO,
        ),
        status=status,
        opened_at=NOW,
        closed_at=NOW + timedelta(hours=4) if status is CaseStatus.COMPLETED else None,
    )


def _task(*, status: TaskStatus = TaskStatus.ACCEPTED) -> ServiceTask:
    return ServiceTask(
        task_id=TASK,
        case_id=CASE,
        blueprint_ref="blueprint-quality-contribution",
        blueprint_version=1,
        task_key="QUALITY_DELIVERY",
        title="Quality delivery",
        description="Deliver one quality-controlled service action.",
        role_key="DELIVERY_RESOURCE",
        acceptance_criteria=(S01_TASK_ACCEPTANCE_CRITERION,),
        task_weight=Decimal("1"),
        status=status,
        responsible_ref="expert-quality" if status is not TaskStatus.PENDING else None,
        deliverable_ref=(
            "evidence:quality-1" if status in {TaskStatus.DELIVERED, TaskStatus.VERIFIED} else None
        ),
        verified_at=NOW + timedelta(hours=2) if status is TaskStatus.VERIFIED else None,
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


async def _seed_accepted(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        await repo.save_case(_case())
        await repo.save_task(_task())
        await session.commit()


async def _seed_delivered(factory: async_sessionmaker[AsyncSession]) -> None:
    await _seed_accepted(factory)
    async with factory() as session:
        await submit_service_delivery(
            SqlAlchemyFGCNRepository(session),
            task_id=TASK,
            delivery_id="delivery-quality-1",
            evidence_ref="evidence:quality-1",
            outcome_observation=S01_OUTCOME_OBSERVATION,
            actor_id="expert-quality",
            scope=_scope(),
            recorder=AuditRecorder(),
            delivered_at=NOW + timedelta(hours=1),
        )


async def _seed_verified(factory: async_sessionmaker[AsyncSession]) -> None:
    await _seed_delivered(factory)
    async with factory() as session:
        await verify_service_delivery(
            SqlAlchemyFGCNRepository(session),
            task_id=TASK,
            quality_review_id=REVIEW_QUALITY_1,
            reviewer_ref="reviewer-quality",
            review_note=S01_QUALITY_VERIFICATION_MARKER,
            scope=_scope(),
            recorder=AuditRecorder(),
            reviewed_at=NOW + timedelta(hours=2),
        )


@pytest.mark.asyncio
async def test_quality_and_contribution_commands_persist_the_fact_chain(session_factory):
    await _seed_delivered(session_factory)
    async with session_factory() as session:
        contribution = None
        await verify_service_delivery(
            SqlAlchemyFGCNRepository(session),
            task_id=TASK,
            quality_review_id=REVIEW_QUALITY_2,
            reviewer_ref="reviewer-quality",
            review_note=S01_QUALITY_VERIFICATION_MARKER,
            scope=_scope(),
            recorder=AuditRecorder(),
            reviewed_at=NOW + timedelta(hours=2),
        )
        contribution = await record_service_contribution(
            SqlAlchemyFGCNRepository(session),
            task_id=TASK,
            contribution_id=CONTRIBUTION_QUALITY,
            delivery_id="delivery-quality-1",
            provider_ref="expert-quality",
            role_key="DELIVERY_RESOURCE",
            started_at=NOW,
            completed_at=NOW + timedelta(hours=1),
            scope=_scope(),
            recorder=AuditRecorder(),
        )

    async with session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        loaded_review = await repo.load_quality_review(REVIEW_QUALITY_2)
        loaded_contribution = await repo.load_contribution(CONTRIBUTION_QUALITY)
        loaded_task = await repo.load_task(TASK)
        events = await read_all_events(session, tenant_id=TENANT)

    assert contribution == loaded_contribution
    assert loaded_review.quality_state is TaskQualityState.PASSED
    assert loaded_task.status is TaskStatus.VERIFIED
    assert loaded_contribution.delivery_id == "delivery-quality-1"
    assert [event.action for event in events] == [
        "SUBMIT_SERVICE_DELIVERY",
        "DELIVER_SERVICE_TASK",
        "PROGRESS_SERVICE_CASE",
        "VERIFY_SERVICE_DELIVERY",
        "VERIFY_SERVICE_TASK",
        "RECORD_SERVICE_CONTRIBUTION",
    ]


@pytest.mark.asyncio
async def test_quality_replay_is_idempotent_and_conflicting_review_is_rejected(session_factory):
    await _seed_delivered(session_factory)
    async with session_factory() as session:
        first = await verify_service_delivery(
            SqlAlchemyFGCNRepository(session),
            task_id=TASK,
            quality_review_id=REVIEW_REPLAY,
            reviewer_ref="reviewer-quality",
            review_note=S01_QUALITY_VERIFICATION_MARKER,
            scope=_scope(),
            recorder=AuditRecorder(),
            reviewed_at=NOW + timedelta(hours=2),
        )

    async with session_factory() as session:
        replay = await verify_service_delivery(
            SqlAlchemyFGCNRepository(session),
            task_id=TASK,
            quality_review_id=REVIEW_REPLAY,
            reviewer_ref="reviewer-quality",
            review_note=S01_QUALITY_VERIFICATION_MARKER,
            scope=_scope(),
            recorder=AuditRecorder(),
            reviewed_at=NOW + timedelta(hours=8),
        )
        events = await read_all_events(session, tenant_id=TENANT)
    assert replay == first
    assert len(events) == 5

    async with session_factory() as session:
        with pytest.raises(
            ServiceConflictError, match="fgcn_quality_review_idempotency_replay_mismatch"
        ):
            await verify_service_delivery(
                SqlAlchemyFGCNRepository(session),
                task_id=TASK,
                quality_review_id=REVIEW_REPLAY,
                reviewer_ref="reviewer-quality",
                review_note="changed after approval",
                scope=_scope(),
                recorder=AuditRecorder(),
            )


@pytest.mark.asyncio
async def test_quality_rejects_self_review_non_pass_and_ai_reviewer(session_factory):
    await _seed_delivered(session_factory)
    async with session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        with pytest.raises(
            ServiceForbiddenError,
            match="fgcn_quality_reviewer_must_differ_from_delivery_person",
        ):
            await verify_service_delivery(
                repo,
                task_id=TASK,
                quality_review_id=REVIEW_SELF,
                reviewer_ref="expert-quality",
                review_note="self review",
                scope=_scope(),
                recorder=AuditRecorder(),
            )
        review = await verify_service_delivery(
            repo,
            task_id=TASK,
            quality_review_id=REVIEW_REWORK,
            reviewer_ref="reviewer-quality",
            review_note=S01_REWORK_QUALITY_MARKER,
            quality_state=TaskQualityState.REWORK_REQUIRED,
            scope=_scope(),
            recorder=AuditRecorder(),
            reviewed_at=NOW + timedelta(hours=2),
        )
        rework_task = await repo.load_task(rework_task_id_for(TASK, REVIEW_REWORK))
        assert review.quality_state is TaskQualityState.REWORK_REQUIRED
        assert (await repo.load_task(TASK)).status is TaskStatus.REWORK_REQUESTED
        assert rework_task.status is TaskStatus.PENDING
        assert rework_task.responsible_ref is None
        assert rework_task.rework_of_task_id == TASK
        assert rework_task.rework_attempt == 1
        with pytest.raises(ServiceConflictError, match="fgcn_contribution_requires_verified_task"):
            await record_service_contribution(
                repo,
                task_id=TASK,
                contribution_id=CONTRIBUTION_BEFORE_REVIEW,
                delivery_id="delivery-quality-1",
                provider_ref="expert-quality",
                role_key="DELIVERY_RESOURCE",
                started_at=NOW,
                completed_at=NOW + timedelta(hours=1),
                scope=_scope(),
                recorder=AuditRecorder(),
            )
        with pytest.raises(ServiceForbiddenError, match="fgcn_requires_human_actor"):
            await verify_service_delivery(
                repo,
                task_id=TASK,
                quality_review_id=REVIEW_AI,
                reviewer_ref="AI:reviewer",
                review_note="automated approval",
                scope=_scope(),
                recorder=AuditRecorder(),
            )
        assert (await repo.load_task(TASK)).status is TaskStatus.REWORK_REQUESTED
        events = await read_all_events(session, tenant_id=TENANT)
        assert [event.action for event in events] == [
            "SUBMIT_SERVICE_DELIVERY",
            "DELIVER_SERVICE_TASK",
            "PROGRESS_SERVICE_CASE",
            "REQUEST_SERVICE_REWORK",
            "CREATE_SERVICE_REWORK_TASK",
        ]


@pytest.mark.asyncio
async def test_rework_quality_replay_across_sessions_has_one_follow_up_and_no_new_audit(
    session_factory,
):
    await _seed_delivered(session_factory)
    async with session_factory() as session:
        first = await verify_service_delivery(
            SqlAlchemyFGCNRepository(session),
            task_id=TASK,
            quality_review_id=REVIEW_REWORK,
            reviewer_ref="reviewer-quality",
            review_note=S01_REWORK_QUALITY_MARKER,
            quality_state=TaskQualityState.REWORK_REQUIRED,
            scope=_scope(),
            recorder=AuditRecorder(),
            reviewed_at=NOW + timedelta(hours=2),
        )

    async with session_factory() as session:
        replay = await verify_service_delivery(
            SqlAlchemyFGCNRepository(session),
            task_id=TASK,
            quality_review_id=REVIEW_REWORK,
            reviewer_ref="reviewer-quality",
            review_note=S01_REWORK_QUALITY_MARKER,
            quality_state=TaskQualityState.REWORK_REQUIRED,
            scope=_scope(),
            recorder=AuditRecorder(),
            reviewed_at=NOW + timedelta(hours=8),
        )
        follow_up_rows = (
            (
                await session.execute(
                    sa.select(ServiceTaskRow).where(ServiceTaskRow.rework_of_task_id == TASK)
                )
            )
            .scalars()
            .all()
        )
        events = await read_all_events(session, tenant_id=TENANT)

    assert replay == first
    assert len(follow_up_rows) == 1
    assert follow_up_rows[0].task_id == rework_task_id_for(TASK, REVIEW_REWORK)
    assert [event.action for event in events].count("REQUEST_SERVICE_REWORK") == 1
    assert [event.action for event in events].count("CREATE_SERVICE_REWORK_TASK") == 1


@pytest.mark.asyncio
async def test_rework_quality_and_follow_up_roll_back_together_when_audit_fails(session_factory):
    await _seed_delivered(session_factory)

    class FailingAuditRecorder(AuditRecorder):
        async def flush(self, session):
            raise RuntimeError("audit store unavailable")

    async with session_factory() as session:
        with pytest.raises(RuntimeError, match="audit store unavailable"):
            await verify_service_delivery(
                SqlAlchemyFGCNRepository(session),
                task_id=TASK,
                quality_review_id=REVIEW_REWORK,
                reviewer_ref="reviewer-quality",
                review_note=S01_REWORK_QUALITY_MARKER,
                quality_state=TaskQualityState.REWORK_REQUIRED,
                scope=_scope(),
                recorder=FailingAuditRecorder(),
                reviewed_at=NOW + timedelta(hours=2),
            )
        await session.rollback()

    async with session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        assert (await repo.load_task(TASK)).status is TaskStatus.DELIVERED
        with pytest.raises(ServiceNotFoundError):
            await repo.load_quality_review(REVIEW_REWORK)
        with pytest.raises(ServiceNotFoundError):
            await repo.load_task(rework_task_id_for(TASK, REVIEW_REWORK))
        events = await read_all_events(session, tenant_id=TENANT)
        assert [event.action for event in events] == [
            "SUBMIT_SERVICE_DELIVERY",
            "DELIVER_SERVICE_TASK",
            "PROGRESS_SERVICE_CASE",
        ]


@pytest.mark.asyncio
async def test_contribution_requires_verified_delivery_and_matching_human_provider(session_factory):
    await _seed_delivered(session_factory)
    async with session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        with pytest.raises(ServiceConflictError, match="fgcn_contribution_requires_verified_task"):
            await record_service_contribution(
                repo,
                task_id=TASK,
                contribution_id=CONTRIBUTION_BEFORE_REVIEW,
                delivery_id="delivery-quality-1",
                provider_ref="expert-quality",
                role_key="DELIVERY_RESOURCE",
                started_at=NOW,
                completed_at=NOW + timedelta(hours=1),
                scope=_scope(),
                recorder=AuditRecorder(),
            )

    async with session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        await verify_service_delivery(
            repo,
            task_id=TASK,
            quality_review_id=REVIEW_BEFORE_CONTRIBUTION,
            reviewer_ref="reviewer-quality",
            review_note=S01_QUALITY_VERIFICATION_MARKER,
            scope=_scope(),
            recorder=AuditRecorder(),
            reviewed_at=NOW + timedelta(hours=2),
        )
        with pytest.raises(ServiceForbiddenError, match="fgcn_contribution_provider_mismatch"):
            await record_service_contribution(
                repo,
                task_id=TASK,
                contribution_id=CONTRIBUTION_WRONG_PROVIDER,
                delivery_id="delivery-quality-1",
                provider_ref="expert-other",
                role_key="DELIVERY_RESOURCE",
                started_at=NOW,
                completed_at=NOW + timedelta(hours=1),
                scope=_scope(),
                recorder=AuditRecorder(),
            )
        with pytest.raises(ServiceForbiddenError, match="fgcn_contribution_role_mismatch"):
            await record_service_contribution(
                repo,
                task_id=TASK,
                contribution_id="00000000-0000-4000-8000-000000000321",
                delivery_id="delivery-quality-1",
                provider_ref="expert-quality",
                role_key="UNBOUND_ROLE",
                started_at=NOW,
                completed_at=NOW + timedelta(hours=1),
                scope=_scope(),
                recorder=AuditRecorder(),
            )
        with pytest.raises(ServiceForbiddenError, match="fgcn_requires_human_actor"):
            await record_service_contribution(
                repo,
                task_id=TASK,
                contribution_id=CONTRIBUTION_AI,
                delivery_id="delivery-quality-1",
                provider_ref="AI:provider",
                role_key="DELIVERY_RESOURCE",
                started_at=NOW,
                completed_at=NOW + timedelta(hours=1),
                scope=_scope(),
                recorder=AuditRecorder(),
            )


@pytest.mark.asyncio
async def test_contribution_replay_and_changed_payload_are_fail_closed(session_factory):
    await _seed_verified(session_factory)
    async with session_factory() as session:
        first = await record_service_contribution(
            SqlAlchemyFGCNRepository(session),
            task_id=TASK,
            contribution_id=CONTRIBUTION_REPLAY,
            delivery_id="delivery-quality-1",
            provider_ref="expert-quality",
            role_key="DELIVERY_RESOURCE",
            started_at=NOW,
            completed_at=NOW + timedelta(hours=1),
            scope=_scope(),
            recorder=AuditRecorder(),
        )

    async with session_factory() as session:
        replay = await record_service_contribution(
            SqlAlchemyFGCNRepository(session),
            task_id=TASK,
            contribution_id=CONTRIBUTION_REPLAY,
            delivery_id="delivery-quality-1",
            provider_ref="expert-quality",
            role_key="DELIVERY_RESOURCE",
            started_at=NOW,
            completed_at=NOW + timedelta(hours=1),
            scope=_scope(),
            recorder=AuditRecorder(),
        )
        events = await read_all_events(session, tenant_id=TENANT)
    assert replay == first
    assert len(events) == 6

    async with session_factory() as session:
        with pytest.raises(
            ServiceConflictError, match="fgcn_contribution_idempotency_replay_mismatch"
        ):
            await record_service_contribution(
                SqlAlchemyFGCNRepository(session),
                task_id=TASK,
                contribution_id=CONTRIBUTION_REPLAY,
                delivery_id="delivery-quality-1",
                provider_ref="expert-quality",
                role_key="DELIVERY_RESOURCE",
                started_at=NOW,
                completed_at=NOW + timedelta(hours=2),
                scope=_scope(),
                recorder=AuditRecorder(),
            )


@pytest.mark.asyncio
async def test_contribution_audit_failure_rolls_back_the_fact(session_factory):
    await _seed_verified(session_factory)

    class _FailingAuditRecorder(AuditRecorder):
        async def flush(self, session):
            raise RuntimeError("audit store unavailable")

    async with session_factory() as session:
        with pytest.raises(RuntimeError, match="audit store unavailable"):
            await record_service_contribution(
                SqlAlchemyFGCNRepository(session),
                task_id=TASK,
                contribution_id=CONTRIBUTION_AUDIT_FAILURE,
                delivery_id="delivery-quality-1",
                provider_ref="expert-quality",
                role_key="DELIVERY_RESOURCE",
                started_at=NOW,
                completed_at=NOW + timedelta(hours=1),
                scope=_scope(),
                recorder=_FailingAuditRecorder(),
            )
        await session.rollback()

    async with session_factory() as session:
        repo = SqlAlchemyFGCNRepository(session)
        with pytest.raises(ServiceNotFoundError, match="fgcn_contribution_not_found"):
            await repo.load_contribution(CONTRIBUTION_AUDIT_FAILURE)
        events = await read_all_events(session, tenant_id=TENANT)
        assert [event.action for event in events] == [
            "SUBMIT_SERVICE_DELIVERY",
            "DELIVER_SERVICE_TASK",
            "PROGRESS_SERVICE_CASE",
            "VERIFY_SERVICE_DELIVERY",
            "VERIFY_SERVICE_TASK",
        ]
