"""HTTP-to-PostgreSQL acceptance tests for GrowthIntent confirmation wiring."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.types import Uuid

from backend.apps.family_api.main import create_app
from backend.apps.family_api.production_growth_wiring import ProductionGrowthConfirmationWiring
from backend.domains.assessment.api.dependencies import FamilyContext, get_family_context
from backend.domains.assessment.application.growth_intent_handoff import (
    ViewedUnderstandingSignal,
)
from backend.domains.assessment.application.reviewed_understanding_signals import (
    RecordReviewedUnderstandingInput,
    RecordReviewedUnderstandingService,
)
from backend.domains.assessment.infrastructure.sqlalchemy_reviewed_understanding_signals import (
    SqlAlchemyReviewedUnderstandingSignals,
)
from backend.intelligence.family_understanding.api import AuthorizedFamilyContext
from backend.intelligence.family_understanding.contracts import KnowledgeRef
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.platform.audit import AuditBase
from backend.platform.outbox import OutboxMetadata
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url

metadata = MetaData()
reviewed_signals = Table(
    "assessment_reviewed_understanding_signals",
    metadata,
    Column("reviewed_signal_id", Uuid(as_uuid=True), primary_key=True),
    Column("tenant_id", Uuid(as_uuid=True), nullable=False),
    Column("family_id", Uuid(as_uuid=True), nullable=False),
    Column("assessment_session_id", Uuid(as_uuid=True), nullable=False),
    Column("signal_ref", String(256), nullable=False),
    Column("signal_version", Integer, nullable=False),
    Column("scope_ref", String(256), nullable=False),
    Column("reviewed_draft_ref", String(256), nullable=False),
    Column("draft_version", Integer, nullable=False),
    Column("provenance_ref", String(256), nullable=False),
    Column("draft_source", String(32), nullable=False),
    Column("output_schema_ref", String(256), nullable=False),
    Column("view_event_ref", String(256), nullable=False),
    Column("human_gate_receipt_ref", String(256), nullable=False),
    Column("effective_status", String(16), nullable=False),
    Column("reviewed_by_actor_id", Uuid(as_uuid=True), nullable=False),
    Column("reviewed_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True)),
    Column("revoked_at", DateTime(timezone=True)),
    Column("revocation_ref", String(256)),
    Column("subject_person_id", Uuid(as_uuid=True), nullable=False),
    Column("need_type", String(64), nullable=False),
    Column("goal_text", Text, nullable=False),
    Column("required_capability_keys", ARRAY(String), nullable=False),
    Column("evidence_refs", ARRAY(String), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint(
        "tenant_id",
        "family_id",
        "human_gate_receipt_ref",
        name="uq_reviewed_understanding_gate_receipt",
    ),
    CheckConstraint("signal_version > 0", name="ck_reviewed_understanding_signal_version"),
    CheckConstraint("draft_version > 0", name="ck_reviewed_understanding_draft_version"),
    CheckConstraint(
        "effective_status IN ('EFFECTIVE', 'REVOKED', 'EXPIRED')",
        name="ck_reviewed_understanding_effective_status",
    ),
    CheckConstraint(
        "draft_source = 'MODEL_GATEWAY'",
        name="ck_reviewed_understanding_model_gateway_source",
    ),
)
tenant_family_bindings = Table(
    "tenant_family_bindings",
    metadata,
    Column("tenant_id", Uuid(as_uuid=True), nullable=False),
    Column("family_id", Uuid(as_uuid=True), nullable=False),
    Column("status", String(16), nullable=False),
    Column("effective_from", DateTime(timezone=True), nullable=False),
    Column("effective_to", DateTime(timezone=True)),
)
audit_logs = Table(
    "audit_logs",
    metadata,
    Column("family_id", Uuid(as_uuid=True), nullable=False),
    Column("actor_id", Uuid(as_uuid=True), nullable=False),
    Column("action_name", String(128), nullable=False),
    Column("result", String(16), nullable=False),
)
family_memberships = Table(
    "family_memberships",
    metadata,
    Column("family_id", Uuid(as_uuid=True), nullable=False),
    Column("person_id", Uuid(as_uuid=True), nullable=False),
    Column("status", String(16), nullable=False),
    Column("role", String(32), nullable=False),
)
persons = Table(
    "persons",
    metadata,
    Column("person_id", Uuid(as_uuid=True), primary_key=True),
    Column("family_id", Uuid(as_uuid=True), nullable=False),
    Column("person_type", String(16), nullable=False),
)
consents = Table(
    "consents",
    metadata,
    Column("consent_id", Uuid(as_uuid=True), primary_key=True),
    Column("family_id", Uuid(as_uuid=True), nullable=False),
    Column("subject_person_id", Uuid(as_uuid=True), nullable=False),
    Column("purpose", String(32), nullable=False),
    Column("status", String(16), nullable=False),
)
growth_intents = Table(
    "growth_intents",
    metadata,
    Column("intent_id", Uuid(as_uuid=True), primary_key=True),
    Column("family_id", Uuid(as_uuid=True), nullable=False),
    Column("subject_person_id", Uuid(as_uuid=True), nullable=False),
    Column("signal_ref", Uuid(as_uuid=True)),
    Column("need_type", String(64), nullable=False),
    Column("goal_text", String, nullable=False),
    Column("required_capability_keys", ARRAY(String), nullable=False),
    Column("status", String(16), nullable=False),
    Column("close_reason", String(48)),
    Column("confirmed_by", Uuid(as_uuid=True), nullable=False),
    Column("confirmed_at", DateTime(timezone=True), nullable=False),
    Column("source_type", String(48), nullable=False),
    Column("source_ref", String(256)),
    Column("evidence_refs", ARRAY(Uuid(as_uuid=True)), nullable=False),
    Column("boundary", String(96), nullable=False),
)
idempotency_keys = Table(
    "idempotency_keys",
    metadata,
    Column("idempotency_key", String(128), primary_key=True),
    Column("action_name", String(128), nullable=False),
    Column("request_hash", String(128), nullable=False),
    Column("response_code", Integer),
    Column("response_body", JSON().with_variant(JSONB(), "postgresql")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True)),
)
decisions = Table(
    "family_growth_hypothesis_decisions",
    metadata,
    Column(
        "decision_id",
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("tenant_id", Uuid(as_uuid=True), nullable=False),
    Column("family_id", Uuid(as_uuid=True), nullable=False),
    Column("assessment_session_id", Uuid(as_uuid=True), nullable=False),
    Column("hypothesis_ref", String(256), nullable=False),
    Column("decision_type", String(16), nullable=False),
    Column("actor_person_id", Uuid(as_uuid=True), nullable=False),
    Column("intent_id", Uuid(as_uuid=True)),
    Column("idempotency_key", String(128), nullable=False),
    Column("request_hash", String(128), nullable=False),
    Column("response_body", JSON().with_variant(JSONB(), "postgresql"), nullable=False),
    Column("correlation_id", String(128), nullable=False),
)
AuditBase.metadata.tables["platform_audit_events"].to_metadata(metadata)
OutboxMetadata.tables["outbox_events"].to_metadata(metadata)

TENANT = uuid.UUID("10000000-0000-4000-8000-000000000001")
FAMILY = uuid.UUID("20000000-0000-4000-8000-000000000001")
ACTOR = uuid.UUID("30000000-0000-4000-8000-000000000001")
SUBJECT = uuid.UUID("40000000-0000-4000-8000-000000000001")
EVIDENCE = uuid.UUID("50000000-0000-4000-8000-000000000001")
SESSION = uuid.UUID("60000000-0000-4000-8000-000000000001")


def signal(**changes) -> ViewedUnderstandingSignal:
    value = ViewedUnderstandingSignal(
        tenant_id=str(TENANT),
        family_id=str(FAMILY),
        assessment_session_id=str(SESSION),
        signal_ref="ASSESSMENT:session-1:FAMILY_SUPPORT_NEEDS:v2:H1",
        signal_version=2,
        scope_ref=f"family://{TENANT}/{FAMILY}/assessment",
        reviewed_draft_ref="draft-1",
        draft_version=3,
        provenance_ref="provenance-1",
        human_gate_receipt_ref="human-gate-1",
        human_gate_effective_status="EFFECTIVE",
        reviewed_by_actor_id=str(ACTOR),
        subject_person_id=str(SUBJECT),
        need_type="PARENT_CHILD_COMMUNICATION",
        goal_text="希望晚饭后的沟通少一点争吵",
        required_capability_keys=("FAMILY_COMMUNICATION",),
        evidence_refs=(str(EVIDENCE),),
        reviewed_at=datetime(2026, 9, 1, 8, 0, tzinfo=UTC),
        draft_source="MODEL_GATEWAY",
        output_schema_ref="family_problem_understanding_v1",
        view_event_ref="view-event-1",
    )
    return replace(value, **changes)


def body(**changes) -> dict:
    value = signal()
    payload = {
        "assessment_session_id": value.assessment_session_id,
        "hypothesis_ref": value.signal_ref,
        "decision_type": "CONFIRM",
        "scope_ref": value.scope_ref,
        "signal_version": value.signal_version,
        "reviewed_draft_ref": value.reviewed_draft_ref,
        "draft_version": value.draft_version,
        "provenance_ref": value.provenance_ref,
        "human_gate_receipt_ref": value.human_gate_receipt_ref,
    }
    payload.update(changes)
    return payload


@pytest.fixture
async def database():
    if postgres_test_url() is None:
        pytest.skip(SKIP_REASON)
    async with postgres_schema_engine(metadata) as engine:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            now = datetime.now(UTC)
            await connection.execute(
                insert(tenant_family_bindings).values(
                    tenant_id=TENANT,
                    family_id=FAMILY,
                    status="ACTIVE",
                    effective_from=now,
                )
            )
            await connection.execute(
                insert(family_memberships).values(
                    family_id=FAMILY,
                    person_id=ACTOR,
                    status="ACTIVE",
                    role="OWNER_GUARDIAN",
                )
            )
            await connection.execute(
                insert(persons).values(
                    person_id=SUBJECT,
                    family_id=FAMILY,
                    person_type="CHILD",
                )
            )
            await connection.execute(
                insert(consents).values(
                    consent_id=uuid.uuid4(),
                    family_id=FAMILY,
                    subject_person_id=SUBJECT,
                    purpose="ASSESSMENT",
                    status="GRANTED",
                )
            )
        yield factory


@pytest.fixture(autouse=True)
def production_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "production")


def app_for(database):
    app = create_app(growth_confirmation_wiring=ProductionGrowthConfirmationWiring(database))
    app.dependency_overrides[get_family_context] = lambda: FamilyContext(
        tenant_id=str(TENANT), family_id=str(FAMILY), person_id=str(ACTOR)
    )
    return app


async def record_reviewed_signal(database) -> None:
    value = signal()
    command = RecordReviewedUnderstandingInput(
        tenant_id=value.tenant_id,
        family_id=value.family_id,
        assessment_session_id=value.assessment_session_id,
        signal_ref=value.signal_ref,
        signal_version=value.signal_version,
        scope_ref=value.scope_ref,
        reviewed_draft_ref=value.reviewed_draft_ref,
        draft_version=value.draft_version,
        provenance_ref=value.provenance_ref,
        draft_source="MODEL_GATEWAY",
        output_schema_ref=value.output_schema_ref or "",
        view_event_ref=value.view_event_ref or "",
        human_gate_receipt_ref=value.human_gate_receipt_ref,
        human_gate_effective_status="EFFECTIVE",
        reviewed_by_actor_id=value.reviewed_by_actor_id,
        reviewed_by_actor_type="FAMILY_GUARDIAN",
        reviewed_at=value.reviewed_at or datetime.now(UTC),
        expires_at=value.expires_at,
        subject_person_id=value.subject_person_id,
        need_type=value.need_type,
        goal_text=value.goal_text,
        required_capability_keys=value.required_capability_keys,
        evidence_refs=value.evidence_refs,
    )
    async with database.begin() as session:
        await RecordReviewedUnderstandingService(
            SqlAlchemyReviewedUnderstandingSignals(session)
        ).record_viewed(command)


class UnavailableUnderstandingApplication:
    async def generate(self, _command):
        raise ModelGatewayError("TIMEOUT", "provider timeout")


class AuthorizedContexts:
    async def resolve(self, *, tenant_id: str, family_id: str):
        return AuthorizedFamilyContext(
            tenant_id=tenant_id,
            family_id=family_id,
            subject_ref=str(SUBJECT),
            consent_ref="consent-1",
            context_snapshot_ref="context-1",
            context_expires_at=datetime(2099, 1, 1, tzinfo=UTC),
            reviewed_knowledge_refs=(
                KnowledgeRef(
                    ref="knowledge-1",
                    source="reviewed-guidance",
                    version="1",
                    chunk_ref="chunk-1",
                    content_digest="sha256:knowledge-1",
                    applicability="family communication",
                    limitations=("not a diagnosis",),
                ),
            ),
        )


def test_create_app_mounts_understanding_and_propagates_gateway_failure_as_503() -> None:
    app = create_app(
        family_understanding_application=UnavailableUnderstandingApplication(),
        authorized_contexts=AuthorizedContexts(),
    )

    response = TestClient(app).post(
        f"/v1/families/{FAMILY}/understanding-drafts",
        json={
            "run_id": "run-1",
            "tenant_id": str(TENANT),
            "guardian_input_ref": "input-1",
            "guardian_text": "晚饭后总会因为写作业争吵",
            "revision": 1,
            "prior_draft_artifact_hash": None,
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "UNDERSTANDING_TEMPORARILY_UNAVAILABLE"
    assert "固定" not in response.text


async def post(app, payload=None, *, key="decision-1", raise_app_exceptions=True):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions),
        base_url="http://test",
    ) as client:
        return await client.post(
            f"/families/{FAMILY}/growth-hypotheses/decisions",
            json=payload or body(),
            headers={"idempotency-key": key, "x-correlation-id": "correlation-1"},
        )


async def test_http_confirmation_persists_and_replays_after_app_rebuild(database) -> None:
    await record_reviewed_signal(database)
    first = await post(app_for(database))
    rebuilt = await post(app_for(database))

    assert first.status_code == 200, first.text
    assert rebuilt.status_code == 200, rebuilt.text
    uuid.UUID(first.json()["intent"]["intent_id"])
    assert "dev-synthetic" not in first.text
    assert first.json()["intent"]["intent_id"] == rebuilt.json()["intent"]["intent_id"]
    assert rebuilt.json()["replayed"] is True

    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(growth_intents)) == 1
        assert await session.scalar(select(func.count()).select_from(decisions)) == 1
        assert await session.scalar(select(func.count()).select_from(idempotency_keys)) == 1
        assert (
            await session.scalar(
                select(func.count()).select_from(metadata.tables["platform_audit_events"])
            )
            == 1
        )
        assert (
            await session.scalar(select(func.count()).select_from(metadata.tables["outbox_events"]))
            == 1
        )


async def test_conflict_cross_scope_and_withdrawal_fail_closed(database) -> None:
    await record_reviewed_signal(database)
    app = app_for(database)
    assert (await post(app)).status_code == 200
    assert (await post(app, body(reviewed_draft_ref="changed"))).status_code == 409
    assert (
        await post(app, body(scope_ref="family://other/other/assessment"), key="scope-1")
    ).status_code == 403

    async with database.begin() as session:
        await session.execute(update(consents).values(status="WITHDRAWN"))
    withdrawn = app_for(database)
    assert (await post(withdrawn, key="withdrawn-1")).status_code == 403

    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(growth_intents)) == 1
        assert await session.scalar(select(func.count()).select_from(decisions)) == 1


async def test_assessment_persistence_failure_rolls_growth_audit_outbox_and_receipt_back(
    database,
) -> None:
    await record_reviewed_signal(database)
    async with database.kw["bind"].begin() as connection:
        await connection.run_sync(decisions.drop)

    response = await post(
        app_for(database),
        key="rollback-1",
        raise_app_exceptions=False,
    )

    assert response.status_code == 500
    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(growth_intents)) == 0
        assert await session.scalar(select(func.count()).select_from(idempotency_keys)) == 0
        assert (
            await session.scalar(
                select(func.count()).select_from(metadata.tables["platform_audit_events"])
            )
            == 0
        )
        assert (
            await session.scalar(select(func.count()).select_from(metadata.tables["outbox_events"]))
            == 0
        )
