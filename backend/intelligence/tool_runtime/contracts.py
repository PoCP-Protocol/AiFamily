"""Provider-neutral contracts for governed AI tool calls.

Tools are deliberately narrower than agents: a tool may prepare a
human-reviewable Named Action candidate, but it can never execute that action
or write a business fact.  The owning domain and Human Gate remain the only
places that can authorize and apply a Named Action.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Literal, Protocol

from backend.intelligence.human_gate.contracts import GateScope

_ACTION_NAME = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_GENERIC_ACTIONS = frozenset({"UPDATE", "PATCH", "DELETE", "WRITE", "SET"})


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Static, reviewed upper bound for one tool."""

    tool_id: str
    name: str
    description: str
    input_schema: Mapping[str, Any]
    action_name: str
    allowed_use_cases: frozenset[str] = field(default_factory=frozenset)
    risk_level: str = "MEDIUM"

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.tool_id, "tool_id"),
            (self.name, "name"),
            (self.description, "description"),
            (self.action_name, "action_name"),
            (self.risk_level, "risk_level"),
        ):
            _text(value, field_name)
        if not _ACTION_NAME.fullmatch(self.action_name) or self.action_name in _GENERIC_ACTIONS:
            raise ValueError("action_name must be an explicit Named Action")
        if not isinstance(self.input_schema, Mapping):
            raise ValueError("input_schema must be a mapping")
        object.__setattr__(self, "input_schema", MappingProxyType(dict(self.input_schema)))

    @property
    def requires_human_confirmation(self) -> Literal[True]:
        return True

    @property
    def may_mutate_business_state(self) -> Literal[False]:
        return False


@dataclass(frozen=True, slots=True)
class ToolAuthorization:
    """Short-lived tool lease derived from an AgentAuthorization."""

    authorization_id: str
    agent_authorization_id: str
    tool_id: str
    agent_id: str
    tenant_id: str
    family_id: str
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    audit_ref: str = ""

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.authorization_id, "authorization_id"),
            (self.agent_authorization_id, "agent_authorization_id"),
            (self.tool_id, "tool_id"),
            (self.agent_id, "agent_id"),
            (self.tenant_id, "tenant_id"),
            (self.family_id, "family_id"),
            (self.audit_ref, "audit_ref"),
        ):
            _text(value, field_name)
        if self.issued_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("tool authorization timestamps must be timezone-aware")
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be after issued_at")

    def is_valid_at(self, now: datetime) -> bool:
        if now.tzinfo is None:
            return False
        return self.issued_at <= now < self.expires_at and (
            self.revoked_at is None or now < self.revoked_at
        )


@dataclass(frozen=True, slots=True)
class ToolCallRequest:
    """One scoped invocation request; no raw media or provider handle."""

    call_id: str
    agent_id: str
    tenant_id: str
    family_id: str
    use_case: str
    tool_id: str
    context_snapshot_ref: str
    provenance_ref: str
    input_payload: Mapping[str, Any]
    subject_ids: tuple[str, ...]
    estimated_steps: int = 1

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.call_id, "call_id"),
            (self.agent_id, "agent_id"),
            (self.tenant_id, "tenant_id"),
            (self.family_id, "family_id"),
            (self.use_case, "use_case"),
            (self.tool_id, "tool_id"),
            (self.context_snapshot_ref, "context_snapshot_ref"),
            (self.provenance_ref, "provenance_ref"),
        ):
            _text(value, field_name)
        if not isinstance(self.input_payload, Mapping):
            raise ValueError("input_payload must be a mapping")
        object.__setattr__(self, "input_payload", MappingProxyType(dict(self.input_payload)))
        if any(
            not isinstance(subject_id, str) or not subject_id.strip()
            for subject_id in self.subject_ids
        ):
            raise ValueError("subject_ids must contain non-empty strings")
        if self.estimated_steps < 1:
            raise ValueError("estimated_steps must be at least 1")


@dataclass(frozen=True, slots=True)
class PendingNamedAction:
    """Tool output awaiting Human Gate; it is not an accepted action request."""

    action_name: str
    action_arguments: Mapping[str, Any]
    scope: GateScope
    provenance_ref: str
    risk_level: str
    expires_at: datetime

    def __post_init__(self) -> None:
        if not _ACTION_NAME.fullmatch(self.action_name) or self.action_name in _GENERIC_ACTIONS:
            raise ValueError("action_name must be an explicit Named Action")
        if not isinstance(self.action_arguments, Mapping):
            raise ValueError("action_arguments must be a mapping")
        object.__setattr__(self, "action_arguments", MappingProxyType(dict(self.action_arguments)))
        if not isinstance(self.scope, GateScope):
            raise ValueError("scope must be a GateScope")
        for value, field_name in (
            (self.provenance_ref, "provenance_ref"),
            (self.risk_level, "risk_level"),
        ):
            _text(value, field_name)
        if self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ToolCallResult:
    """Only legal result of a tool call: a pending Human Gate candidate."""

    call_id: str
    tool_id: str
    agent_id: str
    tenant_id: str
    family_id: str
    pending_action: PendingNamedAction
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: Literal["PENDING_HUMAN_CONFIRMATION"] = "PENDING_HUMAN_CONFIRMATION"

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.call_id, "call_id"),
            (self.tool_id, "tool_id"),
            (self.agent_id, "agent_id"),
            (self.tenant_id, "tenant_id"),
            (self.family_id, "family_id"),
        ):
            _text(value, field_name)
        if not isinstance(self.pending_action, PendingNamedAction):
            raise ValueError("pending_action is required")
        if self.status != "PENDING_HUMAN_CONFIRMATION":
            raise ValueError("tool results must remain pending human confirmation")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")

    @property
    def requires_human_confirmation(self) -> Literal[True]:
        return True

    @property
    def may_mutate_business_state(self) -> Literal[False]:
        return False


class ToolExecutionPort(Protocol):
    """Adapter implemented by a tool, returning action arguments only."""

    async def prepare_named_action(
        self, definition: ToolDefinition, request: ToolCallRequest
    ) -> Mapping[str, Any]:
        ...


__all__ = [
    "PendingNamedAction",
    "ToolAuthorization",
    "ToolCallRequest",
    "ToolCallResult",
    "ToolDefinition",
    "ToolExecutionPort",
]
