"""Production composition root for governed Agent Runtime executions.

The resolver is deliberately an application boundary: identity/consent is
resolved into ``ContextScope`` by the host, while Agent Runtime, Model Gateway,
Attempt, SafetyDecision and AgentRun/Trace stores are assembled per request and
committed as one transaction.  No provider SDK or domain repository is reachable
here.
"""

from __future__ import annotations

import hashlib
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.intelligence.agent_runtime.authorization import AgentAuthorizer
from backend.intelligence.agent_runtime.composition import build_context_bound_agent_runtime
from backend.intelligence.agent_runtime.contracts import AgentAuthorization, AgentRun, AgentTask
from backend.intelligence.agent_runtime.gateway_port import ModelGatewayExecutionPort
from backend.intelligence.agent_runtime.persistence import SqlAlchemyAgentRunStore
from backend.intelligence.context_engine.async_port import AsyncContextBrokerPort
from backend.intelligence.context_engine.contracts import ContextScope, ContextScopeError
from backend.intelligence.human_gate.contracts import (
    ActionProposal,
    ActorType,
    DecisionOutcome,
    GateScope,
    HumanTask,
    NamedActionRequest,
)
from backend.intelligence.human_gate.persistence import SqlAlchemyHumanGate
from backend.intelligence.model_gateway.attempts import AttemptSink
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.observability import TelemetrySink
from backend.intelligence.safety.persistence import SafetyDecisionSink
from backend.platform.audit import AuditRecorder
from backend.platform.persistence.unit_of_work import SqlAlchemyUnitOfWork

ScopeResolver = Callable[[str], ContextScope | Awaitable[ContextScope]]
SubjectScopeResolver = Callable[[str, str], ContextScope | Awaitable[ContextScope]]
AttemptSinkFactory = Callable[[AsyncSession], AttemptSink]
SafetySinkFactory = Callable[[AsyncSession], SafetyDecisionSink]
TelemetrySinkFactory = Callable[[AsyncSession], TelemetrySink]
RegistryFactory = Callable[[AsyncSession], object]
PRODUCTION_ENVIRONMENTS = frozenset({"staging", "production"})
ASSESSMENT_REVIEW_ACTION = "CONFIRM_GROWTH_HYPOTHESIS"
ASSESSMENT_REVIEW_USE_CASE = "assessment_interpretation"


@dataclass(frozen=True, slots=True)
class ProductionAgentRuntime:
    """Request-scoped Agent handle bound to a server-resolved scope."""

    scope: ContextScope
    session_factory: async_sessionmaker[AsyncSession]
    gateway: ModelGateway
    provider_id: str
    registry_path: str | Path
    prompt_registry: object | None
    schema_registry: object | None
    prompt_registry_factory: RegistryFactory | None
    schema_registry_factory: RegistryFactory | None
    execution_material_resolver: object | None
    attempt_sink_factory: AttemptSinkFactory
    safety_sink_factory: SafetySinkFactory
    telemetry_sink_factory: TelemetrySinkFactory
    context_broker: AsyncContextBrokerPort
    authorizer: AgentAuthorizer | None = None
    clock: Callable[[], datetime] | None = None

    async def execute(
        self,
        task: AgentTask,
        authorization: AgentAuthorization | None,
        *,
        idempotency_key: str,
    ) -> AgentRun:
        self.scope.assert_active()
        if task.tenant_id != self.scope.tenant_id or task.family_id != self.scope.family_id:
            raise ContextScopeError("AGENT_TASK_SCOPE_MISMATCH")
        if task.data_class != self.scope.data_class.value:
            raise ContextScopeError("AGENT_TASK_DATA_CLASS_MISMATCH")
        await self.context_broker.read(
            task.context_snapshot_ref,
            self.scope,
            now=self.clock() if self.clock is not None else None,
        )
        async with SqlAlchemyUnitOfWork(self.session_factory) as unit_of_work:
            session = unit_of_work.session
            if session is None:  # pragma: no cover - UoW contract guard
                raise RuntimeError("production Agent UoW did not open a session")
            scoped_gateway = (
                self.gateway.with_attempt_sink(self.attempt_sink_factory(session))
                .with_safety_sink(self.safety_sink_factory(session))
                .with_telemetry_sink(self.telemetry_sink_factory(session))
            )
            prompt_registry = (
                self.prompt_registry_factory(session)
                if self.prompt_registry_factory is not None
                else self.prompt_registry
            )
            schema_registry = (
                self.schema_registry_factory(session)
                if self.schema_registry_factory is not None
                else self.schema_registry
            )
            runtime = build_context_bound_agent_runtime(
                generation_port=ModelGatewayExecutionPort(scoped_gateway, self.provider_id),
                registry_path=self.registry_path,
                prompt_registry=prompt_registry,
                schema_registry=schema_registry,
                execution_material_resolver=self.execution_material_resolver,
                run_store=SqlAlchemyAgentRunStore(session),
                authorizer=self.authorizer,
                clock=self.clock,
                telemetry_sink=self.telemetry_sink_factory(session),
            )
            result = await runtime.execute(
                task,
                authorization,
                scope=self.scope,
                idempotency_key=idempotency_key,
            )
            if result.draft.safety_review is not None:
                result = await self._stage_safety_review(session, result, task=task)
            await unit_of_work.commit()
            return result

    async def decide_review(
        self,
        task_id: str,
        *,
        actor_id: str,
        actor_type: ActorType | str,
        outcome: DecisionOutcome | str,
        decision_id: str,
        reason: str | None = None,
    ) -> tuple[HumanTask, NamedActionRequest | None]:
        """Decide an FE-S01 task against the freshly resolved trusted scope.

        ACCEPT returns a NamedActionRequest; this boundary never executes the
        action or writes an assessment fact.
        """

        self.scope.assert_active()
        async with SqlAlchemyUnitOfWork(self.session_factory) as unit_of_work:
            session = unit_of_work.session
            if session is None:  # pragma: no cover - UoW contract guard
                raise RuntimeError("production Agent UoW did not open a session")
            gate = SqlAlchemyHumanGate(session)
            task = await gate.get(task_id)
            _assert_gate_scope(self.scope, task.proposal.scope)
            if task.proposal.action_name != ASSESSMENT_REVIEW_ACTION:
                raise ContextScopeError("AGENT_HUMAN_GATE_ACTION_MISMATCH")
            recorder = AuditRecorder()
            decided, request = await gate.decide(
                task_id,
                actor_id=actor_id,
                actor_type=actor_type,
                outcome=outcome,
                recorder=recorder,
                reason=reason,
                decision_id=decision_id,
                now=self.clock() if self.clock is not None else None,
            )
            await gate.flush_audit(recorder)
            await unit_of_work.commit()
            return decided, request

    async def _stage_safety_review(
        self,
        session: AsyncSession,
        result: AgentRun,
        *,
        task: AgentTask,
    ) -> AgentRun:
        if task.use_case != ASSESSMENT_REVIEW_USE_CASE:
            # Growth plans and other high-impact flows retain their dedicated
            # review envelopes. The generic bridge never creates a second,
            # weaker action for them; the ModelDraft remains non-publishable.
            return result
        review = result.draft.safety_review
        if review is None:  # pragma: no cover - caller guard
            return result
        identity = _assessment_review_identity(
            task.tenant_id,
            task.family_id,
            result.run_id,
        )
        draft_id = f"agent-draft:{identity}"
        proposal = ActionProposal(
            proposal_id=f"agent-review:{identity}",
            draft_id=draft_id,
            draft_status=result.draft.status,
            action_name=ASSESSMENT_REVIEW_ACTION,
            action_arguments={
                "agent_run_ref": result.run_id,
                "agent_request_ref": result.request_id,
                "draft_ref": draft_id,
                "recommendation_status": "PROPOSED",
            },
            scope=_gate_scope(self.scope),
            allowed_actor_types=(ActorType.GUARDIAN,),
            risk_level=review.risk_level,
            provenance_ref=f"agent-provenance:{identity}",
            created_at=result.completed_at,
            expires_at=result.completed_at + timedelta(hours=24),
        )
        recorder = AuditRecorder()
        gate = SqlAlchemyHumanGate(session)
        human_task = await gate.submit(
            proposal,
            recorder=recorder,
            task_id=assessment_review_task_ref(
                task.tenant_id,
                task.family_id,
                result.run_id,
            ),
        )
        await gate.flush_audit(recorder)
        return replace(result, human_task_ref=human_task.task_id)


@dataclass(frozen=True, slots=True)
class ProductionAgentRuntimeResolver:
    """Resolve authenticated identity/consent and build a durable Agent handle."""

    scope_resolver: ScopeResolver
    session_factory: async_sessionmaker[AsyncSession]
    gateway: ModelGateway
    provider_id: str
    registry_path: str | Path
    attempt_sink_factory: AttemptSinkFactory
    safety_sink_factory: SafetySinkFactory
    environment: str
    prompt_registry: object | None = None
    schema_registry: object | None = None
    prompt_registry_factory: RegistryFactory | None = None
    schema_registry_factory: RegistryFactory | None = None
    execution_material_resolver: object | None = None
    telemetry_sink_factory: TelemetrySinkFactory | None = None
    context_broker: AsyncContextBrokerPort | None = None
    authorizer: AgentAuthorizer | None = None
    clock: Callable[[], datetime] | None = None
    subject_scope_resolver: SubjectScopeResolver | None = None

    def __post_init__(self) -> None:
        if not callable(self.scope_resolver):
            raise TypeError("scope_resolver must be callable")
        if self.subject_scope_resolver is not None and not callable(self.subject_scope_resolver):
            raise TypeError("subject_scope_resolver must be callable")
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        if not isinstance(self.gateway, ModelGateway):
            raise TypeError("gateway must be a ModelGateway")
        if self.gateway.safety_runtime is None:
            raise ValueError("production Agent gateway requires SafetyRuntime")
        if self.environment not in PRODUCTION_ENVIRONMENTS:
            raise ValueError("production Agent environment must be staging or production")
        if self.provider_id not in self.gateway.available_provider_ids():
            raise ValueError("provider_id must be wired in the Model Gateway")
        if self.prompt_registry_factory is None and not callable(
            getattr(self.prompt_registry, "resolve", None)
        ):
            raise ValueError("prompt_registry_or_factory_required")
        if self.schema_registry_factory is None and not callable(
            getattr(self.schema_registry, "resolve", None)
        ):
            raise ValueError("schema_registry_or_factory_required")
        if self.prompt_registry_factory is not None and not callable(self.prompt_registry_factory):
            raise TypeError("prompt_registry_factory must be callable")
        if self.schema_registry_factory is not None and not callable(self.schema_registry_factory):
            raise TypeError("schema_registry_factory must be callable")
        if self.execution_material_resolver is not None and not callable(
            getattr(self.execution_material_resolver, "resolve", None)
        ):
            raise TypeError("execution_material_resolver must implement resolve")
        if not callable(self.attempt_sink_factory):
            raise TypeError("attempt_sink_factory must be callable")
        if not callable(self.safety_sink_factory):
            raise TypeError("safety_sink_factory must be callable")
        if self.telemetry_sink_factory is None:
            raise ValueError("production Agent requires a durable telemetry_sink_factory")
        if not callable(self.telemetry_sink_factory):
            raise TypeError("telemetry_sink_factory must be callable")
        if not isinstance(self.context_broker, AsyncContextBrokerPort):
            raise ValueError("production Agent requires a Context Broker")
        if self.context_broker.durability_mode != "DURABLE":
            raise ValueError("production Agent requires a durable Context Broker")

    async def resolve(self, family_id: str) -> ProductionAgentRuntime:
        if not isinstance(family_id, str) or not family_id.strip():
            raise ValueError("family_id is required")
        resolved = self.scope_resolver(family_id)
        scope = await resolved if inspect.isawaitable(resolved) else resolved
        if not isinstance(scope, ContextScope):
            raise TypeError("scope_resolver must return ContextScope")
        if scope.family_id != family_id:
            raise PermissionError("resolved scope does not match requested family")
        scope.assert_active()
        if scope.data_class.value == "SYNTHETIC":
            raise ValueError("production Agent scope cannot be synthetic")
        return self._build_runtime(scope)

    def _build_runtime(self, scope: ContextScope) -> ProductionAgentRuntime:
        return ProductionAgentRuntime(
            scope=scope,
            session_factory=self.session_factory,
            gateway=self.gateway,
            provider_id=self.provider_id,
            registry_path=self.registry_path,
            prompt_registry=self.prompt_registry,
            schema_registry=self.schema_registry,
            prompt_registry_factory=self.prompt_registry_factory,
            schema_registry_factory=self.schema_registry_factory,
            execution_material_resolver=self.execution_material_resolver,
            attempt_sink_factory=self.attempt_sink_factory,
            safety_sink_factory=self.safety_sink_factory,
            telemetry_sink_factory=self.telemetry_sink_factory,
            context_broker=self.context_broker,
            authorizer=self.authorizer,
            clock=self.clock,
        )

    async def resolve_for_subject(
        self,
        family_id: str,
        subject_id: str,
    ) -> ProductionAgentRuntime:
        """Narrow a verified family scope to the evidence subject.

        The underlying identity/consent resolver remains authoritative. This
        method can only remove subjects from that verified scope; it cannot add
        a client-named subject that was not authorized by it.
        """

        if not isinstance(subject_id, str) or not subject_id.strip():
            raise ValueError("subject_id is required")
        if self.subject_scope_resolver is not None:
            resolved = self.subject_scope_resolver(family_id, subject_id)
            scope = await resolved if inspect.isawaitable(resolved) else resolved
            if not isinstance(scope, ContextScope):
                raise TypeError("subject_scope_resolver must return ContextScope")
            if scope.family_id != family_id or scope.subject_ids != (subject_id,):
                raise ContextScopeError("AGENT_SUBJECT_SCOPE_MISMATCH")
            scope.assert_active()
            if scope.data_class.value == "SYNTHETIC":
                raise ValueError("production Agent scope cannot be synthetic")
            return self._build_runtime(scope)
        runtime = await self.resolve(family_id)
        if subject_id not in runtime.scope.subject_ids:
            raise ContextScopeError("AGENT_SUBJECT_SCOPE_MISMATCH")
        if runtime.scope.subject_ids == (subject_id,):
            return runtime
        narrowed_scope = replace(runtime.scope, subject_ids=(subject_id,))
        return replace(runtime, scope=narrowed_scope)


def _gate_scope(scope: ContextScope) -> GateScope:
    return GateScope(
        tenant_id=scope.tenant_id,
        family_id=scope.family_id,
        subject_ids=scope.subject_ids,
        purpose=scope.purpose,
        consent_version=scope.consent_version,
        correlation_id=scope.correlation_id,
        region_id=scope.region_id,
        deletion_ref=scope.deletion_ref,
    )


def _assert_gate_scope(current: ContextScope, frozen: GateScope) -> None:
    # correlation_id identifies a request/trace, not an authorization scope.
    # A reviewer necessarily arrives on a later request, so requiring the
    # correlation id frozen at draft time would reject every legitimate
    # decision. All authorization and lifecycle dimensions remain frozen.
    if (
        current.tenant_id != frozen.tenant_id
        or current.family_id != frozen.family_id
        or current.subject_ids != frozen.subject_ids
        or current.purpose != frozen.purpose
        or current.consent_version != frozen.consent_version
        or current.region_id != frozen.region_id
        or current.deletion_ref != frozen.deletion_ref
    ):
        raise ContextScopeError("AGENT_HUMAN_GATE_SCOPE_STALE")


def _assessment_review_identity(tenant_id: str, family_id: str, run_id: str) -> str:
    return hashlib.sha256(f"{tenant_id}:{family_id}:{run_id}".encode()).hexdigest()


def assessment_review_task_ref(tenant_id: str, family_id: str, run_id: str) -> str:
    """Return the deterministic FE-S01 HumanTask reference for a durable run."""

    identity = _assessment_review_identity(tenant_id, family_id, run_id)
    return f"human-task:agent-review:{identity}"


__all__ = [
    "ProductionAgentRuntime",
    "ProductionAgentRuntimeResolver",
    "assessment_review_task_ref",
]
