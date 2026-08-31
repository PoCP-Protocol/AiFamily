"""HTTP-to-PostgreSQL acceptance tests for GrowthIntent confirmation wiring."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
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
from backend.platform.audit import AuditBase
from backend.platform.outbox import OutboxMetadata
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url

metadata = MetaData()
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


class SignalReader:
    def __init__(self, signal: ViewedUnderstandingSignal) -> None:
        self.signal = signal

    async def load_viewed_signal(self, **_: str) -> ViewedUnderstandingSignal:
        return self.signal


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


def app_for(database, reader: SignalReader):
    app = create_app(
        growth_confirmation_wiring=ProductionGrowthConfirmationWiring(database, reader)
    )
    app.dependency_overrides[get_family_context] = lambda: FamilyContext(
        tenant_id=str(TENANT), family_id=str(FAMILY), person_id=str(ACTOR)
    )
    return app


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
    first = await post(app_for(database, SignalReader(signal())))
    rebuilt = await post(app_for(database, SignalReader(signal())))

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
    app = app_for(database, SignalReader(signal()))
    assert (await post(app)).status_code == 200
    assert (await post(app, body(reviewed_draft_ref="changed"))).status_code == 409
    assert (
        await post(app, body(scope_ref="family://other/other/assessment"), key="scope-1")
    ).status_code == 403

    async with database.begin() as session:
        await session.execute(update(consents).values(status="WITHDRAWN"))
    withdrawn = app_for(database, SignalReader(signal()))
    assert (await post(withdrawn, key="withdrawn-1")).status_code == 403

    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(growth_intents)) == 1
        assert await session.scalar(select(func.count()).select_from(decisions)) == 1


async def test_assessment_persistence_failure_rolls_growth_audit_outbox_and_receipt_back(
    database,
) -> None:
    async with database.kw["bind"].begin() as connection:
        await connection.run_sync(decisions.drop)

    response = await post(
        app_for(database, SignalReader(signal())),
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
