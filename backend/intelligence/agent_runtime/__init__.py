"""Public contract for the governed, provider-neutral Agent Runtime."""

from backend.intelligence.agent_runtime.authorization import (
    AgentAuthorizationDecision,
    AgentAuthorizationError,
    AgentAuthorizer,
)
from backend.intelligence.agent_runtime.authorization_persistence import (
    AgentAuthorizationAuditEvent,
    AgentAuthorizationAuditRow,
    AgentAuthorizationConflict,
    AgentAuthorizationLeaseStore,
    AgentAuthorizationNotFound,
    AgentAuthorizationPersistenceBase,
    AgentAuthorizationPersistenceError,
    AgentAuthorizationRow,
    AgentAuthorizationScope,
    AgentAuthorizationStore,
    SqlAlchemyAgentAuthorizationLeaseStore,
    SqlAlchemyAgentAuthorizationStore,
)
from backend.intelligence.agent_runtime.composition import (
    build_agent_runtime,
    build_context_bound_agent_runtime,
    build_durable_agent_runtime,
)
from backend.intelligence.agent_runtime.context_bound import ContextBoundAgentRuntime
from backend.intelligence.agent_runtime.contracts import (
    AgentAuthorization,
    AgentDefinition,
    AgentExecutionPort,
    AgentRun,
    AgentTask,
    AuthorizationBudget,
    StructuredGenerationPort,
)
from backend.intelligence.agent_runtime.durable_runtime import (
    DurableAgentRuntime,
    DurableAgentRuntimeError,
)
from backend.intelligence.agent_runtime.gateway_port import ModelGatewayExecutionPort
from backend.intelligence.agent_runtime.persistence import (
    AgentRunConflict,
    AgentRunNotFound,
    AgentRunPersistenceBase,
    AgentRunPersistenceError,
    AgentRunPersistencePort,
    AgentRunRecord,
    AgentRunReplay,
    AgentRunRow,
    AgentRunScope,
    AgentRunStatus,
    AgentTrace,
    AgentTraceEvent,
    AgentTraceRow,
    SqlAlchemyAgentRunStore,
)
from backend.intelligence.agent_runtime.registry import (
    AgentDefinitionRegistry,
    AgentRegistryError,
)
from backend.intelligence.agent_runtime.runtime import AgentRuntime, AgentRuntimeError

__all__ = [
    "AgentAuthorization",
    "build_agent_runtime",
    "build_durable_agent_runtime",
    "build_context_bound_agent_runtime",
    "ContextBoundAgentRuntime",
    "ModelGatewayExecutionPort",
    "DurableAgentRuntime",
    "DurableAgentRuntimeError",
    "AgentAuthorizationDecision",
    "AgentAuthorizationError",
    "AgentAuthorizer",
    "AgentDefinition",
    "AgentExecutionPort",
    "AgentRun",
    "AgentRunConflict",
    "AgentRunNotFound",
    "AgentRunPersistenceBase",
    "AgentRunPersistenceError",
    "AgentRunPersistencePort",
    "AgentRunRecord",
    "AgentRunReplay",
    "AgentRunRow",
    "AgentRunScope",
    "AgentRunStatus",
    "AgentRuntime",
    "AgentRuntimeError",
    "AgentDefinitionRegistry",
    "AgentRegistryError",
    "AgentTask",
    "AuthorizationBudget",
    "StructuredGenerationPort",
    "AgentTraceEvent",
    "AgentTrace",
    "AgentTraceRow",
    "SqlAlchemyAgentRunStore",
    "AgentAuthorizationAuditEvent",
    "AgentAuthorizationAuditRow",
    "AgentAuthorizationConflict",
    "AgentAuthorizationLeaseStore",
    "AgentAuthorizationStore",
    "AgentAuthorizationNotFound",
    "AgentAuthorizationPersistenceBase",
    "AgentAuthorizationPersistenceError",
    "AgentAuthorizationRow",
    "AgentAuthorizationScope",
    "SqlAlchemyAgentAuthorizationLeaseStore",
    "SqlAlchemyAgentAuthorizationStore",
]
