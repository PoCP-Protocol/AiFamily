from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import make_url, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.apps.family_api.main import create_app
from backend.apps.family_api.production_achievement_feedback_write_wiring import (
    install_production_achievement_feedback_write_wiring,
)
from backend.apps.family_api.production_daily_action_http_wiring import (
    install_production_daily_action_http_wiring,
)
from backend.domains.action.application.daily_action import (
    ActionActor,
)
from backend.domains.action.infrastructure.postgres import (
    SqlAlchemyDailyActionApplication,
)
from backend.intelligence.experience.achievement import AchievementKey
from backend.intelligence.experience.achievement_consumer import (
    ExperienceAchievementConsumer,
)
from backend.intelligence.experience.achievement_persistence import (
    SqlAlchemyAchievementProjection,
)
from backend.intelligence.experience.feedback_response import (
    FEEDBACK_RESPONSE_ACTION_NAME,
    ExperienceFeedbackResponseActionHandler,
    SqlAlchemyExperienceFeedbackDeletionService,
)
from backend.intelligence.experience.persistence import SqlAlchemyExperienceOutbox
from backend.intelligence.experience.projections import (
    SqlAlchemyAchievementNotificationProjection,
    SqlAlchemyExperienceAnalyticsProjection,
)
from backend.intelligence.growth_graph.outbox_consumer import (
    GrowthGraphOutboxConsumer,
)
from backend.intelligence.growth_graph.store import SqlAlchemyGrowthGraphProjection
from backend.intelligence.human_gate.contracts import ActorType, DecisionOutcome
from backend.intelligence.human_gate.persistence import SqlAlchemyHumanGate
from backend.intelligence.tool_runtime.accepted_delivery import (
    SqlAlchemyAcceptedActionDeliveryStore,
)
from backend.intelligence.tool_runtime.accepted_dispatch import AcceptedNamedActionDispatcher
from backend.intelligence.tool_runtime.accepted_worker import AcceptedNamedActionWorker
from backend.platform.audit import AuditRecorder
from backend.platform.persistence.session import clear_engine_cache
from backend.workflow_worker.experience_fanout import AtomicExperienceFanoutConsumer
from backend.workflow_worker.growth_action_experience_relay import (
    GrowthActionExperienceRelay,
)
from tests.domains.journey.test_fastapi_postgres_e2e import (
    _seed,
)
from tests.support.postgres import SKIP_REASON, postgres_test_url

NOW = datetime(2026, 9, 3, 9, tzinfo=UTC)


@pytest_asyncio.fixture
async def baselined_database_url() -> AsyncIterator[str]:
    """Create an isolated database at the current Alembic head for this capability."""
    admin_url = postgres_test_url()
    if admin_url is None:
        pytest.skip(SKIP_REASON)
    database_name = f"action_e2e_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(
        admin_url,
        isolation_level="AUTOCOMMIT",
        connect_args={"statement_cache_size": 0},
    )
    try:
        async with admin.connect() as connection:
            await connection.execute(text(f'create database "{database_name}"'))
        database_url = (
            make_url(admin_url)
            .set(database=database_name)
            .render_as_string(hide_password=False)
        )
        migrated = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(Path(__file__).resolve().parents[3]),
            env={**os.environ, "DATABASE_URL": database_url},
            capture_output=True,
            text=True,
            check=False,
        )
        assert migrated.returncode == 0, migrated.stdout + migrated.stderr
        yield database_url
    finally:
        clear_engine_cache()
        async with admin.connect() as connection:
            await connection.execute(
                text(
                    "select pg_terminate_backend(pid) from pg_stat_activity "
                    "where datname=:database and pid<>pg_backend_pid()"
                ),
                {"database": database_name},
            )
            await connection.execute(text(f'drop database if exists "{database_name}"'))
        await admin.dispose()


@pytest.mark.asyncio
async def test_daily_action_sql_lifecycle_is_restart_safe_and_audited(
    baselined_database_url: str,
    monkeypatch,
) -> None:
    ids, token = await _seed(baselined_database_url)
    consent_engine = create_async_engine(
        baselined_database_url,
        connect_args={"statement_cache_size": 0},
    )
    async with consent_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE persons SET birth_date=DATE '2013-05-01' "
                "WHERE person_id=:subject_id"
            ),
            {"subject_id": ids["child"]},
        )
        await connection.execute(
            text("UPDATE tenants SET region_ref='CN' WHERE tenant_id=:tenant_id"),
            {"tenant_id": ids["tenant"]},
        )
    await consent_engine.dispose()
    monkeypatch.setenv("DATABASE_URL", baselined_database_url)
    monkeypatch.setenv("AIFAMILY_ENV", "production")
    clear_engine_cache()
    app = create_app()
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/families/{ids['family']}/growth/onboardings/{ids['onboarding']}"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        priority = await client.get(f"{base}/priority", headers=headers)
        confirmed_priority = await client.post(
            f"{base}/priority/confirm",
            headers={**headers, "Idempotency-Key": "daily-action-priority"},
            json={"draft_id": priority.json()["draft"]["draft_id"], "decision": "R03"},
        )
        priority_id = confirmed_priority.json()["priority"]["priority_id"]
        created = await client.post(
            f"{base}/journey-plan",
            headers={**headers, "Idempotency-Key": "daily-action-plan-create"},
            json={"priority_id": priority_id},
        )
        plan_id = created.json()["plan"]["plan_id"]
        confirmed = await client.post(
            f"/families/{ids['family']}/growth/journey-plans/{plan_id}/confirm",
            headers={**headers, "Idempotency-Key": "daily-action-plan-confirm"},
            json={},
        )
        assert confirmed.json()["plan"]["status"] == "ACTIVE"

    engine = create_async_engine(
        baselined_database_url,
        connect_args={"statement_cache_size": 0},
    )
    actor = ActionActor(actor_id=ids["guardian"], family_id=ids["family"])
    action_app = SqlAlchemyDailyActionApplication(engine, clock=lambda: NOW)
    action = await action_app.initialize_from_ai_plan(
        actor=actor,
        tenant_id=ids["tenant"],
        plan_id=plan_id,
        assignment_text="先听完一句话，再回应。",
        source_draft_id="draft-growth-plan-1",
        source_draft_digest="a" * 64,
        source_provenance_ref="model-draft:draft-growth-plan-1",
        source_consent_version="consent:e2e",
        idempotency_key="daily-action-initialize",
        correlation_id="correlation:daily-action-init",
    )
    replayed_action = await action_app.initialize_from_ai_plan(
        actor=actor,
        tenant_id=ids["tenant"],
        plan_id=plan_id,
        assignment_text="先听完一句话，再回应。",
        source_draft_id="draft-growth-plan-1",
        source_draft_digest="a" * 64,
        source_provenance_ref="model-draft:draft-growth-plan-1",
        source_consent_version="consent:e2e",
        idempotency_key="daily-action-initialize",
        correlation_id="correlation:daily-action-init",
    )
    assert replayed_action.task_id == action.task_id

    daily_app = FastAPI()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    install_production_daily_action_http_wiring(
        daily_app,
        engine=engine,
        session_factory=session_factory,
    )
    install_production_achievement_feedback_write_wiring(
        daily_app,
        engine=engine,
        session_factory=session_factory,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=daily_app),
        base_url="http://test",
    ) as client:
        today_response = await client.get(
            f"/families/{ids['family']}/today",
            headers=headers,
        )
        assert today_response.status_code == 200, today_response.text
        assert today_response.json()["today_task"]["task_state"] == "NOT_STARTED"

        started_response = await client.post(
            f"/families/{ids['family']}/tasks/{action.task_id}/state",
            headers={**headers, "Idempotency-Key": "ui09-start-task-v1-e2e"},
            json={"action": "START", "occurred_at": (NOW + timedelta(minutes=1)).isoformat()},
        )
        assert started_response.status_code == 200, started_response.text
        started = started_response.json()

        stale_response = await client.post(
            f"/families/{ids['family']}/tasks/{action.task_id}/state",
            headers={**headers, "Idempotency-Key": "ui09-pause-task-v1-stale"},
            json={"action": "PAUSE", "occurred_at": (NOW + timedelta(minutes=2)).isoformat()},
        )
        assert stale_response.status_code == 409
        assert "daily_action_version_conflict" in stale_response.json()["detail"]

        paused_response = await client.post(
            f"/families/{ids['family']}/tasks/{action.task_id}/state",
            headers={**headers, "Idempotency-Key": "ui09-pause-task-v2-e2e"},
            json={"action": "PAUSE", "occurred_at": (NOW + timedelta(minutes=2)).isoformat()},
        )
        assert paused_response.status_code == 200, paused_response.text
        paused = paused_response.json()

        resumed_response = await client.post(
            f"/families/{ids['family']}/tasks/{action.task_id}/state",
            headers={**headers, "Idempotency-Key": "ui09-resume-task-v3-e2e"},
            json={"action": "RESUME", "occurred_at": (NOW + timedelta(minutes=3)).isoformat()},
        )
        assert resumed_response.status_code == 200, resumed_response.text
        resumed = resumed_response.json()

        checkin_headers = {
            **headers,
            "Idempotency-Key": "ui09-checkin-task-v4-e2e",
        }
        checkin_body = {
            "completion_status": "COMPLETED",
            "reflection": "我先停下来听完了。",
            "occurred_at": (NOW + timedelta(minutes=4)).isoformat(),
        }
        completed_response = await client.post(
            f"/families/{ids['family']}/tasks/{action.task_id}/check-in",
            headers=checkin_headers,
            json=checkin_body,
        )
        assert completed_response.status_code == 200, completed_response.text
        completed = completed_response.json()
        replay_response = await client.post(
            f"/families/{ids['family']}/tasks/{action.task_id}/check-in",
            headers=checkin_headers,
            json=checkin_body,
        )
        assert replay_response.status_code == 200, replay_response.text
        replay = replay_response.json()

    relay_report = await GrowthActionExperienceRelay(session_factory).run_once()
    relay_replay_report = await GrowthActionExperienceRelay(session_factory).run_once()
    async with session_factory() as session, session.begin():
        experience_outbox = SqlAlchemyExperienceOutbox(session)
        pending_experience = await experience_outbox.pending(limit=10)
        achievement_projection = SqlAlchemyAchievementProjection(session)
        achievement_consumer = ExperienceAchievementConsumer(
            projection=achievement_projection,
            notifications=SqlAlchemyAchievementNotificationProjection(session),
            analytics=SqlAlchemyExperienceAnalyticsProjection(session),
        )
        consumer = AtomicExperienceFanoutConsumer(
            (
                achievement_consumer,
                GrowthGraphOutboxConsumer(SqlAlchemyGrowthGraphProjection(session)),
            )
        )
        for message in pending_experience:
            await consumer.consume(message)
            await experience_outbox.mark_published(message.message_id)

    async with engine.connect() as connection:
        first_step_achievement_id = await connection.scalar(
            text(
                "SELECT achievement_id FROM ai_achievement_projections "
                "WHERE family_id=:family_id AND achievement_key='first_step'"
            ),
            {"family_id": ids["family"]},
        )
    assert isinstance(first_step_achievement_id, str)
    feedback_path = (
        f"/families/{ids['family']}/experience/achievements/"
        f"{first_step_achievement_id}/feedback"
    )
    helpful_body = {
        "signal": "helpful",
        "occurred_at": (NOW + timedelta(minutes=5)).isoformat(),
    }
    human_body = {
        "signal": "request_human",
        "reason_code": "need_professional_guidance",
        "occurred_at": (NOW + timedelta(minutes=6)).isoformat(),
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=daily_app),
        base_url="http://test",
    ) as client:
        helpful_feedback = await client.post(
            feedback_path,
            headers={**headers, "Idempotency-Key": "achievement-helpful-1"},
            json=helpful_body,
        )
        assert helpful_feedback.status_code == 200, helpful_feedback.text
        human_feedback = await client.post(
            feedback_path,
            headers={**headers, "Idempotency-Key": "achievement-human-1"},
            json=human_body,
        )
        assert human_feedback.status_code == 200, human_feedback.text
        human_replay = await client.post(
            feedback_path,
            headers={**headers, "Idempotency-Key": "achievement-human-1"},
            json=human_body,
        )
        assert human_replay.status_code == 200, human_replay.text
        concurrent_body = {
            "signal": "not_helpful",
            "reason_code": "too_generic",
            "occurred_at": (NOW + timedelta(minutes=7)).isoformat(),
        }
        concurrent_feedback = await asyncio.gather(
            client.post(
                feedback_path,
                headers={**headers, "Idempotency-Key": "achievement-concurrent-1"},
                json=concurrent_body,
            ),
            client.post(
                feedback_path,
                headers={**headers, "Idempotency-Key": "achievement-concurrent-1"},
                json=concurrent_body,
            ),
        )
        assert {item.status_code for item in concurrent_feedback} == {200}
        assert {item.json()["result_state"] for item in concurrent_feedback} == {
            "RECORDED",
            "REPLAYED",
        }
        feedback_conflict = await client.post(
            feedback_path,
            headers={**headers, "Idempotency-Key": "achievement-human-1"},
            json={
                "signal": "not_helpful",
                "reason_code": "too_generic",
                "occurred_at": (NOW + timedelta(minutes=6)).isoformat(),
            },
        )
        assert feedback_conflict.status_code == 409

    async def fail_audit_flush(_self, _recorder):
        raise RuntimeError("forced feedback audit failure")

    with monkeypatch.context() as failure_patch:
        failure_patch.setattr(SqlAlchemyHumanGate, "flush_audit", fail_audit_flush)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=daily_app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            atomic_failure = await client.post(
                feedback_path,
                headers={**headers, "Idempotency-Key": "achievement-human-failure"},
                json={
                    **human_body,
                    "occurred_at": (NOW + timedelta(minutes=8)).isoformat(),
                },
            )
    assert atomic_failure.status_code == 500
    with pytest.raises(DBAPIError, match="append-only"):
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE ai_achievement_feedback SET reason_code='tampered' "
                    "WHERE feedback_id=:feedback_id"
                ),
                {"feedback_id": helpful_feedback.json()["feedback_id"]},
            )

    human_task_id = human_feedback.json()["human_task_id"]
    assert isinstance(human_task_id, str)
    async with session_factory() as session:
        gate = SqlAlchemyHumanGate(session)
        decision_audit = AuditRecorder()
        decided, action_request = await gate.decide(
            human_task_id,
            actor_id="operator:family-support-1",
            actor_type=ActorType.OPERATOR,
            outcome=DecisionOutcome.ACCEPT,
            recorder=decision_audit,
            decision_id="decision:feedback-e2e",
        )
        assert action_request is not None
        await gate.flush_audit(decision_audit)
        await gate.commit()
        response_audit = AuditRecorder()
        worker = AcceptedNamedActionWorker(
            gate,
            SqlAlchemyAcceptedActionDeliveryStore(session),
            AcceptedNamedActionDispatcher(
                {
                    FEEDBACK_RESPONSE_ACTION_NAME: ExperienceFeedbackResponseActionHandler(
                        session,
                        recorder=response_audit,
                    )
                }
            ),
        )
        response_delivery = await worker.consume(
            decided.task_id,
            claim_owner="workflow-worker:feedback-e2e",
        )
        assert response_delivery.status.value == "succeeded", response_delivery.error

    restarted = SqlAlchemyDailyActionApplication(engine, clock=lambda: NOW)
    readback = await restarted.get_today(
        actor=actor,
        tenant_id=ids["tenant"],
        subject_person_id=ids["child"],
        consent_version="consent:e2e",
        approval_ref="consent:e2e",
        correlation_id="correlation:daily-action-restart-read",
    )
    async with engine.connect() as connection:
        audit_count = await connection.scalar(
            text(
                "SELECT count(*) FROM audit_logs "
                "WHERE family_id=:family_id AND resource_type='GrowthAction'"
            ),
            {"family_id": ids["family"]},
        )
        events = tuple(
            await connection.scalars(
                text(
                    "SELECT event_name FROM outbox_events "
                    "WHERE aggregate_type='GrowthAction' ORDER BY created_at"
                )
            )
        )
        source_binding = (
            await connection.execute(
                text(
                    "SELECT source_draft_id, source_draft_digest, "
                    "source_provenance_ref, source_consent_version "
                    "FROM growth_actions WHERE action_id=:action_id"
                ),
                {"action_id": action.task_id},
            )
        ).one()
        achievement_keys = tuple(
            await connection.scalars(
                text(
                    "SELECT achievement_key FROM ai_achievement_projections "
                    "WHERE family_id=:family_id ORDER BY earned_at, achievement_key"
                ),
                {"family_id": ids["family"]},
            )
        )
        notification_count = await connection.scalar(
            text(
                "SELECT count(*) FROM ai_achievement_notifications "
                "WHERE family_id=:family_id AND status='UNREAD'"
            ),
            {"family_id": ids["family"]},
        )
        action_started_metric = await connection.scalar(
            text(
                "SELECT value_count FROM ai_experience_analytics "
                "WHERE family_id=:family_id AND metric_key='event:action_started'"
            ),
            {"family_id": ids["family"]},
        )
        action_resumed_metric = await connection.scalar(
            text(
                "SELECT value_count FROM ai_experience_analytics "
                "WHERE family_id=:family_id AND metric_key='event:action_resumed'"
            ),
            {"family_id": ids["family"]},
        )
        growth_graph_edge_count = await connection.scalar(
            text(
                "SELECT count(*) FROM ai_growth_graph_edges "
                "WHERE family_id=:family_id"
            ),
            {"family_id": ids["family"]},
        )
        feedback_rows = tuple(
            await connection.execute(
                text(
                    "SELECT signal, human_task_id FROM ai_achievement_feedback "
                    "WHERE family_id=:family_id ORDER BY occurred_at"
                ),
                {"family_id": ids["family"]},
            )
        )
        feedback_human_task = (
            await connection.execute(
                text(
                    "SELECT status, action_name, purpose, consent_version, "
                    "proposal_payload->>'source_kind' AS source_kind, "
                    "proposal_payload->'scope'->>'region_id' AS region_id, "
                    "proposal_payload->'scope'->>'deletion_ref' AS deletion_ref "
                    "FROM ai_human_tasks WHERE task_id=:task_id"
                ),
                {"task_id": human_feedback.json()["human_task_id"]},
            )
        ).one()
        feedback_audit_count = await connection.scalar(
            text(
                "SELECT count(*) FROM platform_audit_events "
                "WHERE resource_type IN ('FeedbackSignal','HumanTask') "
                "AND correlation_id=:correlation_id"
            ),
            {"correlation_id": "daily-action-request"},
        )
        feedback_read_audit = (
            await connection.execute(
                text(
                    "SELECT action_kind, subject_is_minor, approval_ref, access_purpose "
                    "FROM platform_audit_events "
                    "WHERE action='READ_EXPERIENCE_FEEDBACK_FOR_FOLLOWUP'"
                )
            )
        ).one()
        feedback_resolution = (
            await connection.execute(
                text(
                    "SELECT resolution_code, responder_actor_id, feedback_id "
                    "FROM ai_experience_feedback_resolutions"
                )
            )
        ).one()
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                "UPDATE consents SET status='WITHDRAWN', withdrawn_at=CURRENT_TIMESTAMP "
                "WHERE family_id=:family_id AND subject_person_id=:subject_id "
                "AND purpose='GROWTH_TRACKING'"
            ),
            {"family_id": ids["family"], "subject_id": ids["child"]},
        )
        await session.execute(
            text(
                """
                INSERT INTO outbox_events(
                  aggregate_type, aggregate_id, event_name, event_version,
                  event_id, correlation_id, payload, occurred_at
                )
                SELECT aggregate_type, aggregate_id, event_name, event_version,
                       CAST(:event_id AS uuid), 'correlation:consent-revoked',
                       payload, CURRENT_TIMESTAMP
                FROM outbox_events
                WHERE aggregate_type='GrowthAction' AND event_name='DailyActionStart'
                ORDER BY created_at
                LIMIT 1
                """
            ),
            {"event_id": str(uuid.uuid4())},
        )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=daily_app),
        base_url="http://test",
    ) as client:
        revoked_feedback = await client.post(
            feedback_path,
            headers={**headers, "Idempotency-Key": "achievement-after-withdrawal"},
            json={
                "signal": "helpful",
                "occurred_at": (NOW + timedelta(minutes=9)).isoformat(),
            },
        )
    assert revoked_feedback.status_code == 403
    revoked_report = await GrowthActionExperienceRelay(session_factory).run_once()
    malformed_event_id = str(uuid.uuid4())
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                """
                INSERT INTO outbox_events(
                  aggregate_type, aggregate_id, event_name, event_version,
                  event_id, correlation_id, payload, occurred_at
                ) VALUES (
                  'GrowthAction', :action_id, 'DailyActionStart', 1,
                  CAST(:event_id AS uuid), 'correlation:malformed-relay',
                  '{}'::jsonb, CURRENT_TIMESTAMP
                )
                """
            ),
            {"action_id": action.task_id, "event_id": malformed_event_id},
        )
    malformed_report = await GrowthActionExperienceRelay(session_factory).run_once()
    async with engine.connect() as connection:
        experience_message_count = await connection.scalar(
            text("SELECT count(*) FROM experience_outbox_messages")
        )
        consent_discard_audit_count = await connection.scalar(
            text(
                "SELECT count(*) FROM audit_logs "
                "WHERE action_name='DiscardGrowthActionExperienceEvent'"
            )
        )
        malformed_retry = await connection.execute(
            text(
                "SELECT delivery.attempts, delivery.status, source.published_at "
                "FROM outbox_events AS source "
                "JOIN domain_outbox_consumer_deliveries AS delivery "
                "ON delivery.outbox_id=source.outbox_id "
                "WHERE source.event_id=CAST(:event_id AS uuid)"
            ),
            {"event_id": malformed_event_id},
        )
        (
            malformed_retry_count,
            malformed_delivery_status,
            malformed_published_at,
        ) = malformed_retry.one()
        source_published_count = await connection.scalar(
            text(
                "SELECT count(*) FROM outbox_events "
                "WHERE aggregate_type='GrowthAction' AND published_at IS NOT NULL"
            )
        )
        feedback_count_after_failures = await connection.scalar(
            text(
                "SELECT count(*) FROM ai_achievement_feedback "
                "WHERE family_id=:family_id"
            ),
            {"family_id": ids["family"]},
        )
        feedback_task_count = await connection.scalar(
            text(
                "SELECT count(*) FROM ai_human_tasks "
                "WHERE action_name='RESPOND_TO_EXPERIENCE_FEEDBACK'"
            )
        )
    deletion_ref = str(feedback_human_task.deletion_ref)
    deletion_service = SqlAlchemyExperienceFeedbackDeletionService(session_factory)
    deletion_proof = await deletion_service.delete_subject(
        tenant_id=ids["tenant"],
        subject_id=ids["child"],
        deletion_ref=deletion_ref,
        completed_at=NOW + timedelta(minutes=10),
    )
    deletion_replay = await deletion_service.delete_subject(
        tenant_id=ids["tenant"],
        subject_id=ids["child"],
        deletion_ref=deletion_ref,
        completed_at=NOW + timedelta(minutes=11),
    )
    async with engine.connect() as connection:
        post_deletion_counts = (
            await connection.execute(
                text(
                    "SELECT "
                    "(SELECT count(*) FROM ai_achievement_feedback), "
                    "(SELECT count(*) FROM ai_experience_feedback_resolutions), "
                    "(SELECT count(*) FROM ai_human_tasks "
                    " WHERE action_name='RESPOND_TO_EXPERIENCE_FEEDBACK'), "
                    "(SELECT count(*) FROM ai_accepted_action_deliveries "
                    " WHERE action_name='RESPOND_TO_EXPERIENCE_FEEDBACK')"
                )
            )
        ).one()
    await engine.dispose()

    assert started["action"]["execution_status"] == "IN_PROGRESS"
    assert paused["action"]["execution_status"] == "PAUSED"
    assert resumed["action"]["execution_status"] == "IN_PROGRESS"
    assert completed["action"]["task_state"] == "CHECKED_IN"
    assert completed["action"]["reflection"] == "我先停下来听完了。"
    assert replay["result_state"] == "REPLAYED"
    assert readback["today_task"]["task_state"] == "CHECKED_IN"
    assert relay_report.inspected == 4
    assert relay_report.published == 4
    assert relay_report.consent_discarded == 0
    assert relay_report.failed == 0
    assert relay_report.dead_lettered == 0
    assert relay_replay_report.inspected == 0
    assert set(achievement_keys) == {
        AchievementKey.FIRST_STEP.value,
        AchievementKey.PAUSE_AND_RETURN.value,
    }
    assert notification_count == 2
    assert action_started_metric == 1
    assert action_resumed_metric == 1
    assert growth_graph_edge_count == 4
    assert tuple((row.signal, row.human_task_id is not None) for row in feedback_rows) == (
        ("helpful", False),
        ("request_human", True),
        ("not_helpful", False),
    )
    assert tuple(feedback_human_task)[:3] == (
        "DECIDED",
        "RESPOND_TO_EXPERIENCE_FEEDBACK",
        "growth_tracking",
    )
    assert str(feedback_human_task.consent_version).startswith("db:")
    assert feedback_human_task.source_kind == "USER_REQUEST"
    assert feedback_human_task.region_id == "CN"
    assert str(feedback_human_task.deletion_ref).startswith("consent-delete:")
    assert helpful_feedback.json()["result_state"] == "RECORDED"
    assert helpful_feedback.json()["human_task_id"] is None
    assert human_feedback.json()["result_state"] == "RECORDED"
    assert human_feedback.json()["human_task_id"]
    assert human_replay.json()["result_state"] == "REPLAYED"
    assert human_replay.json()["human_task_id"] == human_feedback.json()["human_task_id"]
    assert feedback_audit_count == 8
    assert tuple(feedback_read_audit)[:2] == ("read", True)
    assert str(feedback_read_audit.approval_ref).startswith("human-gate:")
    assert feedback_read_audit.access_purpose == "growth_tracking"
    assert feedback_count_after_failures == 3
    assert feedback_task_count == 1
    assert response_delivery.status.value == "succeeded"
    assert tuple(feedback_resolution) == (
        "HUMAN_FOLLOWUP_QUEUED",
        "operator:family-support-1",
        human_feedback.json()["feedback_id"],
    )
    assert deletion_proof.deleted_feedback == 3
    assert deletion_proof.deleted_resolutions == 1
    assert deletion_proof.deleted_deliveries == 1
    assert deletion_proof.deleted_human_tasks == 1
    assert deletion_replay == deletion_proof
    assert tuple(post_deletion_counts) == (0, 0, 0, 0)
    assert revoked_report.consent_discarded == 1
    assert revoked_report.failed == 0
    assert experience_message_count == 4
    assert consent_discard_audit_count == 1
    assert malformed_report.failed == 1
    assert malformed_report.dead_lettered == 0
    assert malformed_retry_count == 1
    assert malformed_delivery_status == "RETRY"
    assert malformed_published_at is None
    assert source_published_count == 0
    assert audit_count >= 7
    assert events == (
        "AiDailyActionInitialized",
        "DailyActionStart",
        "DailyActionPause",
        "DailyActionResume",
        "DailyActionCheckedIn",
    )
    assert tuple(source_binding) == (
        "draft-growth-plan-1",
        "a" * 64,
        "model-draft:draft-growth-plan-1",
        "consent:e2e",
    )
