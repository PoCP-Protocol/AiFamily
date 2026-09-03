"""ContextScope guard for Agent Runtime requests."""

from __future__ import annotations

from backend.intelligence.agent_runtime.contracts import AgentAuthorization, AgentRun, AgentTask
from backend.intelligence.agent_runtime.durable_runtime import DurableAgentRuntime
from backend.intelligence.context_engine.contracts import ContextScope, ContextScopeError


class ContextBoundAgentRuntime:
    """Bind durable Agent execution to a server-resolved context scope.

    Identity, consent and deletion state are resolved by the application
    composition root into ``ContextScope``.  This adapter only proves that the
    task cannot substitute another tenant/family/data class before reaching the
    Agent Runtime or Model Gateway.
    """

    def __init__(self, runtime: DurableAgentRuntime) -> None:
        self._runtime = runtime

    async def execute(
        self,
        task: AgentTask,
        authorization: AgentAuthorization | None,
        *,
        scope: ContextScope,
        idempotency_key: str,
    ) -> AgentRun:
        if not isinstance(scope, ContextScope):
            raise TypeError("scope must be a ContextScope")
        scope.assert_active()
        if task.tenant_id != scope.tenant_id or task.family_id != scope.family_id:
            raise ContextScopeError("AGENT_TASK_SCOPE_MISMATCH")
        if task.data_class != scope.data_class.value:
            raise ContextScopeError("AGENT_TASK_DATA_CLASS_MISMATCH")
        return await self._runtime.execute(
            task,
            authorization,
            idempotency_key=idempotency_key,
        )


__all__ = ["ContextBoundAgentRuntime"]
