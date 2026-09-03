"""InMemoryIdempotencyStore.check_and_reserve semantics.

`IdempotencyKey` is tenant-scoped (`docs/06_platform/IDEMPOTENCY.md` §3 gap 6).
The cross-tenant tests below are the ones that bite: with a global keyspace,
tenant B's *first* use of a value tenant A already used returned False, which
callers are contractually required to read as "already happened, skip the side
effect" — a silently dropped command plus a signal derived entirely from another
tenant's activity.
"""

from __future__ import annotations

import pytest

from backend.platform.idempotency.keys import IdempotencyKey, InMemoryIdempotencyStore


def _key(value: str, tenant_id: str = "tenant-1") -> IdempotencyKey:
    return IdempotencyKey(tenant_id=tenant_id, value=value)


def test_first_reservation_of_a_key_succeeds() -> None:
    store = InMemoryIdempotencyStore()

    assert store.check_and_reserve(_key("op-1")) is True


def test_second_reservation_of_the_same_key_is_rejected() -> None:
    store = InMemoryIdempotencyStore()
    key = _key("op-1")

    assert store.check_and_reserve(key) is True
    assert store.check_and_reserve(key) is False


def test_different_keys_are_independent() -> None:
    store = InMemoryIdempotencyStore()

    assert store.check_and_reserve(_key("op-1")) is True
    assert store.check_and_reserve(_key("op-2")) is True


def test_same_value_in_two_tenants_are_two_independent_reservations() -> None:
    """The defect this scoping exists for.

    Client-chosen keys collide across tenants as a matter of course. Tenant B's
    first attempt must be a first attempt.
    """
    store = InMemoryIdempotencyStore()

    assert store.check_and_reserve(_key("sub-001", tenant_id="tenant-a")) is True
    assert store.check_and_reserve(_key("sub-001", tenant_id="tenant-b")) is True


def test_replay_is_still_detected_within_a_tenant_after_scoping() -> None:
    """Scoping must not have bought isolation by disabling replay detection."""
    store = InMemoryIdempotencyStore()

    assert store.check_and_reserve(_key("sub-001", tenant_id="tenant-a")) is True
    assert store.check_and_reserve(_key("sub-001", tenant_id="tenant-b")) is True
    assert store.check_and_reserve(_key("sub-001", tenant_id="tenant-a")) is False
    assert store.check_and_reserve(_key("sub-001", tenant_id="tenant-b")) is False


def test_tenant_and_value_boundary_cannot_be_confused_by_a_separator() -> None:
    """`(tenant="a", value="b:c")` must not collide with `(tenant="a:b", value="c")`.

    A naive `f"{tenant_id}:{value}"` makes these identical and reintroduces the
    cross-tenant collision. Tenant ids are opaque strings; the encoding must not
    assume they contain no separator.
    """
    store = InMemoryIdempotencyStore()

    assert store.check_and_reserve(IdempotencyKey(tenant_id="a", value="b:c")) is True
    assert store.check_and_reserve(IdempotencyKey(tenant_id="a:b", value="c")) is True


def test_idempotency_key_rejects_empty_value() -> None:
    with pytest.raises(ValueError):
        IdempotencyKey(tenant_id="tenant-1", value="")


def test_idempotency_key_rejects_empty_tenant_id() -> None:
    """No un-scoped key is constructible — the bypass is removed, not deprecated."""
    with pytest.raises(ValueError):
        IdempotencyKey(tenant_id="", value="op-1")


def test_idempotency_key_cannot_be_constructed_without_a_tenant() -> None:
    with pytest.raises(TypeError):
        IdempotencyKey("op-1")  # type: ignore[call-arg]
