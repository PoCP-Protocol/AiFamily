from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

from backend.domains.journey.domain.errors import JourneyForbiddenError
from backend.domains.journey.infrastructure.actor_resolver import (
    JourneyAuthenticationError,
    SqlAlchemyJourneyActorResolver,
)


class Result:
    def __init__(self, row=None):
        self.row = row

    def first(self):
        return self.row


class Connection:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    async def execute(self, statement, parameters):
        self.calls.append((str(statement), parameters))
        return self.results.pop(0)


class Context:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, tb):
        return None


class Engine:
    def __init__(self, connection):
        self.connection = connection

    def connect(self):
        return Context(self.connection)


async def test_resolves_only_through_account_tenant_family_person_chain() -> None:
    connection = Connection(
        [
            Result(SimpleNamespace(session_id="session-1", account_ref="account-1")),
            Result(
                SimpleNamespace(
                    tenant_id="tenant-1",
                    person_id="person-1",
                    membership_id="membership-1",
                    role="GUARDIAN",
                )
            ),
        ]
    )
    resolver = SqlAlchemyJourneyActorResolver(Engine(connection))  # type: ignore[arg-type]
    actor = await resolver.resolve("Bearer secret-token", "family-1")
    assert actor.actor_id == "person-1"
    assert actor.family_id == "family-1"
    assert connection.calls[0][1]["token_hash"] == hashlib.sha256(
        b"secret-token"
    ).hexdigest()
    chain_sql = connection.calls[1][0]
    for table in (
        "accounts",
        "tenant_account_memberships",
        "tenant_family_bindings",
        "account_person_bindings",
        "family_memberships",
    ):
        assert table in chain_sql


@pytest.mark.parametrize("authorization", [None, "", "Basic abc", "Bearer "])
async def test_rejects_missing_or_malformed_bearer_token(authorization) -> None:
    resolver = SqlAlchemyJourneyActorResolver(Engine(Connection([])))  # type: ignore[arg-type]
    with pytest.raises(JourneyAuthenticationError, match="authorization_required"):
        await resolver.resolve(authorization, "family-1")


async def test_rejects_expired_revoked_or_legacy_untrusted_session() -> None:
    resolver = SqlAlchemyJourneyActorResolver(
        Engine(Connection([Result()]))  # type: ignore[arg-type]
    )
    with pytest.raises(
        JourneyAuthenticationError, match="invalid_or_expired_identity_session"
    ):
        await resolver.resolve("Bearer expired", "family-1")


async def test_valid_session_without_requested_family_context_is_forbidden() -> None:
    resolver = SqlAlchemyJourneyActorResolver(
        Engine(
            Connection(
                [
                    Result(SimpleNamespace(session_id="session-1", account_ref="account-1")),
                    Result(),
                ]
            )
        )  # type: ignore[arg-type]
    )
    with pytest.raises(JourneyForbiddenError, match="trusted_family_context_not_found"):
        await resolver.resolve("Bearer valid-other-family", "family-1")
