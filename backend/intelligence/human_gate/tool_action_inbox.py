"""Human Gate inbox adapter for pending Named Actions.

The Tool Runtime intentionally stops at ``PENDING_HUMAN_CONFIRMATION``.  This
adapter is the next, still non-mutating boundary: it converts a durable
``StoredToolActionMessage`` into the immutable ``ActionProposal`` consumed by
the SQL Human Gate.  It never executes a domain command and leaves transaction
commit/rollback to the composition root.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from hashlib import sha256
from typing import TYPE_CHECKING, Protocol

from backend.platform.audit import AuditRecorder

from .contracts import ActionProposal, ActorType, GateScope, HumanTask
from .errors import HumanGateError

if TYPE_CHECKING:
    from backend.intelligence.tool_runtime.action_outbox import StoredToolActionMessage

_PENDING_STATUS = "PENDING_HUMAN_CONFIRMATION"
_DEFAULT_ACTOR_TYPES = (ActorType.GUARDIAN,)


class HumanGateSubmitPort(Protocol):
    """Small port implemented by ``SqlAlchemyHumanGate`` (or a test double)."""

    async def submit(
        self,
        proposal: ActionProposal,
        *,
        recorder: AuditRecorder,
        task_id: str | None = None,
    ) -> HumanTask: ...


def _stable_id(prefix: str, tenant_id: str, call_id: str) -> str:
    """Generate bounded ids while remaining stable across message retries."""

    digest = sha256(f"{tenant_id}:{call_id}".encode()).hexdigest()[:48]
    return f"{prefix}:{digest}"


def _invalid(detail: str) -> HumanGateError:
    return HumanGateError("INVALID_TOOL_ACTION_MESSAGE", detail)


class ToolActionHumanGateInbox:
    """Deliver pending Tool Action outbox messages into the Human Gate.

    Idempotency is delegated to ``SqlAlchemyHumanGate.submit`` using a stable
    proposal id derived from ``tenant_id + call_id``.  A replay with changed
    action content therefore fails with ``PROPOSAL_REPLAY_MISMATCH`` instead of
    opening a second task.
    """

    def __init__(
        self,
        gate: HumanGateSubmitPort,
        *,
        allowed_actor_types: tuple[ActorType, ...] = _DEFAULT_ACTOR_TYPES,
    ) -> None:
        if not allowed_actor_types:
            raise HumanGateError("REVIEWER_REQUIRED", "allowed_actor_types must not be empty")
        self._gate = gate
        self._allowed_actor_types = tuple(allowed_actor_types)

    async def deliver(
        self,
        message: StoredToolActionMessage,
        *,
        recorder: AuditRecorder,
        now: datetime | None = None,
    ) -> HumanTask:
        """Create (or replay) one OPEN HumanTask from a pending message."""

        self._validate_message(message)
        current = now or datetime.now(UTC)
        if current.tzinfo is None or current.utcoffset() is None:
            raise _invalid("now must be timezone-aware")
        if message.expires_at <= current:
            raise HumanGateError(
                "TOOL_ACTION_EXPIRED", "pending action expired before inbox delivery"
            )

        proposal = ActionProposal(
            proposal_id=_stable_id("tool-action-proposal", message.tenant_id, message.call_id),
            draft_id=_stable_id("tool-action-draft", message.tenant_id, message.call_id),
            draft_status="DRAFT",
            action_name=message.action_name,
            action_arguments=message.action_arguments,
            scope=message.scope,
            allowed_actor_types=self._allowed_actor_types,
            risk_level=message.risk_level,
            provenance_ref=message.provenance_ref,
            created_at=message.created_at,
            expires_at=message.expires_at,
        )
        return await self._gate.submit(proposal, recorder=recorder)

    @staticmethod
    def _validate_message(message: StoredToolActionMessage) -> None:
        # Import lazily: tool_runtime.action_outbox itself depends on the
        # lightweight human_gate.contracts module, and package-level exports
        # must not create a circular import during application startup.
        from backend.intelligence.tool_runtime.action_outbox import StoredToolActionMessage

        if not isinstance(message, StoredToolActionMessage):
            raise _invalid("message must be a StoredToolActionMessage")
        if message.status != _PENDING_STATUS:
            raise _invalid("message must remain pending human confirmation")
        if not isinstance(message.scope, GateScope):
            raise _invalid("scope must be a GateScope")
        if not isinstance(message.action_arguments, Mapping):
            raise _invalid("action_arguments must be a mapping")
        if message.scope.tenant_id != message.tenant_id:
            raise _invalid("scope tenant does not match message tenant")
        if message.scope.family_id != message.family_id:
            raise _invalid("scope family does not match message family")
        if message.scope.purpose != message.use_case:
            raise _invalid("scope purpose does not match message use_case")
        if message.created_at.tzinfo is None or message.created_at.utcoffset() is None:
            raise _invalid("created_at must be timezone-aware")
        if message.expires_at.tzinfo is None or message.expires_at.utcoffset() is None:
            raise _invalid("expires_at must be timezone-aware")
        payload = message.payload
        if not isinstance(payload, Mapping):
            raise _invalid("payload must be a mapping")
        for key in (
            "event_type",
            "message_id",
            "call_id",
            "tenant_id",
            "family_id",
            "action_name",
            "status",
            "schema_version",
        ):
            if payload.get(key) != getattr(message, key):
                raise _invalid(f"payload {key} does not match message")
        if payload.get("event_type") != "tool.named_action.pending":
            raise _invalid("unsupported outbox event type")
        if payload.get("action_arguments") != dict(message.action_arguments):
            raise _invalid("payload action_arguments do not match message")
        expected_scope = {
            "tenant_id": message.scope.tenant_id,
            "family_id": message.scope.family_id,
            "subject_ids": list(message.scope.subject_ids),
            "purpose": message.scope.purpose,
            "consent_version": message.scope.consent_version,
            "correlation_id": message.scope.correlation_id,
        }
        if payload.get("scope") != expected_scope:
            raise _invalid("payload scope does not match message")


__all__ = ["HumanGateSubmitPort", "ToolActionHumanGateInbox"]
