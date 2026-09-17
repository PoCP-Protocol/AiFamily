"""Real HTTP/PostgreSQL evidence for the Assessment -> Guardian Intent flow.

This test deliberately uses the application factory with an explicit
PostgreSQL URL.  The deterministic interpretation adapter is test plumbing;
the evidence being established here is the durable identity, authorization,
repository and restart-readback path.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import make_url, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.apps.family_api.assessment_ai_wiring import AssessmentAiAssets
from backend.apps.family_api.assessment_human_task_decision import (
    ASSESSMENT_REJECTION_REASON_UNSPECIFIED,
)
from backend.apps.family_api.main import create_app
from backend.apps.family_api.production_assessment_http_wiring import (
    ProductionAssessmentAiCompositionResolver,
    SqlAlchemyAssessmentIdentityResolver,
    install_production_assessment_http_wiring,
)
from backend.intelligence.agent_runtime.authorization_persistence import (
    SqlAlchemyAgentAuthorizationLeaseStore,
)
from backend.intelligence.agent_runtime.contracts import AgentAuthorization, AuthorizationBudget
from backend.intelligence.context_engine.sql_store import AsyncSqlContextBroker
from backend.intelligence.experience.execution_materials import (
    SqlAlchemyExecutionMaterialRegistry,
    SystemPolicyMaterial,
)
from backend.intelligence.model_gateway.attempt_persistence import SqlAlchemyAttemptSink
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import ProviderRecord, ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import deterministic_provider
from backend.intelligence.observability import SqlAlchemyTelemetrySink
from backend.intelligence.prompt_registry.contracts import PromptBundle
from backend.intelligence.prompt_registry.registry import PromptRegistry
from backend.intelligence.safety.persistence import SqlAlchemySafetyDecisionSink
from backend.intelligence.safety.runtime import SafetyRuntime
from backend.intelligence.schema_registry.contracts import SchemaDefinition
from backend.intelligence.schema_registry.registry import SchemaRegistry
from backend.platform.persistence.session import DATABASE_URL_ENV_VAR, clear_engine_cache
from tests.support.postgres import SKIP_REASON, postgres_test_url

ROOT = Path(__file__).resolve().parents[3]
TENANT = "21000000-0000-4000-8000-000000000001"
FAMILY = "21000000-0000-4000-8000-000000000002"
PARENT = "21000000-0000-4000-8000-000000000003"
CHILD = "21000000-0000-4000-8000-000000000004"
ACCOUNT = "21000000-0000-4000-8000-000000000005"
ACCOUNT_BINDING = "21000000-0000-4000-8000-000000000006"
MEMBERSHIP = "21000000-0000-4000-8000-000000000007"
TENANT_MEMBERSHIP = "21000000-0000-4000-8000-000000000008"
TENANT_FAMILY = "21000000-0000-4000-8000-000000000009"
SESSION = "21000000-0000-4000-8000-000000000010"
CONSENT = "21000000-0000-4000-8000-000000000011"
GROWTH_CONSENT = "21000000-0000-4000-8000-000000000012"
TOKEN = "assessment-http-postgres-token"


def _alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, DATABASE_URL_ENV_VAR: database_url},
    )


@pytest.fixture
async def database_url() -> AsyncIterator[str]:
    admin_url = postgres_test_url()
    if admin_url is None:
        pytest.skip(SKIP_REASON)
    name = f"assessment_http_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(
        admin_url,
        isolation_level="AUTOCOMMIT",
        connect_args={"statement_cache_size": 0},
    )
    created = False
    try:
        try:
            async with admin.connect() as connection:
                await connection.execute(text(f'CREATE DATABASE "{name}"'))
            created = True
        except (OSError, SQLAlchemyError) as error:
            pytest.skip(f"external PostgreSQL unavailable: {type(error).__name__}")
        url = make_url(admin_url).set(database=name).render_as_string(hide_password=False)
        result = _alembic(url, "upgrade", "head")
        assert result.returncode == 0, f"alembic failed:\n{result.stdout}\n{result.stderr}"
        yield url
    finally:
        if created:
            async with admin.connect() as connection:
                await connection.execute(
                    text(
                        "select pg_terminate_backend(pid) from pg_stat_activity "
                        "where datname=:name and pid <> pg_backend_pid()"
                    ),
                    {"name": name},
                )
                await connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        await admin.dispose()


@asynccontextmanager
async def _engine(url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(url, connect_args={"statement_cache_size": 0})
    try:
        yield engine
    finally:
        await engine.dispose()


async def _seed(url: str) -> None:
    async with _engine(url) as engine, engine.begin() as connection:
        await connection.execute(
            text(
                "insert into tenants(tenant_id,tenant_ref,display_name,tenant_type,status,"
                "region_ref) "
                "values (cast(:tenant as uuid),'assessment-http','Assessment HTTP',"
                "'DIRECT_CUSTOMER','ACTIVE','CN')"
            ),
            {"tenant": TENANT},
        )
        await connection.execute(
            text(
                "insert into families(family_id,display_name,status) values "
                "(cast(:family as uuid),'Assessment HTTP Family','ACTIVE')"
            ),
            {"family": FAMILY},
        )
        await connection.execute(
            text(
                "insert into persons(person_id,family_id,person_type,parent_role,display_name,"
                "birth_date) values (cast(:parent as uuid),cast(:family as uuid),'PARENT',"
                "'GUARDIAN','Parent',date '1990-01-01'),(cast(:child as uuid),"
                "cast(:family as uuid),'CHILD',null,'Child',date '2016-01-01')"
            ),
            {"parent": PARENT, "child": CHILD, "family": FAMILY},
        )
        await connection.execute(
            text(
                "insert into accounts(account_id,external_ref,status) values "
                "(cast(:account as uuid),'assessment-http-account','ACTIVE')"
            ),
            {"account": ACCOUNT},
        )
        await connection.execute(
            text(
                "insert into account_person_bindings(binding_id,account_id,person_id,status) "
                "values (cast(:binding as uuid),cast(:account as uuid),"
                "cast(:parent as uuid),'ACTIVE')"
            ),
            {"binding": ACCOUNT_BINDING, "account": ACCOUNT, "parent": PARENT},
        )
        await connection.execute(
            text(
                "insert into family_memberships(membership_id,family_id,person_id,role,status) "
                "values (cast(:membership as uuid),cast(:family as uuid),cast(:parent as uuid),"
                "'OWNER_GUARDIAN','ACTIVE')"
            ),
            {"membership": MEMBERSHIP, "family": FAMILY, "parent": PARENT},
        )
        await connection.execute(
            text(
                "insert into tenant_account_memberships(tenant_membership_id,tenant_id,account_id,"
                "role,status,valid_from) values (cast(:membership as uuid),cast(:tenant as uuid),"
                "cast(:account as uuid),'TENANT_OWNER','ACTIVE',now())"
            ),
            {"membership": TENANT_MEMBERSHIP, "tenant": TENANT, "account": ACCOUNT},
        )
        await connection.execute(
            text(
                "insert into tenant_family_bindings(tenant_family_binding_id,tenant_id,family_id,"
                "status,effective_from) values (cast(:binding as uuid),cast(:tenant as uuid),"
                "cast(:family as uuid),'ACTIVE',now())"
            ),
            {"binding": TENANT_FAMILY, "tenant": TENANT, "family": FAMILY},
        )
        await connection.execute(
            text(
                "insert into identity_sessions(session_id,token_hash,person_id,family_id,"
                "account_ref,expires_at) values (cast(:session as uuid),:hash,"
                "cast(:parent as uuid),cast(:family as uuid),cast(:account as uuid),"
                "now()+interval '1 hour')"
            ),
            {
                "session": SESSION,
                "hash": hashlib.sha256(TOKEN.encode()).hexdigest(),
                "parent": PARENT,
                "family": FAMILY,
                "account": ACCOUNT,
            },
        )
        await connection.execute(
            text(
                "insert into consents(consent_id,family_id,subject_person_id,guardian_person_id,"
                "purpose,status,policy_version,granted_at,withdrawn_at) values "
                "(cast(:consent as uuid),cast(:family as uuid),cast(:child as uuid),"
                "cast(:parent as uuid),:purpose,'GRANTED',:policy,now(),null)"
            ),
            {
                "consent": CONSENT,
                "family": FAMILY,
                "child": CHILD,
                "parent": PARENT,
                "purpose": "ASSESSMENT",
                "policy": "assessment-http-v1",
            },
        )
        await connection.execute(
            text(
                "insert into consents(consent_id,family_id,subject_person_id,guardian_person_id,"
                "purpose,status,policy_version,granted_at,withdrawn_at) values "
                "(cast(:consent as uuid),cast(:family as uuid),cast(:child as uuid),"
                "cast(:parent as uuid),'GROWTH_TRACKING','GRANTED','growth-http-v1',now(),null)"
            ),
            {
                "consent": GROWTH_CONSENT,
                "family": FAMILY,
                "child": CHILD,
                "parent": PARENT,
            },
        )
        await connection.execute(
            text(
                "insert into tenant_policy_profiles(tenant_id,policy_version,status,allowed_pages) "
                "values (cast(:tenant as uuid),'assessment-http-v1','ACTIVE',cast(:pages as jsonb))"
            ),
            {"tenant": TENANT, "pages": '["UI-01","UI-02","UI-03"]'},
        )


def _headers(key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Idempotency-Key": key,
        "X-Correlation-Id": f"http:{key}",
    }


def _governed_model_output(request) -> dict[str, object]:
    assessment_ref = str(request.payload["assessment_ref"])
    return {
        "model_component_ref": "FAMILY_ASSESSMENT_V1",
        "assessment_ref": assessment_ref,
        "boundary_labels": ["hypothesis_not_fact", "recommendation_not_decision"],
        "need_summary": [{"need_ref": "COMMUNICATION_SUPPORT"}],
        "construct_signals": [
            {
                "construct_ref": "PARENT_CHILD_COMMUNICATION",
                "boundary": "signal_not_diagnosis",
            }
        ],
        "hypotheses": [
            {
                "hypothesis_ref": f"{assessment_ref}:H1",
                "boundary": "hypothesis_not_fact",
                "construct_refs": ["PARENT_CHILD_COMMUNICATION"],
                "is_primary_contradiction": True,
            }
        ],
        "action_candidates": [
            {
                "action_ref": "COMMUNICATION_SUPPORT:ACTION",
                "boundary": "recommendation_not_decision",
            }
        ],
    }


def _production_assessment_app(database_url: str):
    engine = create_async_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"statement_cache_size": 0},
    )
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    provider = deterministic_provider(
        _governed_model_output,
        provider_id="assessment-http-governed-fake",
    )
    gateway = ModelGateway(
        {provider.provider_id: provider},
        environment="staging",
        registry=ProviderRegistry(
            (
                ProviderRecord(
                    provider_id=provider.provider_id,
                    vendor="aifamily-test",
                    model="fake",
                    model_version="1",
                    status="INTERNAL_APPROVED",
                    approved_environments=("staging",),
                    sub_delegates=False,
                    minor_data_allowed=True,
                    security_assessment_ref="test-only-admission",
                    processing_agreement_ref="test-only-processing",
                    deletion_on_termination_committed=True,
                ),
            )
        ),
        safety_runtime=SafetyRuntime(),
    )
    prompt = PromptBundle(
        prompt_ref="assessment_http_interpretation_v1",
        version="1.0.0",
        use_case="assessment_interpretation",
        agent_id="parent_advisor",
        template="Explain evidence as a non-diagnostic family perspective.",
        system_policy_ref="assessment-http-policy-v1",
        knowledge_refs=(),
        input_contract_ref="assessment-http-input-v1",
        output_schema_ref="assessment_http_growth_perspective_v1",
        safety_policy_version="assessment-http-safety-v1",
        locale="zh-CN",
        author="test",
        reviewer="test-reviewer",
        status="PUBLISHED",
        effective_at=datetime.now(UTC) - timedelta(days=1),
    )
    schema = SchemaDefinition(
        schema_ref="assessment_http_growth_perspective_v1",
        version="1.0.0",
        use_case="assessment_interpretation",
        agent_id="parent_advisor",
        object_type="GrowthPerspective",
        json_schema={
            "type": "object",
            "required": [
                "model_component_ref",
                "assessment_ref",
                "boundary_labels",
                "need_summary",
                "construct_signals",
                "hypotheses",
                "action_candidates",
            ],
            "properties": {
                "model_component_ref": {"type": "string"},
                "assessment_ref": {"type": "string"},
                "boundary_labels": {"type": "array"},
                "need_summary": {"type": "array"},
                "construct_signals": {"type": "array"},
                "hypotheses": {"type": "array"},
                "action_candidates": {"type": "array"},
            },
        },
        status="PUBLISHED",
        effective_at=datetime.now(UTC) - timedelta(days=1),
        reviewer="test-reviewer",
    )
    assets = AssessmentAiAssets(
        prompt_ref=prompt.prompt_ref,
        prompt_version=prompt.version,
        schema_ref=schema.schema_ref,
        schema_version=schema.version,
        reviewed_construct_refs=frozenset({"PARENT_CHILD_COMMUNICATION"}),
    )
    composition_resolver = ProductionAssessmentAiCompositionResolver(
        engine=engine,
        session_factory=sessions,
        gateway=gateway,
        provider_id=provider.provider_id,
        registry_path=ROOT / "governance" / "AI_USE_CASE_REGISTRY.yaml",
        attempt_sink_factory=SqlAlchemyAttemptSink,
        safety_sink_factory=SqlAlchemySafetyDecisionSink,
        telemetry_sink_factory=SqlAlchemyTelemetrySink,
        context_broker=AsyncSqlContextBroker(sessions),
        assets=assets,
        environment="staging",
        clock=lambda: datetime.now(UTC),
        prompt_registry=PromptRegistry(bundles=(prompt,)),
        schema_registry=SchemaRegistry(definitions=(schema,)),
    )
    identity_resolver = SqlAlchemyAssessmentIdentityResolver(engine, sessions)
    app = create_app(
        assessment_production_ai_wiring=lambda application: (
            install_production_assessment_http_wiring(
                application,
                engine=engine,
                identity_resolver=identity_resolver,
                composition_resolver=composition_resolver,
            )
        )
    )
    return app, engine, sessions, provider


@contextmanager
def _production_client(app, engine: AsyncEngine) -> Iterator[TestClient]:
    """Keep pooled asyncpg connections on one TestClient portal loop."""

    with TestClient(app) as client:
        try:
            yield client
        finally:
            if client.portal is None:  # pragma: no cover - TestClient lifecycle guard
                raise RuntimeError("TestClient portal closed before engine disposal")
            client.portal.call(engine.dispose)


async def _assert_no_application_connections(database_url: str) -> None:
    async with _engine(database_url) as engine, engine.connect() as connection:
        remaining = int(
            await connection.scalar(
                text(
                    "select count(*) from pg_stat_activity "
                    "where datname=current_database() and pid<>pg_backend_pid()"
                )
            )
        )
    assert remaining == 0


async def _seed_governed_ai_controls(database_url: str) -> None:
    now = datetime.now(UTC)
    async with _engine(database_url) as engine:
        sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with sessions() as session:
            await SqlAlchemyAgentAuthorizationLeaseStore(session).issue(
                AgentAuthorization(
                    authorization_id="assessment-http-agent-authorization",
                    agent_id="parent_advisor",
                    tenant_id=TENANT,
                    family_id=FAMILY,
                    allowed_use_cases=frozenset({"assessment_interpretation"}),
                    allowed_tools=frozenset({"read_context"}),
                    issued_by=PARENT,
                    issued_at=now - timedelta(minutes=5),
                    expires_at=now + timedelta(hours=1),
                    revoked_at=None,
                    budget=AuthorizationBudget(max_steps=1),
                    policy_version="assessment-http-authorization-v1",
                    reason="guardian requested an assessment perspective",
                    audit_ref="audit:assessment-http-agent-authorization",
                )
            )
            await SqlAlchemyExecutionMaterialRegistry(session).register_policy(
                SystemPolicyMaterial.build(
                    policy_ref="assessment-http-policy-v1",
                    use_case="assessment_interpretation",
                    agent_id="parent_advisor",
                    content="Return a reviewable family perspective, never a diagnosis or fact.",
                    locale="zh-CN",
                    status="PUBLISHED",
                    reviewer="test-reviewer",
                    effective_at=now - timedelta(days=1),
                )
            )
            await session.commit()


@pytest.mark.asyncio
async def test_assessment_http_postgres_restart_readback_and_scope(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed(database_url)
    monkeypatch.setenv("AIFAMILY_ENV", "test")
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    clear_engine_cache()

    app = create_app()
    with TestClient(app) as client:
        headers = _headers("assessment-http")
        ui02 = client.get(f"/families/{FAMILY}/ui/02/assessment", headers=headers)
        assert ui02.status_code == 200, ui02.text
        assert ui02.json()["availability"] == "AVAILABLE"

        started = client.post(
            f"/families/{FAMILY}/assessments/sessions",
            headers=headers,
            json={"subject_person_id": CHILD},
        )
        assert started.status_code == 200, started.text
        session_id = started.json()["session"]["assessment_session_id"]

        response = client.post(
            f"/families/{FAMILY}/assessments/sessions/{session_id}/responses",
            headers=_headers("assessment-response"),
            json={
                "item_ref": "FOCUS",
                "response_type": "SINGLE_CHOICE",
                "response_value": "PARENT_CHILD_COMMUNICATION",
            },
        )
        assert response.status_code == 200, response.text

        submitted = client.post(
            f"/families/{FAMILY}/assessments/sessions/{session_id}/submit",
            headers=_headers("assessment-submit"),
        )
        assert submitted.status_code == 200, submitted.text

        projection = client.get(f"/families/{FAMILY}/ui/03/growth-hypothesis", headers=headers)
        assert projection.status_code == 200, projection.text
        body = projection.json()
        assert body["availability"] == "READY"
        assert body["hypothesis"]["fact_boundary"] == "HYPOTHESIS_NOT_FACT_OR_DIAGNOSIS"

        decision = client.post(
            f"/families/{FAMILY}/growth-hypotheses/decisions",
            headers=_headers("assessment-confirm"),
            json={
                "assessment_session_id": session_id,
                "hypothesis_ref": body["hypothesis"]["hypothesis_ref"],
                "decision_type": "CONFIRM",
            },
        )
        assert decision.status_code == 200, decision.text
        assert decision.json()["intent"]["boundary"] == "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME"

        onboarding = client.post(
            f"/families/{FAMILY}/growth/onboardings",
            headers=_headers("assessment-onboarding"),
            json={"intent_id": decision.json()["intent"]["intent_id"]},
        )
        assert onboarding.status_code == 200, onboarding.text
        onboarding_body = onboarding.json()
        assert onboarding_body["created"] is True
        onboarding_id = onboarding_body["onboarding"]["onboarding_id"]

        priority = client.get(
            f"/families/{FAMILY}/growth/onboardings/{onboarding_id}/priority",
            headers=headers,
        )
        assert priority.status_code == 200, priority.text
        assert priority.json()["onboarding_id"] == onboarding_id
        assert priority.json()["boundary"] == "PRIORITY_IS_HUMAN_CONFIRMED_PRACTICE_FOCUS_NOT_SCORE"

        async with _engine(database_url) as engine, engine.begin() as connection:
            before_counts = {
                table: int(
                    await connection.scalar(
                        text(
                            "select count(*) from ai_run_ledger l "
                            "join family_assessment_sessions s "
                            "on cast(s.assessment_session_id as text)="
                            "l.assessment_session_id "
                            "where s.family_id=cast(:family_id as uuid)"
                        )
                        if table == "ai_run_ledger"
                        else text(f"select count(*) from {table} where family_id=:family_id"),
                        {"family_id": FAMILY},
                    )
                )
                for table in (
                    "family_assessment_sessions",
                    "family_growth_hypothesis_decisions",
                    "ai_run_ledger",
                )
            }
            await connection.execute(
                text(
                    "update consents set status='WITHDRAWN', withdrawn_at=now() "
                    "where consent_id=cast(:consent_id as uuid)"
                ),
                {"consent_id": CONSENT},
            )

        withdrawn_projection = client.get(
            f"/families/{FAMILY}/ui/03/growth-hypothesis",
            headers=_headers("assessment-after-withdrawal"),
        )
        assert withdrawn_projection.status_code == 403, withdrawn_projection.text

        async with _engine(database_url) as engine, engine.begin() as connection:
            after_counts = {
                table: int(
                    await connection.scalar(
                        text(
                            "select count(*) from ai_run_ledger l "
                            "join family_assessment_sessions s "
                            "on cast(s.assessment_session_id as text)="
                            "l.assessment_session_id "
                            "where s.family_id=cast(:family_id as uuid)"
                        )
                        if table == "ai_run_ledger"
                        else text(f"select count(*) from {table} where family_id=:family_id"),
                        {"family_id": FAMILY},
                    )
                )
                for table in before_counts
            }
        assert after_counts == before_counts

        cross_family = client.get(
            "/families/21000000-0000-4000-8000-000000000099/ui/03/growth-hypothesis",
            headers=headers,
        )
        # The bearer session is bound to FAMILY.  Asking the trusted identity
        # resolver to authenticate it for another family yields 401 before a
        # route-level family comparison; either way, the cross-family read is
        # fail-closed and leaks no projection.
        assert cross_family.status_code == 401

    clear_engine_cache()
    restarted_app = create_app()
    with TestClient(restarted_app) as restarted:
        withdrawn_readback = restarted.get(
            f"/families/{FAMILY}/ui/03/growth-hypothesis", headers=headers
        )
        assert withdrawn_readback.status_code == 403, withdrawn_readback.text


@pytest.mark.asyncio
async def test_assessment_human_task_decision_survives_restart_and_confirms_downstream(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed(database_url)
    await _seed_governed_ai_controls(database_url)
    monkeypatch.setenv("AIFAMILY_ENV", "test")
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    clear_engine_cache()

    app, engine, _, provider = _production_assessment_app(database_url)
    with _production_client(app, engine) as client:
        started = client.post(
            f"/families/{FAMILY}/assessments/sessions",
            headers=_headers("human-gate-start"),
            json={"subject_person_id": CHILD},
        )
        assert started.status_code == 200, started.text
        session_id = started.json()["session"]["assessment_session_id"]
        saved = client.post(
            f"/families/{FAMILY}/assessments/sessions/{session_id}/responses",
            headers=_headers("human-gate-response"),
            json={
                "item_ref": "FOCUS",
                "response_type": "SINGLE_CHOICE",
                "response_value": "PARENT_CHILD_COMMUNICATION",
            },
        )
        assert saved.status_code == 200, saved.text
        submitted = client.post(
            f"/families/{FAMILY}/assessments/sessions/{session_id}/submit",
            headers=_headers("human-gate-submit"),
        )
        assert submitted.status_code == 200, submitted.text
        projection = client.get(
            f"/families/{FAMILY}/ui/03/growth-hypothesis",
            headers=_headers("human-gate-draft"),
        )
        assert projection.status_code == 200, projection.text
        projection_body = projection.json()
        task_id = projection_body["hypothesis"]["scorecard"]["human_task_ref"]
        first = client.post(
            f"/families/{FAMILY}/assessment/human-tasks/{task_id}/decisions",
            headers=_headers("stable-human-decision"),
            json={"outcome": "ACCEPT", "reason": "监护人确认这是一项待验证假设"},
        )
        assert first.status_code == 200, first.text
        first_receipt = first.json()
        assert first_receipt["outcome"] == "ACCEPT"
        assert first_receipt["decision_id"].startswith("assessment-decision:")
        assert len(first_receipt["decision_id"]) == len("assessment-decision:") + 64
        first_binding = first_receipt["binding"]
        assert first_binding["subject_person_id"] == CHILD
        assert first_binding["assessment_session_id"] == session_id
        assert first_binding["hypothesis_ref"] == projection_body["hypothesis"]["hypothesis_ref"]
        assert first_binding["scope_ref"] == f"family://{TENANT}/{FAMILY}/assessment"
        assert (
            first_binding["signal_version"]
            == (projection_body["hypothesis"]["source_refs"]["tool_version"])
        )
        assert first_binding["reviewed_draft_ref"].startswith("agent-draft:")
        assert first_binding["draft_version"] == 1
        assert first_binding["provenance_ref"].startswith("agent-provenance:")
        assert first_binding["human_gate_receipt_ref"] == task_id
    await _assert_no_application_connections(database_url)

    restarted_app, restarted_engine, _, restarted_provider = _production_assessment_app(
        database_url
    )
    with _production_client(restarted_app, restarted_engine) as restarted:
        replay = restarted.post(
            f"/families/{FAMILY}/assessment/human-tasks/{task_id}/decisions",
            headers={
                **_headers("stable-human-decision"),
                "X-Correlation-Id": "human-gate-after-process-restart",
            },
            json={"outcome": "ACCEPT", "reason": "监护人确认这是一项待验证假设"},
        )
        assert replay.status_code == 200, replay.text
        assert replay.json() == first_receipt

        changed_payload = restarted.post(
            f"/families/{FAMILY}/assessment/human-tasks/{task_id}/decisions",
            headers=_headers("stable-human-decision"),
            json={"outcome": "REJECT", "reason": "同 key 不同 payload"},
        )
        assert changed_payload.status_code == 409

        binding = replay.json()["binding"]
        confirmation = restarted.post(
            f"/families/{FAMILY}/growth-hypotheses/decisions",
            headers=_headers("human-gate-downstream-confirm"),
            json={
                "assessment_session_id": binding["assessment_session_id"],
                "hypothesis_ref": binding["hypothesis_ref"],
                "decision_type": "CONFIRM",
                "scope_ref": binding["scope_ref"],
                "signal_version": binding["signal_version"],
                "reviewed_draft_ref": binding["reviewed_draft_ref"],
                "draft_version": binding["draft_version"],
                "provenance_ref": binding["provenance_ref"],
                "human_gate_receipt_ref": binding["human_gate_receipt_ref"],
            },
        )
        assert confirmation.status_code == 200, confirmation.text
        assert confirmation.json()["intent"]["boundary"] == ("HUMAN_CONFIRMED_INTENT_NOT_OUTCOME")
    await _assert_no_application_connections(database_url)

    assert len(provider.invocations) == 1
    assert restarted_provider.invocations == []
    async with _engine(database_url) as verification_engine, verification_engine.connect() as conn:
        task_row = (
            await conn.execute(
                text(
                    "select decision_id,decision_payload,action_request_payload "
                    "from ai_human_tasks where task_id=:task_id"
                ),
                {"task_id": task_id},
            )
        ).one()
        audit_count = int(
            await conn.scalar(
                text(
                    "select count(*) from platform_audit_events "
                    "where action='DECIDE_HUMAN_TASK' and resource_id=:task_id"
                ),
                {"task_id": task_id},
            )
        )
        downstream_count = int(
            await conn.scalar(
                text(
                    "select count(*) from family_growth_hypothesis_decisions "
                    "where family_id=cast(:family_id as uuid) "
                    "and assessment_session_id=cast(:session_id as uuid)"
                ),
                {"family_id": FAMILY, "session_id": session_id},
            )
        )
    assert task_row.decision_id == first_receipt["decision_id"]
    assert task_row.decision_payload["actor_id"] == PARENT
    assert task_row.action_request_payload["scope"]["subject_ids"] == [CHILD]
    assert audit_count == 1
    assert downstream_count == 1
    clear_engine_cache()


@pytest.mark.asyncio
async def test_assessment_reject_without_reason_is_audited_and_replays_after_restart(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed(database_url)
    await _seed_governed_ai_controls(database_url)
    monkeypatch.setenv("AIFAMILY_ENV", "test")
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    clear_engine_cache()

    app, engine, _, provider = _production_assessment_app(database_url)
    with _production_client(app, engine) as client:
        started = client.post(
            f"/families/{FAMILY}/assessments/sessions",
            headers=_headers("reasonless-reject-start"),
            json={"subject_person_id": CHILD},
        )
        assert started.status_code == 200, started.text
        session_id = started.json()["session"]["assessment_session_id"]
        saved = client.post(
            f"/families/{FAMILY}/assessments/sessions/{session_id}/responses",
            headers=_headers("reasonless-reject-response"),
            json={
                "item_ref": "FOCUS",
                "response_type": "SINGLE_CHOICE",
                "response_value": "PARENT_CHILD_COMMUNICATION",
            },
        )
        assert saved.status_code == 200, saved.text
        submitted = client.post(
            f"/families/{FAMILY}/assessments/sessions/{session_id}/submit",
            headers=_headers("reasonless-reject-submit"),
        )
        assert submitted.status_code == 200, submitted.text
        projection = client.get(
            f"/families/{FAMILY}/ui/03/growth-hypothesis",
            headers=_headers("reasonless-reject-draft"),
        )
        assert projection.status_code == 200, projection.text
        task_id = projection.json()["hypothesis"]["scorecard"]["human_task_ref"]
        rejected = client.post(
            f"/families/{FAMILY}/assessment/human-tasks/{task_id}/decisions",
            headers=_headers("stable-reasonless-reject"),
            json={"outcome": "REJECT"},
        )
        assert rejected.status_code == 200, rejected.text
        receipt = rejected.json()
        assert receipt["outcome"] == "REJECT"
        assert receipt["reason"] == ASSESSMENT_REJECTION_REASON_UNSPECIFIED
        assert receipt["binding"] is None
    await _assert_no_application_connections(database_url)

    restarted_app, restarted_engine, _, restarted_provider = _production_assessment_app(
        database_url
    )
    with _production_client(restarted_app, restarted_engine) as restarted:
        replay = restarted.post(
            f"/families/{FAMILY}/assessment/human-tasks/{task_id}/decisions",
            headers=_headers("stable-reasonless-reject"),
            json={"outcome": "REJECT"},
        )
        assert replay.status_code == 200, replay.text
        assert replay.json() == receipt
    await _assert_no_application_connections(database_url)

    assert len(provider.invocations) == 1
    assert restarted_provider.invocations == []
    async with _engine(database_url) as verification_engine, verification_engine.connect() as conn:
        task_row = (
            await conn.execute(
                text("select decision_payload from ai_human_tasks where task_id=:task_id"),
                {"task_id": task_id},
            )
        ).one()
        audit_rows = (
            await conn.execute(
                text(
                    "select reason from platform_audit_events "
                    "where action='DECIDE_HUMAN_TASK' and resource_id=:task_id"
                ),
                {"task_id": task_id},
            )
        ).all()
    assert task_row.decision_payload["reason"] == ASSESSMENT_REJECTION_REASON_UNSPECIFIED
    assert [row.reason for row in audit_rows] == [ASSESSMENT_REJECTION_REASON_UNSPECIFIED]
    clear_engine_cache()
