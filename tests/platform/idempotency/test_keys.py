"""InMemoryIdempotencyStore.check_and_reserve semantics."""

from __future__ import annotations

import pytest

from backend.platform.idempotency.keys import IdempotencyKey, InMemoryIdempotencyStore


def test_first_reservation_of_a_key_succeeds() -> None:
    store = InMemoryIdempotencyStore()
    key = IdempotencyKey("op-1")

    assert store.check_and_reserve(key) is True


def test_second_reservation_of_the_same_key_is_rejected() -> None:
    store = InMemoryIdempotencyStore()
    key = IdempotencyKey("op-1")

    assert store.check_and_reserve(key) is True
    assert store.check_and_reserve(key) is False


def test_different_keys_are_independent() -> None:
    store = InMemoryIdempotencyStore()

    assert store.check_and_reserve(IdempotencyKey("op-1")) is True
    assert store.check_and_reserve(IdempotencyKey("op-2")) is True


def test_idempotency_key_rejects_empty_value() -> None:
    with pytest.raises(ValueError):
        IdempotencyKey("")
