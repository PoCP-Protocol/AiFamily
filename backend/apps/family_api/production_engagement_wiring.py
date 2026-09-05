"""Production composition root for the AI engagement draft flow.

The resolver binds a deployment-owned identity/consent scope to the durable
experience outbox reader and the same request-scoped Model Gateway sinks used by
the multimodal runtime.  It never accepts client-created events or synthetic
scopes in staging/production.
"""

from __future__ import annotations

import hashlib
import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Header, Path
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.apps.family_api.trusted_experience_scope import (
    RequestPrincipalResolverFactory,
    SqlAlchemyAuthenticatedEngagementReviewerResolver,
    SqlAlchemyAuthenticatedEngagementScopeResolver,
)
from backend.intelligence.context_engine.async_port import AsyncContextBrokerPort
from backend.intelligence.context_engine.contracts import ContextScope
from backend.intelligence.experience.contracts import ExperienceScope
from backend.intelligence.experience.engagement import (
    EngagementDraft,
    EngagementDraftApplication,
    EngagementDraftService,
)
from backend.intelligence.experience.engagement_persistence import (
    SqlAlchemyEngagementEventReader,
)
from backend.intelligence.experience.engagement_review import (
    AchievementCandidateSubmissionService,
    EngagementReviewer,
    SqlAlchemyEngagementDraftReviewStore,
)
from backend.intelligence.human_gate import (
    DecisionOutcome,
    GateScope,
    HumanTask,
    SqlAlchemyHumanGate,
)
from backend.intelligence.model_gateway.attempts import AttemptSink
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.observability import TelemetrySink
from backend.intelligence.safety.persistence import SafetyDecisionSink
from backend.platform.audit import AuditRecorder
from backend.platform.persistence.unit_of_work import SqlAlchemyUnitOfWork

ScopeResolver = Callable[[str], ExperienceScope | Awaitable[ExperienceScope]]
StringResolver = Callable[[ExperienceScope], str | Awaitable[str]]
ReviewerResolver = Callable[
    [ExperienceScope], EngagementReviewer | Awaitable[EngagementReviewer]
]
AttemptSinkFactory = Callable[[AsyncSession], AttemptSink]
SafetySinkFactory = Callable[[AsyncSession], SafetyDecisionSink]
TelemetrySinkFactory = Callable[[AsyncSession], TelemetrySink]
ContextBrokerFactory = Callable[[], AsyncContextBrokerPort]
PRODUCTION_ENVIRONMENTS = frozenset({"staging", "production"})


@dataclass(frozen=True, slots=True)
class ProductionEngagementRuntime:
    """Request handle for one authenticated, consent-checked family scope."""

    scope: ExperienceScope
    session_factory: async_sessionmaker[AsyncSession]
    gateway: ModelGateway
    provider_id: str
    authorization_ref_resolver: StringResolver
    actor_id_resolver: StringResolver
    context_snapshot_ref_resolver: StringResolver
    attempt_sink_factory: AttemptSinkFactory
    safety_sink_factory: SafetySinkFactory
    telemetry_sink_factory: TelemetrySinkFactory
    context_broker: AsyncContextBrokerPort | None = None
    clock: Callable[[], datetime] | None = None
    reviewer_resolver: ReviewerResolver | None = None

    async def generate_draft(
        self,
        *,
        request_id: str,
        event_ids: tuple[str, ...],
        payload: Mapping[str, Any] | None = None,
    ) -> EngagementDraft:
        authorization_ref = await _resolve_string(
            self.authorization_ref_resolver, self.scope, "authorization_ref"
        )
        actor_id = await _resolve_string(self.actor_id_resolver, self.scope, "actor_id")
        context_snapshot_ref = await _resolve_string(
            self.context_snapshot_ref_resolver, self.scope, "context_snapshot_ref"
        )
        if self.context_broker is not None:
            await self.context_broker.read(
                context_snapshot_ref,
                _context_scope(self.scope),
            )
        async with SqlAlchemyUnitOfWork(self.session_factory) as unit_of_work:
            session = unit_of_work.session
            if session is None:  # pragma: no cover - UoW contract guard
                raise RuntimeError("production engagement UoW did not open a session")
            scoped_gateway = (
                self.gateway.with_attempt_sink(self.attempt_sink_factory(session))
                .with_safety_sink(self.safety_sink_factory(session))
                .with_telemetry_sink(self.telemetry_sink_factory(session))
            )
            application = EngagementDraftApplication(
                EngagementDraftService(scoped_gateway, clock=self.clock),
                SqlAlchemyEngagementEventReader(session),
            )
            result = await application.generate_draft(
                request_id=request_id,
                provider_id=self.provider_id,
                scope=self.scope,
                actor_id=actor_id,
                authorization_ref=authorization_ref,
                event_ids=event_ids,
                context_snapshot_ref=context_snapshot_ref,
                payload=payload,
            )
            stored = await SqlAlchemyEngagementDraftReviewStore(session).save(result)
            await unit_of_work.commit()
            return replace(result, draft_id=stored.draft_id)

    async def submit_achievement_candidate(
        self,
        *,
        draft_id: str,
        candidate_id: str,
        idempotency_key: str,
    ) -> HumanTask:
        """Open a HumanTask from a server-owned draft and revalidated evidence."""

        authorization_ref = await _resolve_string(
            self.authorization_ref_resolver, self.scope, "authorization_ref"
        )
        actor_id = await _resolve_string(self.actor_id_resolver, self.scope, "actor_id")
        async with SqlAlchemyUnitOfWork(self.session_factory) as unit_of_work:
            session = unit_of_work.session
            if session is None:  # pragma: no cover - UoW contract guard
                raise RuntimeError("production engagement UoW did not open a session")
            recorder = AuditRecorder()
            gate = SqlAlchemyHumanGate(session)
            task = await AchievementCandidateSubmissionService(
                SqlAlchemyEngagementDraftReviewStore(session),
                SqlAlchemyEngagementEventReader(session),
                gate,
                recorder,
            ).submit(
                draft_id=draft_id,
                candidate_id=candidate_id,
                scope=self.scope,
                actor_id=actor_id,
                approval_ref=authorization_ref,
                idempotency_key=idempotency_key,
            )
            await gate.flush_audit(recorder)
            await unit_of_work.commit()
            return task

    async def decide_achievement_task(
        self,
        *,
        task_id: str,
        outcome: DecisionOutcome | str,
        reason: str | None,
        idempotency_key: str,
    ) -> HumanTask:
        """Persist one trusted guardian/professional decision; never execute it inline."""

        if self.reviewer_resolver is None:
            raise RuntimeError("engagement reviewer resolver is not configured")
        resolved = self.reviewer_resolver(self.scope)
        reviewer = await resolved if inspect.isawaitable(resolved) else resolved
        if not isinstance(reviewer, EngagementReviewer):
            raise PermissionError("engagement reviewer identity is invalid")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        async with SqlAlchemyUnitOfWork(self.session_factory) as unit_of_work:
            session = unit_of_work.session
            if session is None:  # pragma: no cover - UoW contract guard
                raise RuntimeError("production engagement UoW did not open a session")
            gate = SqlAlchemyHumanGate(session)
            task = await gate.get(task_id)
            _assert_review_scope(task.proposal.scope, self.scope)
            recorder = AuditRecorder()
            decision_id = _review_decision_id(
                tenant_id=self.scope.tenant_id,
                idempotency_key=idempotency_key,
            )
            decided, _ = await gate.decide(
                task_id,
                actor_id=reviewer.actor_id,
                actor_type=reviewer.actor_type,
                outcome=outcome,
                reason=reason,
                decision_id=decision_id,
                recorder=recorder,
            )
            await gate.flush_audit(recorder)
            await unit_of_work.commit()
            return decided


@dataclass(frozen=True, slots=True)
class ProductionEngagementRuntimeResolver:
    """Resolve an explicit production scope and compose a durable runtime."""

    scope_resolver: ScopeResolver
    session_factory: async_sessionmaker[AsyncSession]
    gateway: ModelGateway
    provider_id: str
    environment: str
    authorization_ref_resolver: StringResolver
    actor_id_resolver: StringResolver
    context_snapshot_ref_resolver: StringResolver
    attempt_sink_factory: AttemptSinkFactory
    safety_sink_factory: SafetySinkFactory
    telemetry_sink_factory: TelemetrySinkFactory
    context_broker: AsyncContextBrokerPort | None = None
    clock: Callable[[], datetime] | None = None
    reviewer_resolver: ReviewerResolver | None = None

    def __post_init__(self) -> None:
        if self.environment not in PRODUCTION_ENVIRONMENTS:
            raise ValueError("production engagement environment must be staging or production")
        if not callable(self.scope_resolver):
            raise TypeError("scope_resolver must be callable")
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        if not isinstance(self.gateway, ModelGateway):
            raise TypeError("gateway must be a ModelGateway")
        if self.gateway.safety_runtime is None:
            raise ValueError("production engagement gateway requires SafetyRuntime")
        if self.provider_id not in self.gateway.available_provider_ids():
            raise ValueError("provider_id must be wired in the Model Gateway")
        for name, resolver in (
            ("authorization_ref_resolver", self.authorization_ref_resolver),
            ("actor_id_resolver", self.actor_id_resolver),
            ("context_snapshot_ref_resolver", self.context_snapshot_ref_resolver),
        ):
            if not callable(resolver):
                raise TypeError(f"{name} must be callable")
        if self.context_broker is not None and not callable(
            getattr(self.context_broker, "read", None)
        ):
            raise TypeError("context_broker must implement read()")
        for name, factory in (
            ("attempt_sink_factory", self.attempt_sink_factory),
            ("safety_sink_factory", self.safety_sink_factory),
            ("telemetry_sink_factory", self.telemetry_sink_factory),
        ):
            if not callable(factory):
                raise TypeError(f"{name} must be callable")
        if self.clock is not None and not callable(self.clock):
            raise TypeError("clock must be callable")
        if self.reviewer_resolver is not None and not callable(self.reviewer_resolver):
            raise TypeError("reviewer_resolver must be callable")

    async def resolve(self, family_id: str) -> ProductionEngagementRuntime:
        if not isinstance(family_id, str) or not family_id.strip():
            raise ValueError("family_id is required")
        resolved = self.scope_resolver(family_id)
        scope = await resolved if inspect.isawaitable(resolved) else resolved
        if not isinstance(scope, ExperienceScope):
            raise TypeError("scope_resolver must return ExperienceScope")
        if scope.family_id != family_id:
            raise PermissionError("resolved scope does not match requested family")
        if not scope.consent_granted:
            raise PermissionError("engagement consent is not granted")
        if scope.deletion_ref.requested_at is not None:
            raise PermissionError("engagement scope is deleted")
        if str(scope.data_class) == "SYNTHETIC":
            raise ValueError("production engagement scope cannot be synthetic")
        return ProductionEngagementRuntime(
            scope=scope,
            session_factory=self.session_factory,
            gateway=self.gateway,
            provider_id=self.provider_id,
            authorization_ref_resolver=self.authorization_ref_resolver,
            actor_id_resolver=self.actor_id_resolver,
            context_snapshot_ref_resolver=self.context_snapshot_ref_resolver,
            context_broker=self.context_broker,
            attempt_sink_factory=self.attempt_sink_factory,
            safety_sink_factory=self.safety_sink_factory,
            telemetry_sink_factory=self.telemetry_sink_factory,
            clock=self.clock,
            reviewer_resolver=self.reviewer_resolver,
        )


def install_sql_engagement_runtime_wiring(
    application: FastAPI,
    *,
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    gateway: ModelGateway,
    provider_id: str,
    environment: str,
    attempt_sink_factory: AttemptSinkFactory,
    safety_sink_factory: SafetySinkFactory,
    telemetry_sink_factory: TelemetrySinkFactory,
    authorization_ref_resolver: StringResolver,
    actor_id_resolver: StringResolver,
    context_snapshot_ref_resolver: StringResolver,
    clock: Callable[[], datetime] | None = None,
    context_broker: AsyncContextBrokerPort | None = None,
    context_broker_factory: ContextBrokerFactory | None = None,
    principal_resolver_factory: RequestPrincipalResolverFactory | None = None,
) -> None:
    """Install a request-authenticated SQL Engagement resolver.

    The dependency reads only transport authentication metadata.  It creates a
    fresh scope resolver for each request so identity/session and consent are
    queried again rather than cached in the process-wide app object.
    """

    if not isinstance(application, FastAPI):
        raise TypeError("application must be a FastAPI instance")
    if not isinstance(engine, AsyncEngine):
        raise TypeError("engine must be an AsyncEngine")
    if not isinstance(session_factory, async_sessionmaker):
        raise TypeError("session_factory must be an async_sessionmaker")
    if context_broker is not None and context_broker_factory is not None:
        raise ValueError("provide either context_broker or context_broker_factory")
    if context_broker is None and context_broker_factory is not None:
        context_broker = context_broker_factory()
    if principal_resolver_factory is not None and not callable(principal_resolver_factory):
        raise TypeError("principal_resolver_factory must be callable")

    async def resolve_request_runtime(
        family_id: str = Path(...),
        authorization: str | None = Header(default=None),
        correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
        causation_id: str | None = Header(default=None, alias="X-Causation-ID"),
    ) -> ProductionEngagementRuntimeResolver:
        if principal_resolver_factory is not None:
            def request_principal_factory(requested_family_id: str):
                return principal_resolver_factory(
                    requested_family_id,
                    authorization,
                    correlation_id,
                    causation_id,
                )
        else:
            request_principal_factory = None
        scope_resolver = SqlAlchemyAuthenticatedEngagementScopeResolver(
            engine=engine,
            session_factory=session_factory,
            authorization=authorization,
            correlation_id=correlation_id,
            causation_id=causation_id,
            principal_resolver_factory=request_principal_factory,
        )
        return ProductionEngagementRuntimeResolver(
            scope_resolver=scope_resolver,
            session_factory=session_factory,
            gateway=gateway,
            provider_id=provider_id,
            environment=environment,
            authorization_ref_resolver=authorization_ref_resolver,
            actor_id_resolver=actor_id_resolver,
            context_snapshot_ref_resolver=context_snapshot_ref_resolver,
            context_broker=context_broker,
            attempt_sink_factory=attempt_sink_factory,
            safety_sink_factory=safety_sink_factory,
            telemetry_sink_factory=telemetry_sink_factory,
            clock=clock,
            reviewer_resolver=SqlAlchemyAuthenticatedEngagementReviewerResolver(
                engine=engine,
                session_factory=session_factory,
                authorization=authorization,
                family_id=family_id,
                principal_resolver_factory=request_principal_factory,
            ),
        )

    from backend.intelligence.experience.engagement_api import (
        get_engagement_draft_runtime_resolver,
    )

    application.dependency_overrides[get_engagement_draft_runtime_resolver] = (
        resolve_request_runtime
    )


async def _resolve_string(
    resolver: StringResolver, scope: ExperienceScope, name: str
) -> str:
    value = resolver(scope)
    value = await value if inspect.isawaitable(value) else value
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} resolver returned an empty value")
    return value


def _assert_review_scope(gate_scope: GateScope, scope: ExperienceScope) -> None:
    if (
        gate_scope.tenant_id != scope.tenant_id
        or gate_scope.family_id != scope.family_id
        or gate_scope.subject_ids != scope.subject_ids
        or gate_scope.purpose != scope.purpose
        or gate_scope.consent_version != scope.consent_version
    ):
        raise PermissionError("engagement human task is outside the current scope")


def _review_decision_id(*, tenant_id: str, idempotency_key: str) -> str:
    digest = hashlib.sha256(f"{tenant_id}\x1f{idempotency_key}".encode()).hexdigest()
    return f"engagement-decision:{digest}"


def _context_scope(scope: ExperienceScope) -> ContextScope:
    """Project the shared experience envelope into the Context Engine port."""

    return ContextScope(
        tenant_id=scope.tenant_id,
        region_id=scope.region_id,
        family_id=scope.family_id,
        subject_ids=scope.subject_ids,
        purpose=scope.purpose,
        consent_version=scope.consent_version,
        consent_granted=scope.consent_granted,
        data_class=scope.data_class,
        locale=scope.locale,
        content_locale=scope.content_locale,
        model_locale=scope.model_locale,
        policy_locale=scope.policy_locale,
        deletion_ref=scope.deletion_ref.deletion_id,
        correlation_id=scope.correlation_id,
        causation_id=scope.causation_id,
    )


__all__ = [
    "PRODUCTION_ENVIRONMENTS",
    "ProductionEngagementRuntime",
    "ProductionEngagementRuntimeResolver",
    "ReviewerResolver",
    "install_sql_engagement_runtime_wiring",
]
