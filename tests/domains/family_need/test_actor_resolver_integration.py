"""Real-Postgres tests for :class:`SqlAlchemyFamilyNeedActorResolver`.

Mirrors ``tests/domains/journey/test_postgres_transaction_integration.py``'s
identity-chain test: builds the six trusted-identity tables in a disposable
schema, seeds one guardian, and checks both the happy path and the
cross-family rejection. Gated the same way (skipped without
``AIFAMILY_TEST_DATABASE_URL``); not run against a real database in this
environment because no local PostgreSQL/Docker was available — a developer
with the dev-compose Postgres running should execute it once.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Column, DateTime, MetaData, String, Table
from sqlalchemy.dialects.postgresql import UUID

from backend.domains.family_need.api.dependencies import FamilyNeedActor
from backend.domains.family_need.domain.errors import FamilyNeedForbiddenError
from backend.domains.family_need.domain.value_objects import ActorType
from backend.domains.family_need.infrastructure.actor_resolver import (
    FamilyNeedAuthenticationError,
    SqlAlchemyFamilyNeedActorResolver,
)
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


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_real_postgres_resolves_trusted_family_need_actor_and_rejects_other_family() -> None:
    from sqlalchemy import text

    async with postgres_schema_engine(metadata) as engine:
        ids = {
            "session": "00000000-0000-4000-8000-000000000101",
            "account": "00000000-0000-4000-8000-000000000102",
            "tenant": "00000000-0000-4000-8000-000000000103",
            "family": "00000000-0000-4000-8000-000000000104",
            "other_family": "00000000-0000-4000-8000-000000000105",
            "person": "00000000-0000-4000-8000-000000000106",
            "tenant_membership": "00000000-0000-4000-8000-000000000107",
            "tenant_family": "00000000-0000-4000-8000-000000000108",
            "binding": "00000000-0000-4000-8000-000000000109",
            "family_membership": "00000000-0000-4000-8000-000000000110",
        }
        token = "real-postgres-family-need-opaque-token"
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

        resolver = SqlAlchemyFamilyNeedActorResolver(engine)
        actor = await resolver.resolve(f"Bearer {token}", ids["family"])
        assert actor == FamilyNeedActor(
            tenant_id=ids["tenant"],
            family_id=ids["family"],
            actor_id=ids["person"],
            actor_type=ActorType.FAMILY_GUARDIAN,
        )
        with pytest.raises(FamilyNeedForbiddenError, match="trusted_family_context_not_found"):
            await resolver.resolve(f"Bearer {token}", ids["other_family"])


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_missing_bearer_token_raises_authentication_error() -> None:
    async with postgres_schema_engine(metadata) as engine:
        resolver = SqlAlchemyFamilyNeedActorResolver(engine)
        with pytest.raises(FamilyNeedAuthenticationError, match="authorization_required"):
            await resolver.resolve(None, "family-1")
