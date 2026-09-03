from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.apps.family_api.accepted_action_wiring import (
    FGCNAcceptedActionRuntime,
    SqlAlchemyAcceptedActionQueue,
)
from backend.domains.service.fgcn.admission import DEFAULT_ASYNC_PROVIDER_ADMISSION
from backend.intelligence.experience.accepted_achievement import build_achievement_action_proposal
from backend.intelligence.experience.achievement import AchievementKey
from backend.intelligence.experience.achievement_persistence import SqlAlchemyAchievementProjection
from backend.intelligence.experience.engagement import EngagementDraftService
from backend.intelligence.experience.engagement_review import (
    AchievementCandidateSubmissionService,
    SqlAlchemyEngagementDraftReviewStore,
)
from backend.intelligence.experience.persistence import (
    ExperiencePersistenceBase,
    SqlAlchemyExperienceOutbox,
)
from backend.intelligence.experience.pipeline import ExperienceOutboxMessage
from backend.intelligence.experience.projections import (
    SqlAlchemyAchievementNotificationProjection,
    SqlAlchemyExperienceAnalyticsProjection,
)
from backend.intelligence.human_gate import (
    ActionProposal,
    ActorType,
    DecisionOutcome,
    GateScope,
    HumanGateBase,
    SqlAlchemyHumanGate,
)
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.intelligence.tool_runtime.accepted_delivery import (
    AcceptedActionDeliveryBase,
    AcceptedActionDeliveryStatus,
    SqlAlchemyAcceptedActionDeliveryStore,
)
from backend.intelligence.tool_runtime.accepted_dispatch import ActionExecutionReceipt
from backend.platform.audit import AuditBase, AuditRecorder
from tests.intelligence.experience.test_engagement import _command, _output
from tests.intelligence.experience.test_gateway import _event
from tests.intelligence.model_gateway.test_fail_closed import build

NOW = datetime(2026, 8, 30, 9, tzinfo=UTC)


def _proposal(proposal_id: str) -> ActionProposal:
    return ActionProposal(
        proposal_id=proposal_id,
        draft_id=f"draft-{proposal_id}",
        draft_status="DRAFT",
        action_name="CONFIRM_SERVICE_TASK_ASSIGNMENT",
        action_arguments={"service_task_id": f"task-{proposal_id}"},
        scope=GateScope(
            tenant_id="tenant-runtime",
            family_id="family-runtime",
            subject_ids=("child-runtime",),
            purpose="service_collaboration",
            consent_version="consent.v1",
            correlation_id=f"corr-{proposal_id}",
        ),
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
        await connection.run_sync(AcceptedActionDeliveryBase.metadata.create_all)
        await connection.run_sync(ExperiencePersistenceBase.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_queue_filters_completed_delivery(session_factory) -> None:
    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        task = await gate.submit(_proposal("proposal-runtime"), recorder=AuditRecorder())
        _, request = await gate.decide(
            task.task_id,
            actor_id="guardian-runtime",
            actor_type=ActorType.GUARDIAN,
            outcome=DecisionOutcome.ACCEPT,
            recorder=AuditRecorder(),
            now=NOW + timedelta(minutes=1),
        )
        assert request is not None
        delivery = SqlAlchemyAcceptedActionDeliveryStore(session)
        await delivery.begin_attempt(request, now=NOW + timedelta(minutes=2))
        await delivery.mark_succeeded(
            request,
            ActionExecutionReceipt(
                request_id=request.request_id,
                action_name=request.action_name,
                result_ref="assignment:runtime",
            ),
            now=NOW + timedelta(minutes=2),
        )
        await session.commit()

    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        delivery = SqlAlchemyAcceptedActionDeliveryStore(session)
        queue = SqlAlchemyAcceptedActionQueue(gate, delivery)
        assert await queue.pending_accepted_task_ids(limit=10) == ()


def test_runtime_rejects_non_worker_claim_owner(session_factory) -> None:
    with pytest.raises(ValueError, match="claim_owner"):
        FGCNAcceptedActionRuntime(session_factory=session_factory, claim_owner="AI")


def test_runtime_requires_positive_attempts(session_factory) -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        FGCNAcceptedActionRuntime(
            session_factory=session_factory,
            claim_owner="worker:runtime",
            max_attempts=0,
        )


def test_delivery_status_is_explicitly_terminal() -> None:
    assert AcceptedActionDeliveryStatus.SUCCEEDED.value == "SUCCEEDED"
    assert AcceptedActionDeliveryStatus.DEAD_LETTERED.value == "DEAD_LETTERED"


def test_runtime_accepts_provider_admission_query_object(session_factory) -> None:
    runtime = FGCNAcceptedActionRuntime(
        session_factory=session_factory,
        claim_owner="worker:runtime",
        provider_admission=DEFAULT_ASYNC_PROVIDER_ADMISSION,
    )
    assert runtime.claim_owner == "worker:runtime"


def test_runtime_rejects_incomplete_growth_plan_journey_port(session_factory) -> None:
    class IncompleteJourney:
        async def create(self, *args):
            return {}

    with pytest.raises(TypeError, match="journey application is incomplete"):
        FGCNAcceptedActionRuntime(
            session_factory=session_factory,
            claim_owner="worker:runtime",
            growth_plan_scope_resolver=lambda request: None,
            journey_application=IncompleteJourney(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_runtime_composes_empty_bounded_poll(session_factory) -> None:
    runtime = FGCNAcceptedActionRuntime(
        session_factory=session_factory,
        claim_owner="worker:runtime",
    )
    report = await runtime.run_until_idle(limit=10, max_polls=2)
    assert report.pulled == 0
    assert len(report.passes) == 1


@pytest.mark.asyncio
async def test_runtime_delivers_accepted_ai_achievement(session_factory) -> None:
    event = _event(event_id="runtime-achievement")
    draft = await EngagementDraftService(
        build(FakeProvider({"family-engagement-draft": _output(evidence_refs=[event.event_id])}))
    ).generate_draft(_command(events=(event,)))
    proposal = build_achievement_action_proposal(
        draft,
        candidate_id="achievement-1",
        scope=event.scope,
        draft_id="draft:runtime-achievement",
        proposal_id="proposal:runtime-achievement",
    )
    async with session_factory() as session:
        await SqlAlchemyEngagementDraftReviewStore(session).save(
            draft,
            draft_id="draft:runtime-achievement",
        )
        await SqlAlchemyExperienceOutbox(session).append(
            ExperienceOutboxMessage(
                message_id="outbox:runtime-achievement",
                event_type=f"experience.{event.event_type.value}",
                record=event,
                scope=event.scope,
            )
        )
        gate = SqlAlchemyHumanGate(session)
        task = await gate.submit(proposal, recorder=AuditRecorder())
        _, request = await gate.decide(
            task.task_id,
            actor_id="guardian-runtime",
            actor_type=ActorType.GUARDIAN,
            outcome=DecisionOutcome.ACCEPT,
            recorder=AuditRecorder(),
        )
        assert request is not None
        await session.commit()

    runtime = FGCNAcceptedActionRuntime(
        session_factory=session_factory,
        claim_owner="worker:runtime",
    )
    report = await runtime.run_until_idle(limit=10, max_polls=2)
    assert report.succeeded == 1
    async with session_factory() as session:
        earned = await SqlAlchemyAchievementProjection(session).earned(event.scope)
        assert tuple(item.key for item in earned) == (AchievementKey.AI_EVIDENCE_MOMENT,)
        notifications = await SqlAlchemyAchievementNotificationProjection(session).unread(
            event.scope
        )
        assert tuple(item.achievement_id for item in notifications) == (
            earned[0].achievement_id,
        )
        counts = await SqlAlchemyExperienceAnalyticsProjection(session).counts(event.scope)
        assert counts == (("achievement:ai_evidence_moment", 1),)


@pytest.mark.asyncio
async def test_persisted_draft_human_gate_worker_notification_closed_loop(
    session_factory,
) -> None:
    event = _event(event_id="closed-loop-achievement")
    draft = await EngagementDraftService(
        build(FakeProvider({"family-engagement-draft": _output(evidence_refs=[event.event_id])}))
    ).generate_draft(_command(events=(event,)))

    class _Reader:
        async def read(self, *, scope, event_ids):
            return (event,) if scope == event.scope and event_ids == (event.event_id,) else ()

    recorder = AuditRecorder()
    async with session_factory() as session:
        store = SqlAlchemyEngagementDraftReviewStore(session)
        stored = await store.save(draft, created_at=NOW)
        await SqlAlchemyExperienceOutbox(session).append(
            ExperienceOutboxMessage(
                message_id="outbox:closed-loop-achievement",
                event_type=f"experience.{event.event_type.value}",
                record=event,
                scope=event.scope,
            )
        )
        gate = SqlAlchemyHumanGate(session)
        task = await AchievementCandidateSubmissionService(
            store,
            _Reader(),
            gate,
            recorder,
        ).submit(
            draft_id=stored.draft_id,
            candidate_id="achievement-1",
            scope=event.scope,
            actor_id="guardian-closed-loop",
            approval_ref="consent:closed-loop",
            idempotency_key="submit:closed-loop",
            now=NOW + timedelta(minutes=1),
        )
        decided, request = await gate.decide(
            task.task_id,
            actor_id="guardian-closed-loop",
            actor_type=ActorType.GUARDIAN,
            outcome=DecisionOutcome.ACCEPT,
            decision_id="decision:closed-loop",
            recorder=recorder,
            now=NOW + timedelta(minutes=2),
        )
        assert decided.action_request == request
        assert request is not None
        await recorder.flush(session)
        await session.commit()

    report = await FGCNAcceptedActionRuntime(
        session_factory=session_factory,
        claim_owner="worker:closed-loop",
    ).run_until_idle(limit=10, max_polls=2)
    assert report.succeeded == 1

    async with session_factory() as session:
        earned = await SqlAlchemyAchievementProjection(session).earned(event.scope)
        notifications = await SqlAlchemyAchievementNotificationProjection(session).unread(
            event.scope
        )
        analytics = await SqlAlchemyExperienceAnalyticsProjection(session).counts(
            event.scope
        )
    assert len(earned) == 1
    assert earned[0].evidence_refs == ("experience-event:closed-loop-achievement",)
    assert tuple(item.achievement_id for item in notifications) == (
        earned[0].achievement_id,
    )
    assert analytics == (("achievement:ai_evidence_moment", 1),)
