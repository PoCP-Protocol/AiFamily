"""Immutable contracts for the AI draft -> human decision boundary."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from backend.intelligence.human_gate.errors import HumanGateError

_NAMED_ACTION = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_GENERIC_ACTION_NAMES = frozenset({"UPDATE", "PATCH", "DELETE", "WRITE", "SET"})


class ActorType(StrEnum):
    """Actor categories understood by the gate.

    ``AI`` and ``SYSTEM`` are represented explicitly so that callers cannot
    accidentally use a service account as the human confirmation actor.
    """

    GUARDIAN = "GUARDIAN"
    PROFESSIONAL = "PROFESSIONAL"
    OPERATOR = "OPERATOR"
    AI = "AI"
    SYSTEM = "SYSTEM"


HUMAN_ACTOR_TYPES: frozenset[ActorType] = frozenset(
    {ActorType.GUARDIAN, ActorType.PROFESSIONAL, ActorType.OPERATOR}
)


class DecisionOutcome(StrEnum):
    """A human gate decision; acceptance creates a request, not a fact."""

    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"


class GateStatus(StrEnum):
    OPEN = "OPEN"
    DECIDED = "DECIDED"
    EXPIRED = "EXPIRED"


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HumanGateError("INVALID_CONTRACT", f"{field_name} is required")
    return value.strip()


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise HumanGateError("INVALID_CONTRACT", f"{field_name} must be timezone-aware")


def _validate_action_name(value: str) -> str:
    action_name = _require_text(value, "action_name")
    if action_name in _GENERIC_ACTION_NAMES or not _NAMED_ACTION.fullmatch(action_name):
        raise HumanGateError(
            "INVALID_NAMED_ACTION",
            "action_name must be an explicit uppercase Named Action, not a generic write",
        )
    return action_name


@dataclass(frozen=True, slots=True)
class GateScope:
    """The exact scope a human reviewer is allowed to decide within."""

    tenant_id: str
    family_id: str | None
    subject_ids: tuple[str, ...]
    purpose: str
    consent_version: str
    correlation_id: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.tenant_id, "tenant_id"),
            (self.purpose, "purpose"),
            (self.consent_version, "consent_version"),
            (self.correlation_id, "correlation_id"),
        ):
            _require_text(value, field_name)
        if self.family_id is not None:
            _require_text(self.family_id, "family_id")
        if any(
            not isinstance(subject_id, str) or not subject_id.strip()
            for subject_id in self.subject_ids
        ):
            raise HumanGateError("INVALID_CONTRACT", "subject_ids must contain non-empty strings")


@dataclass(frozen=True, slots=True)
class ActionProposal:
    """A human-reviewable action candidate derived from a model draft."""

    proposal_id: str
    draft_id: str
    draft_status: str
    action_name: str
    action_arguments: Mapping[str, Any]
    scope: GateScope
    allowed_actor_types: tuple[ActorType, ...]
    risk_level: str
    provenance_ref: str
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.proposal_id, "proposal_id")
        _require_text(self.draft_id, "draft_id")
        _require_text(self.draft_status, "draft_status")
        if not isinstance(self.scope, GateScope):
            raise HumanGateError("INVALID_CONTRACT", "action proposal scope is invalid")
        if self.draft_status != "DRAFT":
            raise HumanGateError("DRAFT_REQUIRED", "only a DRAFT can enter the Human Gate")
        _validate_action_name(self.action_name)
        if not isinstance(self.action_arguments, Mapping):
            raise HumanGateError("INVALID_CONTRACT", "action_arguments must be a mapping")
        object.__setattr__(self, "action_arguments", MappingProxyType(dict(self.action_arguments)))
        if not self.allowed_actor_types:
            raise HumanGateError("REVIEWER_REQUIRED", "allowed_actor_types must not be empty")
        try:
            actor_types = tuple(ActorType(actor_type) for actor_type in self.allowed_actor_types)
        except ValueError as exc:
            raise HumanGateError("INVALID_ACTOR_TYPE", "unknown reviewer actor type") from exc
        object.__setattr__(self, "allowed_actor_types", actor_types)
        if any(actor_type not in HUMAN_ACTOR_TYPES for actor_type in actor_types):
            raise HumanGateError("HUMAN_REVIEWER_REQUIRED", "AI and system actors cannot review")
        _require_text(self.risk_level, "risk_level")
        _require_text(self.provenance_ref, "provenance_ref")
        _require_aware(self.created_at, "created_at")
        _require_aware(self.expires_at, "expires_at")
        if self.expires_at <= self.created_at:
            raise HumanGateError("INVALID_EXPIRY", "expires_at must be after created_at")


@dataclass(frozen=True, slots=True)
class HumanDecision:
    """One immutable decision made by a real reviewer."""

    decision_id: str
    task_id: str
    actor_id: str
    actor_type: ActorType
    outcome: DecisionOutcome
    reason: str | None
    decided_at: datetime

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.decision_id, "decision_id"),
            (self.task_id, "task_id"),
            (self.actor_id, "actor_id"),
        ):
            _require_text(value, field_name)
        try:
            actor_type = ActorType(self.actor_type)
        except ValueError as exc:
            raise HumanGateError("INVALID_ACTOR_TYPE", "unknown deciding actor type") from exc
        object.__setattr__(self, "actor_type", actor_type)
        if actor_type not in HUMAN_ACTOR_TYPES:
            raise HumanGateError("HUMAN_REVIEWER_REQUIRED", "the deciding actor must be human")
        if self.outcome in {DecisionOutcome.REJECT, DecisionOutcome.ESCALATE} and not (
            self.reason and self.reason.strip()
        ):
            raise HumanGateError(
                "DECISION_REASON_REQUIRED", "rejection or escalation needs a reason"
            )
        _require_aware(self.decided_at, "decided_at")


@dataclass(frozen=True, slots=True)
class NamedActionRequest:
    """A request for the owning domain to execute its own Named Action.

    The request is intentionally not an entity and carries no persistence
    handle.  The domain must re-authorize, validate, transact, audit, and
    idempotently execute it.
    """

    request_id: str
    action_name: str
    action_arguments: Mapping[str, Any]
    task_id: str
    proposal_id: str
    decision_id: str
    actor_id: str
    actor_type: ActorType
    scope: GateScope
    provenance_ref: str
    idempotency_key: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.request_id, "request_id"),
            (self.task_id, "task_id"),
            (self.proposal_id, "proposal_id"),
            (self.decision_id, "decision_id"),
            (self.actor_id, "actor_id"),
            (self.provenance_ref, "provenance_ref"),
            (self.idempotency_key, "idempotency_key"),
        ):
            _require_text(value, field_name)
        if not isinstance(self.scope, GateScope):
            raise HumanGateError("INVALID_CONTRACT", "named action scope is invalid")
        _validate_action_name(self.action_name)
        if not isinstance(self.action_arguments, Mapping):
            raise HumanGateError("INVALID_CONTRACT", "action_arguments must be a mapping")
        object.__setattr__(self, "action_arguments", MappingProxyType(dict(self.action_arguments)))
        try:
            actor_type = ActorType(self.actor_type)
        except ValueError as exc:
            raise HumanGateError("INVALID_ACTOR_TYPE", "unknown action actor type") from exc
        object.__setattr__(self, "actor_type", actor_type)
        if actor_type not in HUMAN_ACTOR_TYPES:
            raise HumanGateError(
                "HUMAN_REVIEWER_REQUIRED", "a Named Action request needs a human actor"
            )


@dataclass(frozen=True, slots=True)
class HumanTask:
    """The task and its eventual decision, with a single lifecycle transition."""

    task_id: str
    proposal: ActionProposal
    status: GateStatus = GateStatus.OPEN
    decision: HumanDecision | None = None
    action_request: NamedActionRequest | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        _require_text(self.task_id, "task_id")
        _require_aware(self.created_at, "created_at")
        if self.status is GateStatus.OPEN and (
            self.decision is not None or self.action_request is not None
        ):
            raise HumanGateError("INVALID_TASK_STATE", "an OPEN task cannot have a decision")
        if self.status is GateStatus.DECIDED and self.decision is None:
            raise HumanGateError("INVALID_TASK_STATE", "a closed task must have a decision")
        if self.status is GateStatus.DECIDED and self.decision.task_id != self.task_id:
            raise HumanGateError("INVALID_TASK_STATE", "decision must reference its task")
        if self.status is GateStatus.EXPIRED and (
            self.decision is not None or self.action_request is not None
        ):
            raise HumanGateError("INVALID_TASK_STATE", "an EXPIRED task cannot have a decision")
        if (
            self.action_request is not None
            and self.decision is not None
            and self.action_request.decision_id != self.decision.decision_id
        ):
            raise HumanGateError("INVALID_TASK_STATE", "action request must reference its decision")


__all__ = [
    "ActionProposal",
    "ActorType",
    "DecisionOutcome",
    "GateScope",
    "GateStatus",
    "HUMAN_ACTOR_TYPES",
    "HumanDecision",
    "HumanTask",
    "NamedActionRequest",
]
