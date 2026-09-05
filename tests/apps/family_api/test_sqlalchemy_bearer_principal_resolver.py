from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.apps.family_api.trusted_experience_scope import (
    AuthenticatedPrincipal,
    SqlAlchemyAuthenticatedContextScopeResolver,
    SqlAlchemyAuthenticatedEngagementReviewerResolver,
    SqlAlchemyAuthenticatedEngagementScopeResolver,
    SqlAlchemyBearerPrincipalResolver,
)
from backend.intelligence.context_engine.contracts import DataClass
from backend.intelligence.human_gate import ActorType
from backend.platform.consent.models import ConsentPurpose


class _Result:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def mappings(self) -> _Result:
        return self

    def all(self) -> list[dict[str, object]]:
        return self.rows


class _Connection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.params: dict[str, object] | None = None

    async def __aenter__(self) -> _Connection:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def execute(self, _statement: object, params: dict[str, object]) -> _Result:
        self.params = params
        return _Result(self.rows)


class _Engine:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.connection = _Connection(rows)

    def connect(self) -> _Connection:
        return self.connection


@pytest.mark.asyncio
async def test_bearer_principal_resolver_hashes_token_and_binds_family() -> None:
    engine = _Engine([{"session_id": "session-1", "account_id": "account-1"}])
    resolver = SqlAlchemyBearerPrincipalResolver(
        engine,  # type: ignore[arg-type]
        "Bearer opaque-token",
        "family-1",
    )

    principal = await resolver()

    assert principal.account_id == "account-1"
    assert principal.correlation_id == "identity-session:session-1"
    assert engine.connection.params == {
        "token_hash": hashlib.sha256(b"opaque-token").hexdigest(),
        "family_id": "family-1",
    }


@pytest.mark.asyncio
async def test_bearer_principal_resolver_fails_closed_for_missing_or_ambiguous_session() -> None:
    with pytest.raises(PermissionError, match="AUTHENTICATED_PRINCIPAL_UNAVAILABLE"):
        await SqlAlchemyBearerPrincipalResolver(
            _Engine([]),  # type: ignore[arg-type]
            None,
            "family-1",
        )()


@pytest.mark.asyncio
async def test_authenticated_engagement_scope_resolver_composes_sql_identity_and_consent() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    token = "opaque-token"
    async with engine.begin() as connection:
        await connection.execute(text("CREATE TABLE accounts (account_id TEXT, status TEXT)"))
        await connection.execute(
            text(
                "CREATE TABLE tenants (tenant_id TEXT, status TEXT, region_ref TEXT)"
            )
        )
        await connection.execute(
            text(
                "CREATE TABLE tenant_account_memberships (account_id TEXT, tenant_id TEXT, "
                "role TEXT, status TEXT, valid_from DATETIME, valid_to DATETIME)"
            )
        )
        await connection.execute(
            text(
                "CREATE TABLE tenant_family_bindings (tenant_id TEXT, family_id TEXT, "
                "status TEXT, effective_from DATETIME, effective_to DATETIME)"
            )
        )
        await connection.execute(
            text(
                "CREATE TABLE account_person_bindings "
                "(account_id TEXT, person_id TEXT, status TEXT)"
            )
        )
        await connection.execute(
            text(
                "CREATE TABLE family_memberships (membership_id TEXT, family_id TEXT, "
                "person_id TEXT, role TEXT, status TEXT)"
            )
        )
        await connection.execute(
            text(
                "CREATE TABLE identity_sessions (session_id TEXT, token_hash TEXT, "
                "person_id TEXT, family_id TEXT, account_id TEXT, account_ref TEXT, "
                "expires_at DATETIME, revoked_at DATETIME)"
            )
        )
        await connection.execute(
            text(
                "CREATE TABLE persons (person_id TEXT, family_id TEXT, birth_date DATE)"
            )
        )
        await connection.execute(
            text(
                "CREATE TABLE consents (consent_id TEXT, family_id TEXT, subject_person_id TEXT, "
                "guardian_person_id TEXT, purpose TEXT, status TEXT, policy_version TEXT, "
                "granted_at DATETIME, withdrawn_at DATETIME)"
            )
        )
        await connection.execute(
            text("INSERT INTO accounts VALUES ('account-1', 'ACTIVE')")
        )
        await connection.execute(text("INSERT INTO tenants VALUES ('tenant-1', 'ACTIVE', 'CN')"))
        await connection.execute(
            text(
                "INSERT INTO tenant_account_memberships VALUES "
                "('account-1', 'tenant-1', 'TENANT_OWNER', 'ACTIVE', CURRENT_TIMESTAMP, NULL)"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO tenant_family_bindings VALUES "
                "('tenant-1', 'family-1', 'ACTIVE', CURRENT_TIMESTAMP, NULL)"
            )
        )
        await connection.execute(
            text("INSERT INTO account_person_bindings VALUES ('account-1', 'guardian-1', 'ACTIVE')")
        )
        await connection.execute(
            text(
                "INSERT INTO family_memberships VALUES "
                "('membership-g', 'family-1', 'guardian-1', 'OWNER_GUARDIAN', 'ACTIVE')"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO family_memberships VALUES "
                "('membership-c', 'family-1', 'child-1', 'CHILD', 'ACTIVE')"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO identity_sessions VALUES "
                "('session-1', :token_hash, 'guardian-1', 'family-1', 'account-1', "
                "'account-1', '2099-01-01 00:00:00', NULL)"
            ),
            {"token_hash": hashlib.sha256(token.encode()).hexdigest()},
        )
        await connection.execute(
            text("INSERT INTO persons VALUES ('guardian-1', 'family-1', '1980-01-01')")
        )
        await connection.execute(
            text("INSERT INTO persons VALUES ('child-1', 'family-1', '2015-01-01')")
        )
        for consent_id, subject_id, guardian_id in (
            ("consent-g", "guardian-1", "guardian-1"),
            ("consent-c", "child-1", "guardian-1"),
        ):
            await connection.execute(
                text(
                    "INSERT INTO consents VALUES (:consent_id, 'family-1', :subject_id, "
                    ":guardian_id, 'AI_PERSONALIZATION', 'GRANTED', 'policy.v1', "
                    "'2026-08-01 00:00:00', NULL)"
                ),
                {
                    "consent_id": consent_id,
                    "subject_id": subject_id,
                    "guardian_id": guardian_id,
                },
            )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        scope = await SqlAlchemyAuthenticatedEngagementScopeResolver(
            engine,  # type: ignore[arg-type]
            factory,
            f"Bearer {token}",
            purpose=ConsentPurpose.AI_PERSONALIZATION,
            data_class=DataClass.MINOR_PERSONAL_DATA,
        ).resolve("family-1")
        context_scope = await SqlAlchemyAuthenticatedContextScopeResolver(
            engine,  # type: ignore[arg-type]
            factory,
            f"Bearer {token}",
            purpose=ConsentPurpose.AI_PERSONALIZATION,
            data_class=DataClass.MINOR_PERSONAL_DATA,
        ).resolve("family-1")

        async def injected_principal() -> AuthenticatedPrincipal:
            return AuthenticatedPrincipal(
                account_id="account-1",
                correlation_id="corr:injected",
                causation_id="cause:injected",
            )

        injected_scope = await SqlAlchemyAuthenticatedContextScopeResolver(
            engine,  # type: ignore[arg-type]
            factory,
            None,
            purpose=ConsentPurpose.AI_PERSONALIZATION,
            data_class=DataClass.MINOR_PERSONAL_DATA,
            principal_resolver_factory=lambda _family_id: injected_principal,
        ).resolve("family-1")
        reviewer = await SqlAlchemyAuthenticatedEngagementReviewerResolver(
            engine,  # type: ignore[arg-type]
            factory,
            f"Bearer {token}",
            "family-1",
        )(scope)
    finally:
        await engine.dispose()

    assert scope.tenant_id == "tenant-1"
    assert scope.subject_ids == ("child-1", "guardian-1")
    assert scope.consent_granted is True
    assert scope.data_class == DataClass.MINOR_PERSONAL_DATA.value
    assert context_scope.family_id == "family-1"
    assert context_scope.tenant_id == "tenant-1"
    assert context_scope.subject_ids == ("child-1", "guardian-1")
    assert context_scope.consent_granted is True
    assert injected_scope.correlation_id == "corr:injected"
    assert reviewer.actor_id == "guardian-1"
    assert reviewer.actor_type is ActorType.GUARDIAN
    with pytest.raises(PermissionError, match="AUTHENTICATED_PRINCIPAL_UNAVAILABLE"):
        await SqlAlchemyBearerPrincipalResolver(
            _Engine(
                [
                    {"session_id": "session-1", "account_id": "account-1"},
                    {"session_id": "session-2", "account_id": "account-1"},
                ]
            ),  # type: ignore[arg-type]
            "Bearer opaque-token",
            "family-1",
        )()
