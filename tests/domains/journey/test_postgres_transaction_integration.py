from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from backend.domains.journey.application.service import JourneyActor
from backend.domains.journey.domain.errors import JourneyForbiddenError
from backend.domains.journey.infrastructure.actor_resolver import (
    SqlAlchemyJourneyActorResolver,
)
from backend.domains.journey.infrastructure.transaction import JourneyTransactionRunner
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url

metadata = MetaData()

for table_name, columns in (
    (
        "accounts",
        [Column("account_id", UUID(as_uuid=False), primary_key=True), Column("status", String(16))],
    ),
    (
        "identity_sessions",
        [
            Column("session_id", UUID(as_uuid=False), primary_key=True),
            Column("token_hash", String(128), nullable=False),
            Column("account_ref", UUID(as_uuid=False)),
            Column("expires_at", DateTime(timezone=True), nullable=False),
            Column("revoked_at", DateTime(timezone=True)),
        ],
    ),
    (
        "tenant_account_memberships",
        [
            Column("tenant_membership_id", UUID(as_uuid=False), primary_key=True),
            Column("tenant_id", UUID(as_uuid=False)),
            Column("account_id", UUID(as_uuid=False)),
            Column("status", String(16)),
            Column("valid_from", DateTime(timezone=True)),
            Column("valid_to", DateTime(timezone=True)),
        ],
    ),
    (
        "tenant_family_bindings",
        [
            Column("tenant_family_binding_id", UUID(as_uuid=False), primary_key=True),
            Column("tenant_id", UUID(as_uuid=False)),
            Column("family_id", UUID(as_uuid=False)),
            Column("status", String(16)),
            Column("effective_from", DateTime(timezone=True)),
            Column("effective_to", DateTime(timezone=True)),
        ],
    ),
    (
        "account_person_bindings",
        [
            Column("binding_id", UUID(as_uuid=False), primary_key=True),
            Column("account_id", UUID(as_uuid=False)),
            Column("person_id", UUID(as_uuid=False)),
            Column("status", String(16)),
        ],
    ),
    (
        "family_memberships",
        [
            Column("membership_id", UUID(as_uuid=False), primary_key=True),
            Column("family_id", UUID(as_uuid=False)),
            Column("person_id", UUID(as_uuid=False)),
            Column("role", String(32)),
            Column("status", String(16)),
        ],
    ),
):
    Table(table_name, metadata, *columns)

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
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("family_id", String(128)),
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
    "outbox_events",
    metadata,
    Column(
        "outbox_id",
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("aggregate_type", String(64), nullable=False),
    Column("aggregate_id", String(128), nullable=False),
    Column("event_name", String(128), nullable=False),
    Column("event_version", Integer, nullable=False),
    Column("event_id", UUID(as_uuid=False), nullable=False, unique=True),
    Column("correlation_id", String(128), nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
)


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_real_postgres_replay_writes_one_audit_and_outbox_event() -> None:
    async with postgres_schema_engine(metadata) as engine:
        runner = JourneyTransactionRunner(engine)
        calls = 0

        async def operation(service):
            nonlocal calls
            calls += 1
            return {"plan": {"plan_id": "plan-1", "status": "DRAFT"}}

        arguments = {
            "actor": JourneyActor("actor-1", "family-1"),
            "action": "CreateJourneyPlan",
            "resource_type": "JourneyPlan",
            "resource_id": "plan-1",
            "event_name": "JourneyPlanCreated",
            "idempotency_key": "postgres-replay-1",
            "correlation_id": "correlation-1",
            "request_payload": {"onboarding_id": "onboarding-1"},
            "operation": operation,
        }
        first = await runner.execute(**arguments)
        replay = await runner.execute(**arguments)
        assert replay == first
        assert calls == 1

        async with engine.connect() as connection:
            assert await connection.scalar(text("select count(*) from idempotency_keys")) == 1
            assert await connection.scalar(text("select count(*) from audit_logs")) == 1
            assert await connection.scalar(text("select count(*) from outbox_events")) == 1
            stored = await connection.scalar(
                text("select response_body from idempotency_keys where idempotency_key=:key"),
                {"key": "postgres-replay-1"},
            )
            assert stored == first


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_real_postgres_exception_rolls_back_idempotency_claim() -> None:
    async with postgres_schema_engine(metadata) as engine:
        runner = JourneyTransactionRunner(engine)

        async def fail_after_claim(service):
            raise RuntimeError("domain_write_failed")

        with pytest.raises(RuntimeError, match="domain_write_failed"):
            await runner.execute(
                actor=JourneyActor("actor-1", "family-1"),
                action="CreateJourneyPlan",
                resource_type="JourneyPlan",
                resource_id="plan-failed",
                event_name="JourneyPlanCreated",
                idempotency_key="postgres-rollback-1",
                correlation_id="correlation-rollback",
                request_payload={"onboarding_id": "onboarding-1"},
                operation=fail_after_claim,
            )

        async with engine.connect() as connection:
            assert await connection.scalar(text("select count(*) from idempotency_keys")) == 0
            assert await connection.scalar(text("select count(*) from audit_logs")) == 0
            assert await connection.scalar(text("select count(*) from outbox_events")) == 0


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_real_postgres_resolves_trusted_actor_and_rejects_other_family() -> None:
    async with postgres_schema_engine(metadata) as engine:
        ids = {
            "session": "00000000-0000-4000-8000-000000000001",
            "account": "00000000-0000-4000-8000-000000000002",
            "tenant": "00000000-0000-4000-8000-000000000003",
            "family": "00000000-0000-4000-8000-000000000004",
            "other_family": "00000000-0000-4000-8000-000000000005",
            "person": "00000000-0000-4000-8000-000000000006",
            "tenant_membership": "00000000-0000-4000-8000-000000000007",
            "tenant_family": "00000000-0000-4000-8000-000000000008",
            "binding": "00000000-0000-4000-8000-000000000009",
            "family_membership": "00000000-0000-4000-8000-000000000010",
        }
        token = "real-postgres-opaque-token"
        now = datetime.now(UTC)
        async with engine.begin() as connection:
            await connection.execute(
                text("insert into accounts(account_id,status) values (:id,'ACTIVE')"),
                {"id": ids["account"]},
            )
            await connection.execute(
                text(
                    "insert into identity_sessions(session_id,token_hash,account_ref,expires_at) "
                    "values (:session,:hash,:account,:expires)"
                ),
                {
                    "session": ids["session"],
                    "hash": hashlib.sha256(token.encode()).hexdigest(),
                    "account": ids["account"],
                    "expires": now + timedelta(hours=1),
                },
            )
            await connection.execute(
                text(
                    "insert into tenant_account_memberships(" 
                    "tenant_membership_id,tenant_id,account_id,status,valid_from) "
                    "values (:id,:tenant,:account,'ACTIVE',:now)"
                ),
                {
                    "id": ids["tenant_membership"],
                    "tenant": ids["tenant"],
                    "account": ids["account"],
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "insert into tenant_family_bindings(" 
                    "tenant_family_binding_id,tenant_id,family_id,status,effective_from) "
                    "values (:id,:tenant,:family,'ACTIVE',:now)"
                ),
                {
                    "id": ids["tenant_family"],
                    "tenant": ids["tenant"],
                    "family": ids["family"],
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "insert into account_person_bindings(binding_id,account_id,person_id,status) "
                    "values (:id,:account,:person,'ACTIVE')"
                ),
                {
                    "id": ids["binding"],
                    "account": ids["account"],
                    "person": ids["person"],
                },
            )
            await connection.execute(
                text(
                    "insert into family_memberships(" 
                    "membership_id,family_id,person_id,role,status) "
                    "values (:id,:family,:person,'GUARDIAN','ACTIVE')"
                ),
                {
                    "id": ids["family_membership"],
                    "family": ids["family"],
                    "person": ids["person"],
                },
            )

        resolver = SqlAlchemyJourneyActorResolver(engine)
        actor = await resolver.resolve(f"Bearer {token}", ids["family"])
        assert actor == JourneyActor(ids["person"], ids["family"])
        with pytest.raises(JourneyForbiddenError, match="trusted_family_context_not_found"):
            await resolver.resolve(f"Bearer {token}", ids["other_family"])
