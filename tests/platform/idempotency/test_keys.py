"""InMemoryIdempotencyStore.check_and_reserve semantics."""

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
    store = InMemoryIdempotencyStore()

    assert store.check_and_reserve(_key("sub-001", tenant_id="tenant-a")) is True
    assert store.check_and_reserve(_key("sub-001", tenant_id="tenant-b")) is True


def test_replay_is_detected_only_within_the_same_tenant() -> None:
    store = InMemoryIdempotencyStore()

    assert store.check_and_reserve(_key("sub-001", tenant_id="tenant-a")) is True
    assert store.check_and_reserve(_key("sub-001", tenant_id="tenant-b")) is True
    assert store.check_and_reserve(_key("sub-001", tenant_id="tenant-a")) is False
    assert store.check_and_reserve(_key("sub-001", tenant_id="tenant-b")) is False


def test_serialization_cannot_confuse_tenant_and_value_boundaries() -> None:
    store = InMemoryIdempotencyStore()

    assert store.check_and_reserve(IdempotencyKey(tenant_id="a", value="b:c")) is True
    assert store.check_and_reserve(IdempotencyKey(tenant_id="a:b", value="c")) is True


def test_scoped_value_is_canonical_for_the_same_tenant_and_value() -> None:
    assert _key("op-1", tenant_id="tenant-a").scoped_value == "8:tenant-a:op-1"


def test_idempotency_key_rejects_empty_value() -> None:
    with pytest.raises(ValueError):
        IdempotencyKey(tenant_id="tenant-1", value="")


def test_idempotency_key_rejects_empty_tenant_id() -> None:
    with pytest.raises(ValueError):
        IdempotencyKey(tenant_id="", value="op-1")


def test_idempotency_key_cannot_be_constructed_without_a_tenant() -> None:
    with pytest.raises(TypeError):
        IdempotencyKey("op-1")  # type: ignore[call-arg]
