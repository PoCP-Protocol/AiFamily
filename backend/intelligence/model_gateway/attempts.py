"""Attempt ledger — one record per outbound attempt, written *before* the call.

The ordering is the entire point. If the record were written after the provider
responded, then a call that timed out, was killed, or crashed the worker would
leave no trace at all — the audit trail would contain only successes and tidy
failures, which is the shape of a trail that cannot be trusted.

So `begin()` runs first and returns a handle; `finish()` updates it. A record
stuck in `STARTED` is itself the finding: it says an outbound attempt was made and
never accounted for. The source repository reached the same conclusion in
`AttemptRecordingGateway` ("persist BEFORE external attempt → timeout 不会消失").

One deliberate asymmetry: ledger failures never block the call, and never mask a
provider failure. Losing an audit row is bad; converting a real model failure into
a ledger error — so the caller sees the wrong reason — is worse. `finish()` errors
are therefore swallowed, and `begin()` errors leave `attempt_id=None` while the
call proceeds. The provider failure is what propagates.

Storage seam: `InMemoryAttemptSink` here is complete and real for the current
runtime. Durable persistence belongs to whichever platform component owns the
audit table; this package must not reach into a domain repository to write it
(AI Runtime isolation), so it depends on the `AttemptSink` protocol only.
"""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import uuid4

from backend.intelligence.model_gateway.contracts import TokenUsage

AttemptStatus = Literal["STARTED", "SUCCESS", "FAILURE"]


@dataclass(frozen=True, slots=True)
class AttemptOutcome:
    """How an attempt ended. `failure_kind` mirrors `errors.FailureKind`."""

    status: AttemptStatus
    latency_ms: int
    failure_kind: str | None = None
    model: str | None = None
    model_version: str | None = None
    token_usage: TokenUsage | None = None
    tenant_id: str | None = None
    family_id: str | None = None


@dataclass(slots=True)
class AttemptRecord:
    """A single ledger row.

    `data_class` is recorded because "which data class went to which provider,
    when" is the question a 第16条 delegated-processing audit asks, and it cannot
    be reconstructed afterwards from a provider's own logs.
    """

    attempt_id: str
    provider_id: str
    use_case: str
    data_class: str
    environment: str
    route_sequence: int
    status: AttemptStatus
    started_at: datetime
    request_id: str | None = None
    session_id: str | None = None
    finished_at: datetime | None = None
    latency_ms: int | None = None
    failure_kind: str | None = None
    model: str | None = None
    model_version: str | None = None
    token_usage: TokenUsage | None = None
    tenant_id: str | None = None
    family_id: str | None = None
    release_set_id: str | None = None
    bundle_id: str | None = None
    deployment_receipt_id: str | None = None
    deployment_sequence: int | None = None
    runtime_config_digest: str | None = None
    control_id: str | None = None

    @property
    def is_unaccounted(self) -> bool:
        """`True` while the attempt has no recorded outcome.

        Surfaced as a property so an operator can query "what did we send that we
        never got an answer about" without knowing the status vocabulary.
        """
        return self.status == "STARTED"


class AttemptSink(Protocol):
    """Where attempt records go. Implementations must not raise into the caller."""

    def begin(
        self,
        *,
        provider_id: str,
        use_case: str,
        data_class: str,
        environment: str,
        route_sequence: int,
        request_id: str | None,
        session_id: str | None,
        tenant_id: str | None = None,
        family_id: str | None = None,
        release_set_id: str | None = None,
        bundle_id: str | None = None,
        deployment_receipt_id: str | None = None,
        deployment_sequence: int | None = None,
        runtime_config_digest: str | None = None,
        control_id: str | None = None,
    ) -> str | None | Awaitable[str | None]:
        """Record STARTED and return its handle.

        Async durable sinks may return an awaitable; the gateway awaits it while
        preserving synchronous in-memory implementations for tests.
        """
        ...

    def finish(
        self, attempt_id: str | None, outcome: AttemptOutcome
    ) -> None | Awaitable[None]:
        """Close out an attempt; a `None` handle is a no-op."""
        ...


class InMemoryAttemptSink:
    """Process-local ledger — real, queryable, and not durable.

    Named for what it is. The gateway does not depend on durability, so this is a
    complete implementation of the contract rather than a stub: nothing here
    raises `NotImplementedError`, and the tests assert against its contents.
    """

    def __init__(self) -> None:
        self._records: dict[str, AttemptRecord] = {}
        self._order: list[str] = []

    def begin(
        self,
        *,
        provider_id: str,
        use_case: str,
        data_class: str,
        environment: str,
        route_sequence: int,
        request_id: str | None,
        session_id: str | None,
        tenant_id: str | None = None,
        family_id: str | None = None,
        release_set_id: str | None = None,
        bundle_id: str | None = None,
        deployment_receipt_id: str | None = None,
        deployment_sequence: int | None = None,
        runtime_config_digest: str | None = None,
        control_id: str | None = None,
    ) -> str | None:
        attempt_id = str(uuid4())
        self._records[attempt_id] = AttemptRecord(
            attempt_id=attempt_id,
            provider_id=provider_id,
            use_case=use_case,
            data_class=data_class,
            environment=environment,
            route_sequence=route_sequence,
            status="STARTED",
            started_at=datetime.now(UTC),
            request_id=request_id,
            session_id=session_id,
            tenant_id=tenant_id,
            family_id=family_id,
            release_set_id=release_set_id,
            bundle_id=bundle_id,
            deployment_receipt_id=deployment_receipt_id,
            deployment_sequence=deployment_sequence,
            runtime_config_digest=runtime_config_digest,
            control_id=control_id,
        )
        self._order.append(attempt_id)
        return attempt_id

    def finish(self, attempt_id: str | None, outcome: AttemptOutcome) -> None:
        if attempt_id is None:
            return
        record = self._records.get(attempt_id)
        if record is None:
            return
        record.status = outcome.status
        record.finished_at = datetime.now(UTC)
        record.latency_ms = outcome.latency_ms
        record.failure_kind = outcome.failure_kind
        record.model = outcome.model
        record.model_version = outcome.model_version
        record.token_usage = outcome.token_usage

    def all_attempts(self) -> tuple[AttemptRecord, ...]:
        return tuple(self._records[key] for key in self._order)

    def unaccounted_attempts(self) -> tuple[AttemptRecord, ...]:
        return tuple(r for r in self.all_attempts() if r.is_unaccounted)


class NullAttemptSink:
    """Discards everything.

    Exists so that "no ledger" is a named, visible choice at the construction site
    rather than an `attempt_sink=None` default that reads like an oversight. The
    gateway's own default is `InMemoryAttemptSink`, so recording is opt-out, not
    opt-in.
    """

    def begin(
        self,
        *,
        provider_id: str,
        use_case: str,
        data_class: str,
        environment: str,
        route_sequence: int,
        request_id: str | None,
        session_id: str | None,
        tenant_id: str | None = None,
        family_id: str | None = None,
        release_set_id: str | None = None,
        bundle_id: str | None = None,
        deployment_receipt_id: str | None = None,
        deployment_sequence: int | None = None,
        runtime_config_digest: str | None = None,
        control_id: str | None = None,
    ) -> str | None:
        return None

    def finish(self, attempt_id: str | None, outcome: AttemptOutcome) -> None:
        return None
