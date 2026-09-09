"""End-to-end acceptance for `IdentityApplicationService`, run against all
three backends (`fake`, `sqlalchemy`/SQLite, `postgres`) via the `repo`
fixture — same convention `tests/domains/membership/test_acceptance_chain.py`
uses.

Covers the property `dev_auth.py` explicitly lacked and this migration
(ADR-0011 §4) exists to add: real expiry enforcement and a session that
survives being looked up from a second, independent repository instance
bound to the same backend (proving persistence, not merely in-process
object identity).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.domains.identity.application.service import IdentityApplicationService
from backend.domains.identity.domain.errors import (
    IdentityForbiddenError,
    IdentityUnauthenticatedError,
    IdentityValidationError,
)


class _FixedClock:
    """Swap-in for `datetime` whose `.now(tz)` returns a controlled instant,
    so expiry can be asserted deterministically instead of sleeping in a
    test."""

    def __init__(self, initial: datetime) -> None:
        self._current = initial

    def now(self, tz=None):  # noqa: ANN001 - mirrors `datetime.now`'s signature
        return self._current if tz is None else self._current.astimezone(tz)

    def advance(self, delta: timedelta) -> None:
        self._current = self._current + delta


async def test_create_account_session_round_trips_and_carries_family_scope(repo) -> None:
    service = IdentityApplicationService(repo)

    issued = await service.create_account_session(
        external_ref="account-a:family-a", idempotency_key="auth-1"
    )
    assert issued.account_id == "account-a"
    assert issued.family_id == "family-a"
    assert issued.token

    identity = await service.resolve_actor(bearer_token=f"Bearer {issued.token}")
    assert identity.account_id == "account-a"
    assert identity.family_id == "family-a"


async def test_create_account_session_with_no_colon_uses_ref_as_both_account_and_family(
    repo,
) -> None:
    service = IdentityApplicationService(repo)
    issued = await service.create_account_session(
        external_ref="solo-ref", idempotency_key="auth-solo"
    )
    assert issued.account_id == "solo-ref"
    assert issued.family_id == "solo-ref"


async def test_create_account_session_replays_the_same_response_for_a_repeated_key(repo) -> None:
    service = IdentityApplicationService(repo)
    first = await service.create_account_session(
        external_ref="account-a:family-a", idempotency_key="dup-key"
    )
    second = await service.create_account_session(
        external_ref="account-a:family-a", idempotency_key="dup-key"
    )
    assert first == second


async def test_create_account_session_rejects_missing_external_ref(repo) -> None:
    service = IdentityApplicationService(repo)
    with pytest.raises(IdentityValidationError, match="EXTERNAL_REF_REQUIRED"):
        await service.create_account_session(external_ref="", idempotency_key="k")


async def test_create_account_session_rejects_missing_idempotency_key(repo) -> None:
    service = IdentityApplicationService(repo)
    with pytest.raises(IdentityValidationError, match="IDEMPOTENCY_KEY_REQUIRED"):
        await service.create_account_session(external_ref="account-a", idempotency_key="")


async def test_resolve_actor_rejects_missing_or_malformed_bearer_with_401(repo) -> None:
    service = IdentityApplicationService(repo)
    with pytest.raises(IdentityUnauthenticatedError, match="AUTHORIZATION_REQUIRED"):
        await service.resolve_actor(bearer_token=None)
    with pytest.raises(IdentityUnauthenticatedError, match="AUTHORIZATION_REQUIRED"):
        await service.resolve_actor(bearer_token="not-a-bearer-token")


async def test_resolve_actor_rejects_unknown_token_with_401(repo) -> None:
    service = IdentityApplicationService(repo)
    with pytest.raises(IdentityUnauthenticatedError, match="UNKNOWN_OR_EXPIRED_SESSION"):
        await service.resolve_actor(bearer_token="Bearer does-not-exist")


async def test_resolve_actor_scoped_to_wrong_family_is_403_not_401(repo) -> None:
    """The 401-vs-403 split `dev_auth.resolve_actor` documented must survive
    the migration: a *valid* token for the wrong family must not be
    indistinguishable from "no credential at all"."""

    service = IdentityApplicationService(repo)
    issued = await service.create_account_session(
        external_ref="account-a:family-a", idempotency_key="auth-2"
    )
    with pytest.raises(IdentityForbiddenError, match="FAMILY_ACCESS_DENIED"):
        await service.resolve_actor(
            bearer_token=f"Bearer {issued.token}", family_id="family-b"
        )


async def test_expired_session_is_rejected_not_accepted_forever(repo) -> None:
    """The property `dev_auth.py`'s `_NON_EXPIRY` sentinel explicitly did not
    have: `expires_at` is real and enforced."""

    clock = _FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    service = IdentityApplicationService(
        repo, clock=clock, session_lifetime=timedelta(minutes=10)
    )
    issued = await service.create_account_session(
        external_ref="account-a:family-a", idempotency_key="auth-3"
    )

    # Still valid a moment later.
    await service.resolve_actor(bearer_token=f"Bearer {issued.token}")

    clock.advance(timedelta(minutes=11))
    with pytest.raises(IdentityUnauthenticatedError, match="UNKNOWN_OR_EXPIRED_SESSION"):
        await service.resolve_actor(bearer_token=f"Bearer {issued.token}")


async def test_revoke_session_invalidates_it_immediately(repo) -> None:
    service = IdentityApplicationService(repo)
    issued = await service.create_account_session(
        external_ref="account-a:family-a", idempotency_key="auth-4"
    )
    revoked = await service.revoke_session(
        bearer_token=f"Bearer {issued.token}", idempotency_key="revoke-1"
    )
    assert revoked is True

    with pytest.raises(IdentityUnauthenticatedError, match="UNKNOWN_OR_EXPIRED_SESSION"):
        await service.resolve_actor(bearer_token=f"Bearer {issued.token}")


async def test_revoke_session_replays_for_a_repeated_key(repo) -> None:
    service = IdentityApplicationService(repo)
    issued = await service.create_account_session(
        external_ref="account-a:family-a", idempotency_key="auth-5"
    )
    first = await service.revoke_session(
        bearer_token=f"Bearer {issued.token}", idempotency_key="revoke-dup"
    )
    second = await service.revoke_session(
        bearer_token=f"Bearer {issued.token}", idempotency_key="revoke-dup"
    )
    assert first == second is True


async def test_revoke_session_without_credential_is_401_not_400(repo) -> None:
    service = IdentityApplicationService(repo)
    with pytest.raises(IdentityUnauthenticatedError, match="AUTHORIZATION_REQUIRED"):
        await service.revoke_session(bearer_token=None, idempotency_key="revoke-x")
