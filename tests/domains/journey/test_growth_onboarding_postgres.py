from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from backend.domains.journey.application.growth_onboarding import (
    GrowthOnboardingApplication,
    StartGrowthOnboardingCommand,
)
from backend.domains.journey.domain.growth_onboarding import (
    CONFIRMED_INTENT_BOUNDARY,
    GrowthOnboardingScope,
)
from backend.domains.journey.infrastructure.growth_onboarding_postgres import (
    PostgresGrowthOnboardingTransaction,
    SqlAlchemyGrowthOnboardingConsent,
    build_postgres_growth_onboarding_application,
)
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url

metadata = MetaData()

Table(
    "tenant_family_bindings",
    metadata,
    Column("tenant_family_binding_id", PGUUID(as_uuid=False), primary_key=True),
    Column("tenant_id", PGUUID(as_uuid=False), nullable=False),
    Column("family_id", PGUUID(as_uuid=False), nullable=False),
    Column("status", String(16), nullable=False),
    Column("effective_from", DateTime(timezone=True), nullable=False),
    Column("effective_to", DateTime(timezone=True)),
)
Table(
    "family_memberships",
    metadata,
    Column("membership_id", PGUUID(as_uuid=False), primary_key=True),
    Column("family_id", PGUUID(as_uuid=False), nullable=False),
    Column("person_id", PGUUID(as_uuid=False), nullable=False),
    Column("role", String(32), nullable=False),
    Column("status", String(16), nullable=False),
)
Table(
    "growth_intents",
    metadata,
    Column("intent_id", PGUUID(as_uuid=False), primary_key=True),
    Column("family_id", PGUUID(as_uuid=False), nullable=False),
    Column("subject_person_id", PGUUID(as_uuid=False), nullable=False),
    Column("need_type", String(64), nullable=False),
    Column("goal_text", String(1000), nullable=False),
    Column("required_capability_keys", ARRAY(String), nullable=False),
    Column("status", String(24), nullable=False),
    Column("confirmed_by", PGUUID(as_uuid=False), nullable=False),
    Column("confirmed_at", DateTime(timezone=True), nullable=False),
    Column("boundary", String(96), nullable=False),
)
Table(
    "consents",
    metadata,
    Column("consent_id", PGUUID(as_uuid=False), primary_key=True),
    Column("family_id", PGUUID(as_uuid=False), nullable=False),
    Column("subject_person_id", PGUUID(as_uuid=False), nullable=False),
    Column("purpose", String(48), nullable=False),
    Column("status", String(24), nullable=False),
    Column("granted_at", DateTime(timezone=True), nullable=False),
    Column("withdrawn_at", DateTime(timezone=True)),
)
Table(
    "growth_journeys",
    metadata,
    Column("journey_id", PGUUID(as_uuid=False), primary_key=True),
    Column("family_id", PGUUID(as_uuid=False), nullable=False),
    Column("journey_type", String(64), nullable=False),
    Column("phase", String(32), nullable=False),
    Column("status", String(16), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False),
)
Table(
    "growth_onboarding_intent_bindings",
    metadata,
    Column(
        "binding_id",
        PGUUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("tenant_family_binding_id", PGUUID(as_uuid=False), nullable=False),
    Column("tenant_id", PGUUID(as_uuid=False), nullable=False),
    Column("family_id", PGUUID(as_uuid=False), nullable=False),
    Column("intent_id", PGUUID(as_uuid=False), nullable=False),
    Column("onboarding_id", PGUUID(as_uuid=False), nullable=False),
    Column("subject_person_id", PGUUID(as_uuid=False), nullable=False),
    Column("created_at", DateTime(timezone=True)),
    UniqueConstraint("tenant_id", "family_id", "intent_id", name="uq_test_growth_binding_intent"),
    UniqueConstraint(
        "tenant_id", "family_id", "onboarding_id", name="uq_test_growth_binding_onboarding"
    ),
)
Table(
    "idempotency_keys",
    metadata,
    Column("idempotency_key", String(128), primary_key=True),
    Column("action_name", String(128), nullable=False),
    Column("request_hash", String(128), nullable=False),
    Column("response_code", Integer),
    Column("response_body", JSONB),
)
Table(
    "audit_logs",
    metadata,
    Column(
        "audit_id",
        PGUUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("family_id", PGUUID(as_uuid=False)),
    Column("actor_type", String(32), nullable=False),
    Column("actor_id", String(128), nullable=False),
    Column("action_name", String(128), nullable=False),
    Column("resource_type", String(64), nullable=False),
    Column("resource_id", String(128)),
    Column("correlation_id", String(128), nullable=False),
    Column("idempotency_key", String(128)),
    Column("result", String(32), nullable=False),
    Column("metadata", JSONB, nullable=False),
)
Table(
    "platform_audit_events",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("actor_id", String(128), nullable=False),
    Column("tenant_id", String(128), nullable=False),
    Column("action", String(128), nullable=False),
    Column("resource_type", String(64), nullable=False),
    Column("resource_id", String(128), nullable=False),
    Column("reason", String, nullable=False),
    Column("correlation_id", String(128), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("action_kind", String(16), nullable=False),
    Column("before", JSON, nullable=True),
    Column("after", JSON, nullable=True),
    Column("subject_person_id", String(128), nullable=True),
    Column("subject_is_minor", Boolean, nullable=False, server_default=text("false")),
    Column("accessed_fields", JSON, nullable=True),
    Column("access_purpose", String(64), nullable=True),
    Column("approval_ref", String(128), nullable=True),
)
Table(
    "outbox_events",
    metadata,
    Column(
        "outbox_id",
        PGUUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("aggregate_type", String(64), nullable=False),
    Column("aggregate_id", String(128), nullable=False),
    Column("event_name", String(128), nullable=False),
    Column("event_version", Integer, nullable=False),
    Column("event_id", PGUUID(as_uuid=False), nullable=False, unique=True),
    Column("correlation_id", String(128), nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
)


def test_postgres_adapter_uses_reader_port_and_durable_binding() -> None:
    root = Path(__file__).resolve().parents[3]
    source = (
        root / "backend/domains/journey/infrastructure/growth_onboarding_postgres.py"
    ).read_text(encoding="utf-8")
    assert "from backend.domains.assessment" not in source
    assert "growth_onboarding_intent_bindings" in source
    assert "gi.boundary=:boundary" in source
    assert "c.withdrawn_at is null" in source
    assert "c.granted_at<=CURRENT_TIMESTAMP" in source
    assert "tfb.tenant_id=cast(:tenant_id as uuid)" in source
    consent_source = source.split("class SqlAlchemyGrowthOnboardingConsent", 1)[1]
    assert "c.expires_at" not in consent_source


def _ids() -> dict[str, str]:
    return {
        "tenant": "00000000-0000-4000-8000-000000000001",
        "family": "00000000-0000-4000-8000-000000000002",
        "parent": "00000000-0000-4000-8000-000000000003",
        "child": "00000000-0000-4000-8000-000000000004",
        "binding": "00000000-0000-4000-8000-000000000005",
        "membership": "00000000-0000-4000-8000-000000000006",
        "intent": "00000000-0000-4000-8000-000000000007",
        "consent": "00000000-0000-4000-8000-000000000008",
    }


def _command(ids: dict[str, str], key: str = "postgres-start") -> StartGrowthOnboardingCommand:
    return StartGrowthOnboardingCommand(
        tenant_id=ids["tenant"],
        family_id=ids["family"],
        actor_id=ids["parent"],
        intent_id=ids["intent"],
        correlation_id=f"correlation:{key}",
        idempotency_key=key,
    )


async def _seed(connection, ids: dict[str, str], *, consent_status: str = "GRANTED") -> None:
    now = datetime.now(UTC)
    await connection.execute(
        text(
            """
            insert into tenant_family_bindings(
              tenant_family_binding_id,tenant_id,family_id,status,effective_from
            ) values (:binding,:tenant,:family,'ACTIVE',:now)
            """
        ),
        {"binding": ids["binding"], "tenant": ids["tenant"], "family": ids["family"], "now": now},
    )
    await connection.execute(
        text(
            """
            insert into family_memberships(
              membership_id,family_id,person_id,role,status
            ) values (:membership,:family,:parent,'OWNER_GUARDIAN','ACTIVE')
            """
        ),
        {"membership": ids["membership"], "family": ids["family"], "parent": ids["parent"]},
    )
    await connection.execute(
        text(
            """
            insert into growth_intents(
              intent_id,family_id,subject_person_id,need_type,goal_text,
              required_capability_keys,status,confirmed_by,confirmed_at,boundary
            ) values (
              :intent,:family,:child,'COMMUNICATION_SUPPORT',:goal,
              :capabilities,'OPEN',:parent,:now,:boundary
            )
            """
        ),
        {
            "intent": ids["intent"],
            "family": ids["family"],
            "child": ids["child"],
            "goal": "先完整听完，再确认彼此听到的内容。",
            "capabilities": ["CAP_PARENT_CHILD_COMMUNICATION"],
            "parent": ids["parent"],
            "now": now,
            "boundary": CONFIRMED_INTENT_BOUNDARY,
        },
    )
    await connection.execute(
        text(
            """
            insert into consents(
              consent_id,family_id,subject_person_id,purpose,status,granted_at
            ) values (:consent,:family,:child,'GROWTH_TRACKING',:status,:now)
            """
        ),
        {
            "consent": ids["consent"],
            "family": ids["family"],
            "child": ids["child"],
            "status": consent_status,
            "now": now,
        },
    )


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_real_postgres_creates_queryable_binding_and_replays() -> None:
    ids = _ids()
    async with postgres_schema_engine(metadata) as engine:
        async with engine.begin() as connection:
            await _seed(connection, ids)
        application = GrowthOnboardingApplication(
            PostgresGrowthOnboardingTransaction(engine)
        )

        first = await application.start(_command(ids))
        replay = await application.start(_command(ids))
        second_key = await application.start(_command(ids, "postgres-start-2"))

        assert first["event"]["event_name"] == "GrowthOnboardingStarted"
        assert replay["replayed"] is True
        assert second_key["created"] is False
        assert second_key["onboarding"]["onboarding_id"] == first["onboarding"]["onboarding_id"]
        async with engine.connect() as connection:
            assert await connection.scalar(text("select count(*) from growth_journeys")) == 1
            assert await connection.scalar(
                text("select count(*) from growth_onboarding_intent_bindings")
            ) == 1
            binding = await connection.execute(
                text(
                    "select intent_id,onboarding_id from growth_onboarding_intent_bindings"
                )
            )
            binding_row = binding.first()
            assert binding_row is not None
            assert tuple(map(str, binding_row)) == (
                ids["intent"],
                first["onboarding"]["onboarding_id"],
            )
            assert await connection.scalar(text("select count(*) from idempotency_keys")) == 2
            assert await connection.scalar(
                text("select count(*) from platform_audit_events")
            ) == 2
            audit = await connection.execute(
                text(
                    "select tenant_id,action,reason,action_kind,before,after "
                    "from platform_audit_events order by id limit 1"
                )
            )
            audit_row = audit.first()
            assert audit_row is not None
            assert str(audit_row.tenant_id) == ids["tenant"]
            assert audit_row.action == "StartGrowthOnboarding"
            assert audit_row.reason
            assert audit_row.action_kind == "mutation"
            assert audit_row.before is None
            assert audit_row.after["intent_id"] == ids["intent"]
            assert await connection.scalar(text("select count(*) from outbox_events")) == 1


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
@pytest.mark.parametrize(
    (
        "tenant_id",
        "purpose",
        "status",
        "granted_at",
        "withdrawn_at",
        "binding_window",
        "allowed",
    ),
    [
        (
            "00000000-0000-4000-8000-000000000001",
            "GROWTH_TRACKING",
            "GRANTED",
            "now",
            None,
            "active",
            True,
        ),
        (
            "00000000-0000-4000-8000-000000000099",
            "GROWTH_TRACKING",
            "GRANTED",
            "now",
            None,
            "active",
            False,
        ),
        (
            "00000000-0000-4000-8000-000000000001",
            "SERVICE",
            "GRANTED",
            "now",
            None,
            "active",
            False,
        ),
        (
            "00000000-0000-4000-8000-000000000001",
            "GROWTH_TRACKING",
            "WITHDRAWN",
            "now",
            "past",
            "active",
            False,
        ),
        (
            "00000000-0000-4000-8000-000000000001",
            "GROWTH_TRACKING",
            "EXPIRED",
            "now",
            None,
            "active",
            False,
        ),
        (
            "00000000-0000-4000-8000-000000000001",
            "GROWTH_TRACKING",
            "GRANTED",
            "future",
            None,
            "active",
            False,
        ),
        (
            "00000000-0000-4000-8000-000000000001",
            "GROWTH_TRACKING",
            "GRANTED",
            "now",
            None,
            "future",
            False,
        ),
        (
            "00000000-0000-4000-8000-000000000001",
            "GROWTH_TRACKING",
            "GRANTED",
            "now",
            None,
            "expired",
            False,
        ),
    ],
)
async def test_real_postgres_consent_scope_status_and_effective_window(
    tenant_id: str,
    purpose: str,
    status: str,
    granted_at: str,
    withdrawn_at: str | None,
    binding_window: str,
    allowed: bool,
) -> None:
    ids = _ids()
    async with postgres_schema_engine(metadata) as engine:
        now = datetime.now(UTC)
        active_at = now - timedelta(seconds=1)
        async with engine.begin() as connection:
            # Use a value just before the database clock for the active case.
            # The adapter intentionally compares against PostgreSQL's
            # CURRENT_TIMESTAMP, so using the client clock at exact equality
            # would make this test race when the client is a few microseconds
            # ahead of the database.
            binding_from = active_at
            binding_to = None
            if binding_window == "future":
                binding_from = now + timedelta(minutes=1)
            elif binding_window == "expired":
                binding_to = now - timedelta(minutes=1)
            await connection.execute(
                text(
                    """
                    insert into tenant_family_bindings(
                      tenant_family_binding_id,tenant_id,family_id,status,
                      effective_from,effective_to
                    ) values (:binding,:tenant,:family,'ACTIVE',:binding_from,:binding_to)
                    """
                ),
                {
                    "binding": ids["binding"],
                    "tenant": ids["tenant"],
                    "family": ids["family"],
                    "binding_from": binding_from,
                    "binding_to": binding_to,
                },
            )
            await connection.execute(
                text(
                    """
                    insert into consents(
                      consent_id,family_id,subject_person_id,purpose,status,
                      granted_at,withdrawn_at
                    ) values (
                      :consent,:family,:child,:purpose,:status,
                      :granted,:withdrawn
                    )
                    """
                ),
                {
                    "consent": ids["consent"],
                    "family": ids["family"],
                    "child": ids["child"],
                    "purpose": purpose,
                    "status": status,
                    "granted": active_at
                    if granted_at == "now"
                    else now + timedelta(minutes=1),
                    "withdrawn": now - timedelta(minutes=1) if withdrawn_at == "past" else None,
                },
            )
        async with engine.connect() as connection:
            consent = SqlAlchemyGrowthOnboardingConsent(connection)
            if allowed:
                await consent.assert_granted(
                    GrowthOnboardingScope(ids["tenant"], ids["family"], ids["parent"]),
                    ids["child"],
                    "GROWTH_TRACKING",
                )
            else:
                with pytest.raises(Exception, match="missing_consent"):
                    await consent.assert_granted(
                        GrowthOnboardingScope(tenant_id, ids["family"], ids["parent"]),
                        ids["child"],
                        "GROWTH_TRACKING",
                    )


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_real_postgres_audit_failure_rolls_back_all_writes() -> None:
    ids = _ids()
    async def fail_audit(*_args) -> None:
        raise RuntimeError("audit_write_failed")

    async with postgres_schema_engine(metadata) as engine:
        async with engine.begin() as connection:
            await _seed(connection, ids)
        application = GrowthOnboardingApplication(
            PostgresGrowthOnboardingTransaction(engine, audit_writer=fail_audit)
        )
        with pytest.raises(RuntimeError, match="audit_write_failed"):
            await application.start(_command(ids, "audit-failure"))
        async with engine.connect() as connection:
            for table in (
                "growth_journeys",
                "growth_onboarding_intent_bindings",
                "idempotency_keys",
                "platform_audit_events",
                "outbox_events",
            ):
                assert await connection.scalar(text(f"select count(*) from {table}")) == 0


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_real_postgres_outbox_failure_rolls_back_all_writes() -> None:
    ids = _ids()
    async def fail_outbox(*_args) -> None:
        raise RuntimeError("outbox_write_failed")

    async with postgres_schema_engine(metadata) as engine:
        async with engine.begin() as connection:
            await _seed(connection, ids)
        application = GrowthOnboardingApplication(
            PostgresGrowthOnboardingTransaction(engine, outbox_writer=fail_outbox)
        )
        with pytest.raises(RuntimeError, match="outbox_write_failed"):
            await application.start(_command(ids, "outbox-failure"))
        async with engine.connect() as connection:
            for table in (
                "growth_journeys",
                "growth_onboarding_intent_bindings",
                "idempotency_keys",
                "platform_audit_events",
                "outbox_events",
            ):
                assert await connection.scalar(text(f"select count(*) from {table}")) == 0


def test_postgres_builder_rejects_non_postgres_url() -> None:
    with pytest.raises(RuntimeError, match="production_requires_postgresql"):
        build_postgres_growth_onboarding_application("sqlite+aiosqlite:///:memory:")
