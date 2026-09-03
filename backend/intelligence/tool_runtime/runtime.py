"""Fail-closed Tool Runtime orchestration."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta

from backend.intelligence.agent_runtime.authorization import AgentAuthorizer
from backend.intelligence.agent_runtime.contracts import (
    AgentAuthorization,
    AgentDefinition,
    AgentTask,
)
from backend.intelligence.tool_runtime.contracts import (
    PendingNamedAction,
    ToolAuthorization,
    ToolCallRequest,
    ToolCallResult,
    ToolDefinition,
    ToolExecutionPort,
)


class ToolRuntimeError(PermissionError):
    """Raised when a tool call is not authorized or violates the seam."""

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(f"[{code}] {message or code}")
        self.code = code


class ToolRuntime:
    """Run tools through AgentAuthorization and return pending actions only."""

    def __init__(
        self,
        execution_port: ToolExecutionPort,
        definitions: Iterable[ToolDefinition] = (),
        *,
        agent_definitions: Iterable[AgentDefinition] = (),
        agent_authorizer: AgentAuthorizer | None = None,
        clock: Callable[[], datetime] | None = None,
        action_ttl: timedelta = timedelta(minutes=15),
    ) -> None:
        self._execution_port = execution_port
        self._definitions = {item.tool_id: item for item in definitions}
        self._agent_definitions = {item.agent_id: item for item in agent_definitions}
        self._agent_authorizer = agent_authorizer or AgentAuthorizer()
        self._clock = clock or (lambda: datetime.now(UTC))
        if action_ttl <= timedelta(0):
            raise ValueError("action_ttl must be positive")
        self._action_ttl = action_ttl

    def register(self, definition: ToolDefinition) -> None:
        if definition.tool_id in self._definitions:
            raise ValueError(f"tool definition already registered: {definition.tool_id}")
        self._definitions[definition.tool_id] = definition

    def register_agent(self, definition: AgentDefinition) -> None:
        if definition.agent_id in self._agent_definitions:
            raise ValueError(f"agent definition already registered: {definition.agent_id}")
        self._agent_definitions[definition.agent_id] = definition

    async def execute(
        self,
        request: ToolCallRequest,
        agent_authorization: AgentAuthorization | None,
        tool_authorization: ToolAuthorization | None,
    ) -> ToolCallResult:
        definition = self._definitions.get(request.tool_id)
        agent_definition = self._agent_definitions.get(request.agent_id)
        now = self._clock()
        if definition is None:
            raise ToolRuntimeError("TOOL_DEFINITION_MISSING")
        if agent_definition is None:
            raise ToolRuntimeError("AGENT_DEFINITION_MISSING")
        if request.use_case not in definition.allowed_use_cases:
            raise ToolRuntimeError("TOOL_USE_CASE_NOT_ALLOWED")
        if tool_authorization is None:
            raise ToolRuntimeError("TOOL_AUTHORIZATION_MISSING")
        if (
            tool_authorization.tool_id != request.tool_id
            or tool_authorization.agent_id != request.agent_id
            or tool_authorization.tenant_id != request.tenant_id
            or tool_authorization.family_id != request.family_id
            or agent_authorization is None
            or tool_authorization.agent_authorization_id != agent_authorization.authorization_id
        ):
            raise ToolRuntimeError("TOOL_SCOPE_MISMATCH")
        if not tool_authorization.is_valid_at(now):
            raise ToolRuntimeError("TOOL_AUTHORIZATION_EXPIRED_OR_REVOKED")

        # Reuse the Agent Runtime's static + dynamic whitelist checks.  The
        # temporary task never reaches a model; it only carries the common
        # authorization dimensions needed by AgentAuthorizer.
        agent_task = AgentTask(
            request_id=request.call_id,
            agent_id=request.agent_id,
            tenant_id=request.tenant_id,
            family_id=request.family_id,
            use_case=request.use_case,
            context_snapshot_ref=request.context_snapshot_ref,
            prompt_version="tool-runtime",
            schema_version="tool-runtime",
            data_class="OPERATIONAL_TEXT",
            payload=dict(request.input_payload),
            output_schema={"type": "object"},
            requested_tools=frozenset({request.tool_id}),
            estimated_steps=request.estimated_steps,
        )
        try:
            self._agent_authorizer.require(
                agent_definition, agent_authorization, agent_task, now=now
            )
        except PermissionError as error:
            raise ToolRuntimeError("AGENT_AUTHORIZATION_DENIED") from error

        action_arguments = await self._execution_port.prepare_named_action(definition, request)
        if not isinstance(action_arguments, dict):
            action_arguments = dict(action_arguments)
        pending = PendingNamedAction(
            action_name=definition.action_name,
            action_arguments=action_arguments,
            scope=_scope_for_request(request),
            provenance_ref=request.provenance_ref,
            risk_level=definition.risk_level,
            expires_at=now + self._action_ttl,
        )
        return ToolCallResult(
            call_id=request.call_id,
            tool_id=request.tool_id,
            agent_id=request.agent_id,
            tenant_id=request.tenant_id,
            family_id=request.family_id,
            pending_action=pending,
            created_at=now,
        )


def _scope_for_request(request: ToolCallRequest):
    from backend.intelligence.human_gate.contracts import GateScope

    return GateScope(
        tenant_id=request.tenant_id,
        family_id=request.family_id,
        subject_ids=request.subject_ids,
        purpose=request.use_case,
        consent_version="tool-runtime",
        correlation_id=request.call_id,
    )


__all__ = ["ToolRuntime", "ToolRuntimeError"]
