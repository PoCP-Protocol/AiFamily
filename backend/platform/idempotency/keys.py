"""Idempotency key type and store interface.

An `IdempotencyKey` is a thin wrapper, not a bare `str`, so that a caller
cannot accidentally pass a resource id or correlation id where an
idempotency key is expected without at least one explicit conversion step.

**The key is scoped to a tenant, and that is not optional.** The first version
of this module keyed reservations on the raw client-supplied string alone.
That allowed two tenants using the same client key to collide and made the
reservation result a cross-tenant signal. `tenant_id` is therefore part of the
key identity, not merely logging metadata.

`IdempotencyStore` is an interface: `check_and_reserve` must be atomic from
the caller's point of view — the first caller to present a given key gets
True (reserved), every subsequent caller with the same key gets False
(already reserved), until the concrete implementation's retention policy
expires it (not modeled yet in Wave 1). `InMemoryIdempotencyStore` is the
test/dev implementation; a Postgres-backed implementation (e.g. a unique
constraint on the key column) is deferred to the domain that first needs
durable idempotency across process restarts — that constraint must be on
`(tenant_id, value)`, not on `value`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IdempotencyKey:
    """A tenant-scoped idempotency key.

    Both fields are required. The client-selected value is not assumed to be
    globally unique, so tenant scope is part of the identity of the key.
    """

    tenant_id: str
    value: str

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("IdempotencyKey.tenant_id must not be empty")
        if not self.value:
            raise ValueError("IdempotencyKey.value must not be empty")

    @property
    def scoped_value(self) -> str:
        """Return an unambiguous string representation for string-keyed stores.

        Length-prefixing avoids collisions such as ``("a", "b:c")`` versus
        ``("a:b", "c")`` that a naive separator join would create.
        """
        return f"{len(self.tenant_id)}:{self.tenant_id}:{self.value}"


class IdempotencyStore(ABC):
    """Interface for idempotency key reservation."""

    @abstractmethod
    def check_and_reserve(self, key: IdempotencyKey) -> bool:
        """Reserve `key`. Return True if this is the first reservation.

        Returns False if `key` was already reserved by an earlier call —
        callers must treat False as "this operation already happened,
        do not repeat the side effect."

        Reservations are per tenant. The same `value` presented by two
        different tenants is two different keys.
        """
        ...


class InMemoryIdempotencyStore(IdempotencyStore):
    """Dict-backed idempotency store for tests and single-process dev use."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def check_and_reserve(self, key: IdempotencyKey) -> bool:
        if key.scoped_value in self._seen:
            return False
        self._seen.add(key.scoped_value)
        return True
