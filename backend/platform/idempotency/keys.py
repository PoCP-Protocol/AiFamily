"""Idempotency key type and store interface.

An `IdempotencyKey` is a thin wrapper, not a bare `str`, so that a caller
cannot accidentally pass a resource id or correlation id where an
idempotency key is expected without at least one explicit conversion step.

**The key is scoped to a tenant, and that is not optional.** The first version
of this module keyed reservations on the raw client-supplied string alone
(recorded as `docs/06_platform/IDEMPOTENCY.md` §3 gap 6). Idempotency keys are
chosen by clients — `"sub-001"`, `"booking-1"`, a retried mobile request's UUID
— so two tenants picking the same string is not an exotic collision, it is the
expected case for any human-readable convention. With a global keyspace the
consequences were two distinct bugs at once:

* **Correctness.** Tenant B's *first* attempt at `"sub-001"` returns False,
  which every caller is contractually required to read as "this operation
  already happened, do not repeat the side effect". Tenant B's command is
  silently dropped and nothing anywhere reports an error.
* **Leakage.** That False is a signal derived entirely from tenant A's
  activity. A tenant can probe which keys another tenant has used. Once a
  persistent store also caches responses (see §3 of the spec), the same
  keyspace hands over tenant A's response body.

So `tenant_id` is a required field, `scoped_value` is what stores key on, and
there is deliberately no constructor, classmethod, or default that produces an
un-scoped key. Removing the bypass is the fix; leaving a compatibility path
would leave the bug reachable.

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

    Both fields are required. `tenant_id` is not a convenience for logging: it
    is part of the identity of the key, because the `value` half is chosen by an
    untrusted client and therefore cannot be assumed unique across tenants.
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
        """The string a store must key on.

        The tenant id is length-prefixed rather than merely joined with a
        separator. A bare `f"{tenant_id}:{value}"` is ambiguous: tenant `"a"`
        with value `"b:c"` and tenant `"a:b"` with value `"c"` produce the same
        string, which reintroduces exactly the cross-tenant collision this
        field exists to prevent. Tenant ids are opaque strings that may contain
        any character, so the encoding must not depend on them not containing
        the separator.
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

        Reservations are per tenant. The same `value` presented by two different
        tenants is two different keys, and both first reservations return True.
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
