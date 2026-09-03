"""Fail-closed authorization for Agent Runtime executions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from backend.intelligence.agent_runtime.contracts import (
    AgentAuthorization,
    AgentDefinition,
    AgentTask,
)


class AgentAuthorizationError(PermissionError):
    """Raised when an agent request does not satisfy its authorization lease."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class AgentAuthorizationDecision:
    allowed: bool
    reason: str


class AgentAuthorizer:
    """Evaluate static definition + dynamic lease with deny-by-default rules."""

    def authorize(
        self,
        definition: AgentDefinition | None,
        authorization: AgentAuthorization | None,
        task: AgentTask,
        *,
        now: datetime | None = None,
    ) -> AgentAuthorizationDecision:
        instant = now if now is not None else datetime.now(UTC)
        if definition is None:
            return AgentAuthorizationDecision(False, "agent_definition_missing")
        if authorization is None:
            return AgentAuthorizationDecision(False, "agent_authorization_missing")
        if task.agent_id != definition.agent_id or authorization.agent_id != definition.agent_id:
            return AgentAuthorizationDecision(False, "agent_id_mismatch")
        if task.tenant_id != authorization.tenant_id or task.family_id != authorization.family_id:
            return AgentAuthorizationDecision(False, "scope_mismatch")
        if not authorization.is_valid_at(instant):
            return AgentAuthorizationDecision(False, "authorization_expired_or_revoked")
        if task.use_case not in definition.allowed_use_cases:
            return AgentAuthorizationDecision(False, "use_case_not_in_definition")
        if task.use_case not in authorization.allowed_use_cases:
            return AgentAuthorizationDecision(False, "use_case_not_authorized")
        if not task.requested_tools.issubset(definition.allowed_tools):
            return AgentAuthorizationDecision(False, "tool_not_in_definition")
        if not task.requested_tools.issubset(authorization.allowed_tools):
            return AgentAuthorizationDecision(False, "tool_not_authorized")
        if task.estimated_steps > authorization.budget.max_steps:
            return AgentAuthorizationDecision(False, "budget_exceeded")
        return AgentAuthorizationDecision(True, "authorized")

    def require(
        self,
        definition: AgentDefinition | None,
        authorization: AgentAuthorization | None,
        task: AgentTask,
        *,
        now: datetime | None = None,
    ) -> None:
        decision = self.authorize(definition, authorization, task, now=now)
        if not decision.allowed:
            raise AgentAuthorizationError("AUTHORIZATION_DENIED", decision.reason)

