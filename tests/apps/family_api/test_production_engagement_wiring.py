from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.apps.family_api.production_engagement_wiring import (
    ProductionEngagementRuntimeResolver,
    install_sql_engagement_runtime_wiring,
)
from backend.intelligence.experience.achievement_persistence import (
    SqlAlchemyAchievementProjection,
)
from backend.intelligence.experience.contracts import ExperienceEventType
from backend.intelligence.experience.engagement_api import router as engagement_router
from backend.intelligence.experience.engagement_review import (
    EngagementReviewer,
    SqlAlchemyEngagementDraftReviewStore,
)
from backend.intelligence.experience.persistence import (
    ExperiencePersistenceBase,
    SqlAlchemyExperienceOutbox,
)
from backend.intelligence.experience.pipeline import ExperienceOutboxMessage
from backend.intelligence.human_gate import (
    ActorType,
    GateStatus,
    HumanGateBase,
    SqlAlchemyHumanGate,
)
from backend.intelligence.model_gateway.attempt_persistence import (
    AttemptPersistenceBase,
    SqlAlchemyAttemptSink,
)
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import ProviderRecord, ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.intelligence.observability import SqlAlchemyTelemetrySink, TelemetryPersistenceBase
from backend.intelligence.safety.persistence import (
    SafetyDecisionPersistenceBase,
    SqlAlchemySafetyDecisionSink,
)
from backend.intelligence.safety.runtime import SafetyRuntime
from backend.platform.audit import AuditBase, read_all_events
from tests.intelligence.experience.test_engagement import _output
from tests.intelligence.experience.test_gateway import _event


class _VerifyingContextBroker:
    durability_mode = "DURABLE"

    def __init__(self) -> None:
        self.reads: list[tuple[str, object]] = []

    async def read(self, snapshot_ref, scope, *, now=None):  # type: ignore[no-untyped-def]
        self.reads.append((snapshot_ref, scope))
        return None


@pytest.fixture
async def production_engagement_runtime():
    provider_id = "fake-production-engagement"
    provider = FakeProvider(
        {"family-engagement-draft": _output(evidence_refs=["engagement-event"])},
        provider_id=provider_id,
    )
    record = ProviderRecord(
        provider_id=provider_id,
        vendor="internal-contract-test",
        model="fake-engagement",
        model_version="1.0.0",
        status="INTERNAL_APPROVED",
        approved_environments=("staging",),
        sub_delegates=False,
        security_assessment_ref="in-process",
        processing_agreement_ref="in-process",
        deletion_on_termination_committed=True,
    )
    gateway = ModelGateway(
        {provider_id: provider},
        environment="staging",
        registry=ProviderRegistry((record,)),
        safety_runtime=SafetyRuntime(),
    )
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(ExperiencePersistenceBase.metadata.create_all)
        await connection.run_sync(AttemptPersistenceBase.metadata.create_all)
        await connection.run_sync(SafetyDecisionPersistenceBase.metadata.create_all)
        await connection.run_sync(TelemetryPersistenceBase.metadata.create_all)
        await connection.run_sync(HumanGateBase.metadata.create_all)
        await connection.run_sync(AuditBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    event = _event(event_id="engagement-event", event_type=ExperienceEventType.ACTION_COMPLETED)
    async with session_factory() as session, session.begin():
        await SqlAlchemyExperienceOutbox(session).append(
            ExperienceOutboxMessage(
                message_id="outbox:engagement-event",
                event_type=f"experience.{event.event_type.value}",
                record=event,
                scope=event.scope,
            )
        )
    resolver = ProductionEngagementRuntimeResolver(
        scope_resolver=lambda family_id: event.scope,
        session_factory=session_factory,
        gateway=gateway,
        provider_id=provider_id,
        environment="staging",
        authorization_ref_resolver=lambda scope: "auth:engagement",
        actor_id_resolver=lambda scope: "guardian-a",
        context_snapshot_ref_resolver=lambda scope: "context:engagement",
        attempt_sink_factory=SqlAlchemyAttemptSink,
        safety_sink_factory=SqlAlchemySafetyDecisionSink,
        telemetry_sink_factory=SqlAlchemyTelemetrySink,
        reviewer_resolver=lambda scope: EngagementReviewer(
            actor_id="guardian-a",
            actor_type=ActorType.GUARDIAN,
        ),
    )
    try:
        yield resolver, event, provider
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_production_engagement_runtime_reads_outbox_and_persists_gateway_evidence(
    production_engagement_runtime,
) -> None:
    resolver, event, provider = production_engagement_runtime
    runtime = await resolver.resolve(event.scope.family_id)
    draft = await runtime.generate_draft(
        request_id="engagement-production-1",
        event_ids=(event.event_id,),
    )

    assert draft.draft.status == "DRAFT"
    assert draft.draft_id is not None
    assert draft.evidence_event_ids == (event.event_id,)
    assert len(provider.invocations) == 1
    async with resolver.session_factory() as session:
        attempts = await SqlAlchemyAttemptSink(session).list_attempts(
            request_id="engagement-production-1"
        )
        decisions = await SqlAlchemySafetyDecisionSink(session).list_decisions(
            request_id="engagement-production-1"
        )
        spans = await SqlAlchemyTelemetrySink(session).list_spans(
            trace_id="engagement-production-1"
        )
        stored = await SqlAlchemyEngagementDraftReviewStore(session).resolve(
            draft.draft_id,
            scope=event.scope,
        )
    assert len(attempts) == 1
    assert [item.stage for item in decisions] == ["input", "output"]
    assert len(spans) == 1
    assert stored.draft.evidence_event_ids == (event.event_id,)


@pytest.mark.asyncio
async def test_production_engagement_runtime_verifies_context_snapshot_scope(
    production_engagement_runtime,
) -> None:
    resolver, event, provider = production_engagement_runtime
    context = _VerifyingContextBroker()
    runtime = await replace(resolver, context_broker=context).resolve(event.scope.family_id)

    draft = await runtime.generate_draft(
        request_id="engagement-context-verify",
        event_ids=(event.event_id,),
    )

    assert draft.draft.status == "DRAFT"
    assert len(provider.invocations) == 1
    assert len(context.reads) == 1
    snapshot_ref, scope = context.reads[0]
    assert snapshot_ref == "context:engagement"
    assert scope.tenant_id == event.scope.tenant_id
    assert scope.family_id == event.scope.family_id
    assert scope.subject_ids == event.scope.subject_ids
    assert scope.purpose == event.scope.purpose
    assert scope.consent_version == event.scope.consent_version


@pytest.mark.asyncio
async def test_production_runtime_opens_audited_human_task_from_persisted_candidate(
    production_engagement_runtime,
) -> None:
    resolver, event, _ = production_engagement_runtime
    runtime = await resolver.resolve(event.scope.family_id)
    draft = await runtime.generate_draft(
        request_id="engagement-human-review-1",
        event_ids=(event.event_id,),
    )
    assert draft.draft_id is not None

    task = await runtime.submit_achievement_candidate(
        draft_id=draft.draft_id,
        candidate_id="achievement-1",
        idempotency_key="engagement-human-review-submit-1",
    )

    assert task.status is GateStatus.OPEN
    assert task.proposal.draft_id == draft.draft_id
    async with resolver.session_factory() as session:
        persisted = await SqlAlchemyHumanGate(session).get(task.task_id)
        audit = await read_all_events(session, tenant_id=event.scope.tenant_id)
    assert persisted == task
    assert any(
        item.action == "READ_ENGAGEMENT_DRAFT_EVIDENCE_FOR_REVIEW" for item in audit
    )
    assert any(item.action == "CREATE_HUMAN_TASK" for item in audit)

    decided = await runtime.decide_achievement_task(
        task_id=task.task_id,
        outcome="ACCEPT",
        reason=None,
        idempotency_key="engagement-human-review-decision-1",
    )
    assert decided.status is GateStatus.DECIDED
    assert decided.action_request is not None
    async with resolver.session_factory() as session:
        assert await SqlAlchemyAchievementProjection(session).earned(event.scope) == ()


@pytest.mark.asyncio
async def test_production_engagement_runtime_rejects_synthetic_scope(
    production_engagement_runtime,
) -> None:
    resolver, event, _ = production_engagement_runtime
    synthetic = event.scope.__class__(
        global_id=event.scope.global_id,
        tenant_id=event.scope.tenant_id,
        region_id=event.scope.region_id,
        family_id=event.scope.family_id,
        subject_ids=event.scope.subject_ids,
        purpose=event.scope.purpose,
        consent_version=event.scope.consent_version,
        consent_granted=True,
        data_class="SYNTHETIC",  # type: ignore[arg-type]
        locale=event.scope.locale,
        content_locale=event.scope.content_locale,
        model_locale=event.scope.model_locale,
        policy_locale=event.scope.policy_locale,
        deletion_ref=event.scope.deletion_ref,
        correlation_id=event.scope.correlation_id,
        causation_id=event.scope.causation_id,
    )
    blocked = resolver.__class__(
        scope_resolver=lambda family_id: synthetic,
        session_factory=resolver.session_factory,
        gateway=resolver.gateway,
        provider_id=resolver.provider_id,
        environment=resolver.environment,
        authorization_ref_resolver=resolver.authorization_ref_resolver,
        actor_id_resolver=resolver.actor_id_resolver,
        context_snapshot_ref_resolver=resolver.context_snapshot_ref_resolver,
        attempt_sink_factory=resolver.attempt_sink_factory,
        safety_sink_factory=resolver.safety_sink_factory,
        telemetry_sink_factory=resolver.telemetry_sink_factory,
    )
    with pytest.raises(ValueError, match="cannot be synthetic"):
        await blocked.resolve(event.scope.family_id)


@pytest.mark.asyncio
async def test_sql_engagement_wiring_binds_request_auth_and_fails_closed_without_token(
    production_engagement_runtime,
) -> None:
    resolver, _, _ = production_engagement_runtime
    app = FastAPI()
    app.include_router(engagement_router)
    engine = resolver.session_factory.kw["bind"]
    install_sql_engagement_runtime_wiring(
        app,
        engine=engine,
        session_factory=resolver.session_factory,
        gateway=resolver.gateway,
        provider_id=resolver.provider_id,
        environment=resolver.environment,
        authorization_ref_resolver=resolver.authorization_ref_resolver,
        actor_id_resolver=resolver.actor_id_resolver,
        context_snapshot_ref_resolver=resolver.context_snapshot_ref_resolver,
        attempt_sink_factory=resolver.attempt_sink_factory,
        safety_sink_factory=resolver.safety_sink_factory,
        telemetry_sink_factory=resolver.telemetry_sink_factory,
    )

    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/families/family-1/experience/engagement/drafts",
            json={"request_id": "request-auth-1", "event_ids": ["event-1"]},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "engagement_scope_denied"
