"""Provider-neutral relay seam for accepted, run-bound Named Actions.

The relay is an outbox-consumer boundary: it only accepts an already human-
approved request, validates its ExperienceRun binding, and publishes an
idempotent envelope.  It never executes a domain command or commits a
transaction.  The in-memory implementation is for contract tests; a durable
outbox adapter can implement the same protocol later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.intelligence.human_gate.contracts import GateScope, NamedActionRequest

from .human_gate_bridge import assert_named_action_binding, experience_run_ref
from .runs import DurableExperienceRun


class NamedActionRelayError(ValueError):
    """Base error for invalid relay envelopes or idempotency conflicts."""


class RelayConflictError(NamedActionRelayError):
    """The same request id was published with different content."""


@dataclass(frozen=True, slots=True)
class RunBoundNamedActionEnvelope:
    """Immutable message sent from Human Gate to a future domain consumer."""

    request: NamedActionRequest
    run_id: str
    run_ref: str
    scope: GateScope
    provenance_ref: str

    @classmethod
    def from_run(
        cls,
        run: DurableExperienceRun,
        request: NamedActionRequest,
    ) -> RunBoundNamedActionEnvelope:
        assert_named_action_binding(run, request)
        return cls(
            request=request,
            run_id=run.run_id,
            run_ref=experience_run_ref(run),
            scope=request.scope,
            provenance_ref=request.provenance_ref,
        )

    def __post_init__(self) -> None:
        if not isinstance(self.request, NamedActionRequest):
            raise NamedActionRelayError("named action request is required")
        if not self.run_id or self.run_id != self.request.action_arguments.get("run_id"):
            raise NamedActionRelayError("run_id binding is invalid")
        expected_ref = f"experience-run:{self.scope.tenant_id}:{self.scope.family_id}:{self.run_id}"
        if self.run_ref != expected_ref:
            raise NamedActionRelayError("run_ref binding is invalid")
        if self.request.action_arguments.get("experience_run_ref") != self.run_ref:
            raise NamedActionRelayError("request lost its run_ref binding")
        if self.scope != self.request.scope:
            raise NamedActionRelayError("scope snapshot is inconsistent")
        if self.provenance_ref != self.request.provenance_ref:
            raise NamedActionRelayError("provenance snapshot is inconsistent")


@dataclass(frozen=True, slots=True)
class RelayReceipt:
    request_id: str
    replayed: bool


class NamedActionRelay(Protocol):
    async def publish(self, envelope: RunBoundNamedActionEnvelope) -> RelayReceipt: ...


class InMemoryNamedActionRelay:
    """Idempotent relay used by tests and local development."""

    def __init__(self) -> None:
        self._messages: dict[str, RunBoundNamedActionEnvelope] = {}

    async def publish(self, envelope: RunBoundNamedActionEnvelope) -> RelayReceipt:
        if not isinstance(envelope, RunBoundNamedActionEnvelope):
            raise NamedActionRelayError("relay envelope is required")
        request_id = envelope.request.request_id
        existing = self._messages.get(request_id)
        if existing is not None:
            if existing != envelope:
                raise RelayConflictError("named action replay content differs")
            return RelayReceipt(request_id=request_id, replayed=True)
        self._messages[request_id] = envelope
        return RelayReceipt(request_id=request_id, replayed=False)


__all__ = [
    "InMemoryNamedActionRelay",
    "NamedActionRelay",
    "NamedActionRelayError",
    "RelayConflictError",
    "RelayReceipt",
    "RunBoundNamedActionEnvelope",
]
