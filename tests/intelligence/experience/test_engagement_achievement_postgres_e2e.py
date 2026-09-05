"""Real-PostgreSQL proof for the governed engagement achievement loop."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.apps.family_api.accepted_action_wiring import FGCNAcceptedActionRuntime
from backend.apps.family_api.production_engagement_wiring import (
    ProductionEngagementRuntimeResolver,
)
from backend.intelligence.experience.achievement_persistence import (
    SqlAlchemyAchievementProjection,
)
from backend.intelligence.experience.engagement_api import (
    get_engagement_draft_runtime_resolver,
    router,
)
from backend.intelligence.experience.engagement_review import EngagementReviewer
from backend.intelligence.experience.persistence import SqlAlchemyExperienceOutbox
from backend.intelligence.experience.pipeline import ExperienceOutboxMessage
from backend.intelligence.experience.projections import (
    SqlAlchemyAchievementNotificationProjection,
    SqlAlchemyExperienceAnalyticsProjection,
)
from backend.intelligence.human_gate import ActorType
from backend.intelligence.model_gateway.attempt_persistence import SqlAlchemyAttemptSink
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import ProviderRecord, ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.intelligence.observability import SqlAlchemyTelemetrySink
from backend.intelligence.safety.persistence import SqlAlchemySafetyDecisionSink
from backend.intelligence.safety.runtime import SafetyRuntime
from tests.intelligence.experience.test_engagement import _output
from tests.intelligence.experience.test_gateway import _event
from tests.support.postgres import SKIP_REASON, postgres_test_url


@pytest_asyncio.fixture
async def migrated_database_url() -> str:
    admin_url = postgres_test_url()
    if admin_url is None:
        pytest.skip(SKIP_REASON)
    database_name = f"engagement_e2e_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{database_name}"'))
        database_url = (
            make_url(admin_url)
            .set(database=database_name)
            .render_as_string(hide_password=False)
        )
        environment = os.environ.copy()
        environment["DATABASE_URL"] = database_url
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=os.fspath(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))),
            env=environment,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        yield database_url
    finally:
        async with admin.connect() as connection:
            await connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        await admin.dispose()


@pytest.mark.asyncio
async def test_http_draft_to_guardian_acceptance_to_notification_on_postgres(
    migrated_database_url: str,
) -> None:
    engine = create_async_engine(migrated_database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    event = _event(event_id=f"pg-engagement-{uuid.uuid4().hex}")
    provider_id = "fake-postgres-engagement"
    provider = FakeProvider(
        {"family-engagement-draft": _output(evidence_refs=[event.event_id])},
        provider_id=provider_id,
    )
    gateway = ModelGateway(
        {provider_id: provider},
        environment="staging",
        registry=ProviderRegistry(
            (
                ProviderRecord(
                    provider_id=provider_id,
                    vendor="postgres-contract-test",
                    model="fake-engagement",
                    model_version="1.0.0",
                    status="INTERNAL_APPROVED",
                    approved_environments=("staging",),
                    sub_delegates=False,
                    security_assessment_ref="in-process-test",
                    processing_agreement_ref="in-process-test",
                    deletion_on_termination_committed=True,
                ),
            )
        ),
        safety_runtime=SafetyRuntime(),
    )
    resolver = ProductionEngagementRuntimeResolver(
        scope_resolver=lambda family_id: event.scope,
        session_factory=session_factory,
        gateway=gateway,
        provider_id=provider_id,
        environment="staging",
        authorization_ref_resolver=lambda scope: "guardian-consent:postgres-e2e",
        actor_id_resolver=lambda scope: "guardian:postgres-e2e",
        context_snapshot_ref_resolver=lambda scope: "context:postgres-e2e",
        attempt_sink_factory=SqlAlchemyAttemptSink,
        safety_sink_factory=SqlAlchemySafetyDecisionSink,
        telemetry_sink_factory=SqlAlchemyTelemetrySink,
        reviewer_resolver=lambda scope: EngagementReviewer(
            actor_id="guardian:postgres-e2e",
            actor_type=ActorType.GUARDIAN,
        ),
    )
    try:
        async with session_factory() as session, session.begin():
            await SqlAlchemyExperienceOutbox(session).append(
                ExperienceOutboxMessage(
                    message_id=f"outbox:{event.event_id}",
                    event_type=f"experience.{event.event_type.value}",
                    record=event,
                    scope=event.scope,
                )
            )
        application = FastAPI()
        application.include_router(router)
        application.dependency_overrides[get_engagement_draft_runtime_resolver] = (
            lambda: resolver
        )
        async with AsyncClient(
            transport=ASGITransport(app=application),
            base_url="http://test",
        ) as client:
            generated = await client.post(
                f"/families/{event.scope.family_id}/experience/engagement/drafts",
                json={"request_id": f"request:{event.event_id}", "event_ids": [event.event_id]},
            )
            assert generated.status_code == 200, generated.text
            draft_id = generated.json()["draft_id"]
            submitted = await client.post(
                f"/families/{event.scope.family_id}/experience/engagement/drafts/"
                f"{draft_id}/achievement-candidates/achievement-1/human-task",
                headers={"Idempotency-Key": f"submit:{event.event_id}"},
                json={},
            )
            assert submitted.status_code == 201, submitted.text
            decided = await client.post(
                f"/families/{event.scope.family_id}/experience/engagement/human-tasks/"
                f"{submitted.json()['task_id']}/decisions",
                headers={"Idempotency-Key": f"decision:{event.event_id}"},
                json={"outcome": "ACCEPT"},
            )
            assert decided.status_code == 200, decided.text
            assert decided.json()["decision_outcome"] == "ACCEPT"

        report = await FGCNAcceptedActionRuntime(
            session_factory=session_factory,
            claim_owner="worker:postgres-engagement-e2e",
        ).run_until_idle(limit=10, max_polls=2)
        assert report.succeeded == 1
        async with session_factory() as session:
            achievements = await SqlAlchemyAchievementProjection(session).earned(event.scope)
            notifications = await SqlAlchemyAchievementNotificationProjection(session).unread(
                event.scope
            )
            analytics = await SqlAlchemyExperienceAnalyticsProjection(session).counts(
                event.scope
            )
        assert len(achievements) == 1
        assert achievements[0].evidence_refs == (f"experience-event:{event.event_id}",)
        assert tuple(item.achievement_id for item in notifications) == (
            achievements[0].achievement_id,
        )
        assert analytics == (("achievement:ai_evidence_moment", 1),)
    finally:
        await engine.dispose()
