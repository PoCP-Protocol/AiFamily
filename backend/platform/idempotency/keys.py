"""Idempotency key type and store interface.

An `IdempotencyKey` is a thin wrapper, not a bare `str`, so that a caller
cannot accidentally pass a resource id or correlation id where an
idempotency key is expected without at least one explicit conversion step.

`IdempotencyStore` is an interface: `check_and_reserve` must be atomic from
the caller's point of view — the first caller to present a given key gets
True (reserved), every subsequent caller with the same key gets False
(already reserved), until the concrete implementation's retention policy
expires it (not modeled yet in Wave 1). `InMemoryIdempotencyStore` is the
test/dev implementation; a Postgres-backed implementation (e.g. a unique
constraint on the key column) is deferred to the domain that first needs
durable idempotency across process restarts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IdempotencyKey:
    """A typed wrapper around the raw idempotency key string."""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("IdempotencyKey.value must not be empty")


class IdempotencyStore(ABC):
    """Interface for idempotency key reservation."""

    @abstractmethod
    def check_and_reserve(self, key: IdempotencyKey) -> bool:
        """Reserve `key`. Return True if this is the first reservation.

        Returns False if `key` was already reserved by an earlier call —
        callers must treat False as "this operation already happened,
        do not repeat the side effect."
        """
        ...


class InMemoryIdempotencyStore(IdempotencyStore):
    """Dict-backed idempotency store for tests and single-process dev use."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def check_and_reserve(self, key: IdempotencyKey) -> bool:
        if key.value in self._seen:
            return False
        self._seen.add(key.value)
        return True
