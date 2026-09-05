"""Failure taxonomy — callers never receive a raw provider exception.

Two reasons this is a closed enum rather than free-form exceptions:

1. **Fail-closed needs a decidable boundary.** Routing may only retry
   *infrastructure* failures (see `INFRA_FAILURE_KINDS`); everything else must
   surface immediately. If failures were arbitrary exception types, "is this
   retryable?" would be a guess made at each call site.
2. **A leaked provider exception is a data-leak path.** Provider SDK errors
   routinely embed the request body — which in this platform can contain family
   or minor data — in their string form. Mapping every failure to a
   `ModelGatewayError` with a message the gateway itself composed keeps request
   payloads out of logs and HTTP responses.

`POLICY_REJECTED` deserves note: it is the admission verdict, raised *before* any
network call. It is not an infrastructure failure and is never retried or routed
around — a provider that is not approved for the data class does not become
approved because another one timed out.
"""

from __future__ import annotations

from typing import Literal

FailureKind = Literal[
    "TIMEOUT",
    "NETWORK_ERROR",
    "PROVIDER_4XX",
    "PROVIDER_5XX",
    "INVALID_JSON",
    "SCHEMA_INVALID",
    "POLICY_REJECTED",
    "CREDENTIAL_MISSING",
    "CREDENTIAL_EXPIRED",
    "CREDENTIAL_REVOKED",
    "CREDENTIAL_PROVIDER_MISMATCH",
    "CREDENTIAL_UNAVAILABLE",
    "CREDENTIAL_INVALID",
    "CREDENTIAL_TIMEOUT",
    "CREDENTIAL_NETWORK_ERROR",
    "CREDENTIAL_PLATFORM_REJECTED",
    "BUDGET_REJECTED",
    "RELEASE_FENCE_REJECTED",
    "ATTEMPT_LEDGER_REJECTED",
]

INFRA_FAILURE_KINDS: frozenset[str] = frozenset({"TIMEOUT", "NETWORK_ERROR", "PROVIDER_5XX"})
"""Transient infrastructure failures — the only kinds a routing gateway may move
past. Deliberately excludes `INVALID_JSON` and `SCHEMA_INVALID`: a model that
returned unparseable output is not a broken network, and asking a second vendor
the same question until one of them answers in valid JSON is exactly the
"looks like AI output" degradation R9 forbids.
"""


class ModelGatewayError(RuntimeError):
    """The only exception type the gateway raises to its callers."""

    def __init__(
        self,
        kind: FailureKind,
        message: str,
        *,
        provider_id: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(f"[{kind}] {message}")
        self.kind = kind
        self.message = message
        self.provider_id = provider_id
        self.status_code = status_code

    @property
    def is_infrastructure_failure(self) -> bool:
        return self.kind in INFRA_FAILURE_KINDS
