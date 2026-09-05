"""Explicit production composition root for the Web multimodal experience.

The HTTP router deliberately knows nothing about authentication, consent,
provider credentials or SQL sessions.  This module binds those already-owned
dependencies into a request-scoped runtime.  It never creates a synthetic
provider and it refuses the ``test`` environment, so an omitted or incomplete
deployment fails closed instead of serving a demo answer.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace

from fastapi import FastAPI, Header, Path
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.apps.family_api.trusted_experience_scope import (
    RequestPrincipalResolverFactory,
    SqlAlchemyAuthenticatedContextScopeResolver,
)
from backend.intelligence.context_engine.async_port import AsyncContextBrokerPort
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.experience.api import (
    MultimodalDraftApplication,
    MultimodalDraftRuntime,
    MultimodalDraftRuntimeResolver,
)
from backend.intelligence.experience.async_ledger_bridge import (
    AsyncExperienceRunLedgerBridge,
)
from backend.intelligence.experience.contract_binding import (
    MultimodalContractRegistryBinding,
    ReleaseContractExpectation,
)
from backend.intelligence.experience.invocation_fence import (
    SqlAlchemyModelInvocationFence,
)
from backend.intelligence.experience.multimodal_application import (
    RoutedMultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_context_application import (
    ContextBoundMultimodalCommand,
    ContextBoundMultimodalDraft,
    ContextBoundMultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_generation import (
    MultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_routing import MultimodalRouter
from backend.intelligence.experience.runtime_release_binding import (
    ActiveFamilyExperienceReleaseResolver,
    ActiveFamilyExperienceRuntimeBinding,
    SqlAlchemyActiveFamilyExperienceReleaseResolver,
    validate_active_runtime_binding,
)
from backend.intelligence.experience.sql_run_ledger import (
    SessionPerCallExperienceRunLedger,
)
from backend.intelligence.model_gateway.attempts import AttemptSink
from backend.intelligence.model_gateway.contracts import ModelReleaseBinding
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provenance import (
    SqlAlchemyModelDraftRegistry,
)
from backend.intelligence.observability import TelemetrySink
from backend.intelligence.safety.persistence import SafetyDecisionSink
from backend.platform.consent.models import ConsentPurpose
from backend.platform.persistence.unit_of_work import SqlAlchemyUnitOfWork

ScopeResolver = Callable[[str], ContextScope | Awaitable[ContextScope]]
DraftSubjectResolver = Callable[[ContextScope], str | None]
AttemptSinkFactory = Callable[[async_sessionmaker[AsyncSession]], AttemptSink]
SafetySinkFactory = Callable[[async_sessionmaker[AsyncSession]], SafetyDecisionSink]
TelemetrySinkFactory = Callable[[async_sessionmaker[AsyncSession]], TelemetrySink]
PRODUCTION_ENVIRONMENTS = frozenset({"staging", "production"})


@dataclass(frozen=True, slots=True)
class _RequestScopedMultimodalApplication(MultimodalDraftApplication):
    """Use one short-lived SQL session for the model-draft transaction."""

    session_factory: async_sessionmaker[AsyncSession]
    gateway: ModelGateway
    router: MultimodalRouter
    context_broker: AsyncContextBrokerPort
    model_draft_subject_resolver: DraftSubjectResolver | None
    attempt_sink_factory: AttemptSinkFactory
    safety_sink_factory: SafetySinkFactory
    telemetry_sink_factory: TelemetrySinkFactory
    active_release_resolver: ActiveFamilyExperienceReleaseResolver
    active_runtime_binding: ActiveFamilyExperienceRuntimeBinding

    async def generate_draft(
        self, command: ContextBoundMultimodalCommand
    ) -> ContextBoundMultimodalDraft:
        budget_runtime = self.gateway.budget_runtime
        safety_runtime = self.gateway.safety_runtime
        if budget_runtime is None or safety_runtime is None:  # pragma: no cover
            raise RuntimeError("production budget or safety runtime is unavailable")
        release_set = self.active_runtime_binding.release_set
        if (
            command.prompt_version != release_set.prompt_version
            or command.schema_version != release_set.schema_version
        ):
            raise ValueError("ACTIVE_RELEASE_CONTRACT_VERSION_MISMATCH")
        if (
            command.prompt_execution_plan is None
            or command.prompt_execution_plan.asset_digest != release_set.asset_digest
            or command.prompt_execution_plan.prompt_ref != release_set.prompt_ref
        ):
            raise ValueError("ACTIVE_RELEASE_PROMPT_EXECUTION_MISMATCH")
        command = replace(
            command,
            release_binding=ModelReleaseBinding(
                release_set_id=release_set.release_set_id,
                deployment_receipt_id=(
                    self.active_runtime_binding.deployment_receipt.receipt_id
                ),
                deployment_sequence=(
                    self.active_runtime_binding.deployment_receipt.sequence
                ),
                runtime_config_digest=release_set.runtime_config_digest,
                control_id=self.active_runtime_binding.deployment_receipt.control_id,
                provider_bundle_ids=tuple(
                    zip(release_set.provider_ids, release_set.bundle_ids, strict=True)
                ),
            ),
        )
        current_binding = await self.active_release_resolver.resolve(
            environment=self.gateway.environment,
            use_case=command.scope.purpose,
            data_class=command.scope.data_class.value,
        )
        validate_active_runtime_binding(
            current_binding,
            router=self.router,
            budget_runtime=budget_runtime,
            safety_runtime=safety_runtime,
            environment=self.gateway.environment,
            use_case=command.scope.purpose,
            data_class=command.scope.data_class.value,
        )
        if (
            current_binding.release_set.release_set_id
            != self.active_runtime_binding.release_set.release_set_id
            or current_binding.deployment_receipt.sequence
            != self.active_runtime_binding.deployment_receipt.sequence
        ):
            raise ValueError("ACTIVE_RELEASE_CHANGED_DURING_REQUEST")
        async with SqlAlchemyUnitOfWork(self.session_factory) as unit_of_work:
            session = unit_of_work.session
            if session is None:  # pragma: no cover - UoW contract guard
                raise RuntimeError("production experience UoW did not open a session")
            registry = SqlAlchemyModelDraftRegistry(session)
            gateway = self.gateway.with_attempt_sink(
                self.attempt_sink_factory(self.session_factory)
            ).with_safety_sink(
                self.safety_sink_factory(self.session_factory)
            ).with_telemetry_sink(
                self.telemetry_sink_factory(self.session_factory)
            ).with_invocation_fence(
                SqlAlchemyModelInvocationFence(
                    self.session_factory,
                    environment=self.gateway.environment,
                )
            )
            application = ContextBoundMultimodalExperienceService(
                context=self.context_broker,
                routed=RoutedMultimodalExperienceService(
                    router=self.router,
                    generation=MultimodalExperienceService(
                        gateway,
                        registry=registry,
                    ),
                ),
                registry=registry,
            )
            subject_id = (
                self.model_draft_subject_resolver(command.scope)
                if self.model_draft_subject_resolver is not None
                else command.scope.subject_id
            )
            result = await application.generate_draft(_with_subject(command, subject_id))
            await unit_of_work.commit()
            return result


def _with_subject(
    command: ContextBoundMultimodalCommand, subject_id: str | None
) -> ContextBoundMultimodalCommand:
    """Attach the explicit action subject without accepting it from HTTP."""

    if subject_id is None:
        raise ValueError(
            "production multimodal runtime requires an explicit model-draft subject "
            "for multi-subject scopes"
        )
    if subject_id not in command.scope.subject_ids:
        raise ValueError("model-draft subject must belong to the context scope")
    if command.model_draft_subject_id == subject_id:
        return command
    return replace(command, model_draft_subject_id=subject_id)


def install_sql_experience_runtime_wiring(
    application: FastAPI,
    *,
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    gateway: ModelGateway,
    router: MultimodalRouter,
    environment: str,
    attempt_sink_factory: AttemptSinkFactory,
    safety_sink_factory: SafetySinkFactory,
    telemetry_sink_factory: TelemetrySinkFactory,
    model_draft_subject_resolver: DraftSubjectResolver | None = None,
    purpose: ConsentPurpose = ConsentPurpose.AI_PERSONALIZATION,
    data_class: DataClass = DataClass.MINOR_PERSONAL_DATA,
    locale: str = "zh-CN",
    context_broker: AsyncContextBrokerPort | None = None,
    context_broker_factory: Callable[[], AsyncContextBrokerPort] | None = None,
    principal_resolver_factory: RequestPrincipalResolverFactory | None = None,
    contract_binding: MultimodalContractRegistryBinding | None = None,
    active_release_resolver: ActiveFamilyExperienceReleaseResolver | None = None,
) -> None:
    """Install request-authenticated SQL wiring for the multimodal route.

    Every request resolves Bearer identity, trusted tenant/family binding and
    current consent before composing the durable multimodal runtime. The app
    stores only the dependency callable; no principal or consent result is
    cached across requests.
    """

    if not isinstance(application, FastAPI):
        raise TypeError("application must be a FastAPI instance")
    if not isinstance(engine, AsyncEngine):
        raise TypeError("engine must be an AsyncEngine")
    if not isinstance(session_factory, async_sessionmaker):
        raise TypeError("session_factory must be an async_sessionmaker")
    if not isinstance(gateway, ModelGateway):
        raise TypeError("gateway must be a ModelGateway")
    if not isinstance(router, MultimodalRouter):
        raise TypeError("router must be a MultimodalRouter")
    if context_broker is not None and context_broker_factory is not None:
        raise ValueError("provide either context_broker or context_broker_factory")
    if context_broker is None:
        if context_broker_factory is None:
            raise ValueError(
                "production multimodal wiring requires a durable context_broker"
            )
        context_broker = context_broker_factory()
    if context_broker is None:  # pragma: no cover - defensive narrowing guard
        raise RuntimeError("context broker factory returned no broker")
    if principal_resolver_factory is not None and not callable(principal_resolver_factory):
        raise TypeError("principal_resolver_factory must be callable")
    if environment in PRODUCTION_ENVIRONMENTS and contract_binding is None:
        raise ValueError(
            "production multimodal wiring requires a published contract_binding"
        )

    async def resolve_request_runtime(
        family_id: str = Path(...),
        authorization: str | None = Header(default=None),
        correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
        causation_id: str | None = Header(default=None, alias="X-Causation-ID"),
    ) -> ProductionExperienceRuntimeResolver:
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
        scope_resolver = SqlAlchemyAuthenticatedContextScopeResolver(
            engine=engine,
            session_factory=session_factory,
            authorization=authorization,
            correlation_id=correlation_id,
            causation_id=causation_id,
            purpose=purpose,
            data_class=data_class,
            locale=locale,
            principal_resolver_factory=request_principal_factory,
        )
        return ProductionExperienceRuntimeResolver(
            scope_resolver=scope_resolver,
            session_factory=session_factory,
            gateway=gateway,
            router=router,
            context_broker=context_broker,
            environment=environment,
            model_draft_subject_resolver=model_draft_subject_resolver,
            attempt_sink_factory=attempt_sink_factory,
            safety_sink_factory=safety_sink_factory,
            telemetry_sink_factory=telemetry_sink_factory,
            contract_binding=contract_binding,
            active_release_resolver=active_release_resolver,
        )

    from backend.intelligence.experience.api import get_multimodal_draft_runtime_resolver

    application.dependency_overrides[get_multimodal_draft_runtime_resolver] = (
        resolve_request_runtime
    )


@dataclass(frozen=True, slots=True)
class ProductionExperienceRuntimeResolver(MultimodalDraftRuntimeResolver):
    """Resolve authenticated scope and build a fresh production runtime.

    ``scope_resolver`` is the identity/authorization/consent boundary owned by
    the deployment.  It receives only the URL family id, never request JSON.
    ``ModelGateway`` and ``MultimodalRouter`` are injected so provider admission
    remains centralized and testable.  Attempt and SafetyDecision sinks are
    request-scoped factories, so SQL sessions are opened per operation and no
    request connection is retained by this resolver.
    """

    scope_resolver: ScopeResolver
    session_factory: async_sessionmaker[AsyncSession]
    gateway: ModelGateway
    router: MultimodalRouter
    context_broker: AsyncContextBrokerPort
    environment: str
    model_draft_subject_resolver: DraftSubjectResolver | None = None
    attempt_sink_factory: AttemptSinkFactory | None = None
    safety_sink_factory: SafetySinkFactory | None = None
    telemetry_sink_factory: TelemetrySinkFactory | None = None
    contract_binding: MultimodalContractRegistryBinding | None = None
    active_release_resolver: ActiveFamilyExperienceReleaseResolver | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.environment, str) or not self.environment.strip():
            raise ValueError("production environment is required")
        if self.environment == "test":
            raise ValueError(
                "production experience resolver cannot run in the test environment"
            )
        if not callable(self.scope_resolver):
            raise TypeError("scope_resolver must be callable")
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        if self.active_release_resolver is None:
            object.__setattr__(
                self,
                "active_release_resolver",
                SqlAlchemyActiveFamilyExperienceReleaseResolver(self.session_factory),
            )
        elif not callable(getattr(self.active_release_resolver, "resolve", None)):
            raise TypeError("active_release_resolver must implement resolve()")
        if getattr(self.active_release_resolver, "durability_mode", None) != "DURABLE":
            raise ValueError("production active_release_resolver must be durable")
        if not isinstance(self.gateway, ModelGateway):
            raise TypeError("gateway must be a ModelGateway")
        if self.gateway.safety_runtime is None:
            raise ValueError("production gateway requires SafetyRuntime")
        if self.gateway.budget_runtime is None:
            raise ValueError("production gateway requires a durable ModelBudgetRuntime")
        if self.gateway.budget_runtime.environment != self.environment:
            raise ValueError("production ModelBudgetRuntime environment must match resolver")
        if self.gateway.budget_runtime.store.durability_mode != "DURABLE":
            raise ValueError("production ModelBudgetRuntime store must be durable")
        if self.attempt_sink_factory is None:
            raise ValueError("production gateway requires a durable attempt_sink_factory")
        if not callable(self.attempt_sink_factory):
            raise TypeError("attempt_sink_factory must be callable")
        if self.safety_sink_factory is None:
            raise ValueError("production gateway requires a durable safety_sink_factory")
        if not callable(self.safety_sink_factory):
            raise TypeError("safety_sink_factory must be callable")
        if self.telemetry_sink_factory is None:
            raise ValueError("production gateway requires a durable telemetry_sink_factory")
        if not callable(self.telemetry_sink_factory):
            raise TypeError("telemetry_sink_factory must be callable")
        if not isinstance(self.router, MultimodalRouter):
            raise TypeError("router must be a MultimodalRouter")
        for provider_id in self.router.provider_ids:
            if provider_id not in self.gateway.available_provider_ids():
                raise ValueError(
                    f"multimodal route provider {provider_id!r} has no Model Gateway adapter"
                )
            profile = self.router.profile(provider_id)
            record = self.gateway.registry.get(provider_id)
            if (record.model, record.model_version) != (profile.model, profile.model_version):
                raise ValueError(
                    f"multimodal provider {provider_id!r} model identity differs between "
                    "route catalog and Model Gateway registry"
                )
            adapter_modalities = self.gateway.provider_supported_modalities(provider_id)
            if not set(profile.modalities).issubset(adapter_modalities):
                missing = sorted(set(profile.modalities) - adapter_modalities)
                raise ValueError(
                    f"multimodal provider {provider_id!r} route declares unsupported "
                    f"modalities {missing}"
                )
        if not all(
            callable(getattr(self.context_broker, method_name, None))
            for method_name in ("snapshot", "read")
        ):
            raise TypeError("context_broker must implement snapshot() and read()")
        if getattr(self.context_broker, "durability_mode", "IN_MEMORY") != "DURABLE":
            raise ValueError(
                "production experience resolver requires a durable ContextBroker"
            )
        if self.environment not in PRODUCTION_ENVIRONMENTS:
            raise ValueError(
                "production experience resolver environment must be staging or production"
            )
        if self.contract_binding is None:
            raise ValueError(
                "production experience resolver requires a published contract_binding"
            )
        if self.model_draft_subject_resolver is not None and not callable(
            self.model_draft_subject_resolver
        ):
            raise TypeError("model_draft_subject_resolver must be callable")
        if self.contract_binding is not None and not isinstance(
            self.contract_binding, MultimodalContractRegistryBinding
        ):
            raise TypeError("contract_binding must be a MultimodalContractRegistryBinding")

    async def resolve(self, family_id: str) -> MultimodalDraftRuntime:
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
            raise ValueError("production experience scope cannot be synthetic")
        release_resolver = self.active_release_resolver
        budget_runtime = self.gateway.budget_runtime
        safety_runtime = self.gateway.safety_runtime
        if (  # pragma: no cover - constructor invariants
            release_resolver is None
            or budget_runtime is None
            or safety_runtime is None
        ):
            raise RuntimeError("production release, budget or safety runtime is unavailable")
        active_runtime_binding = await release_resolver.resolve(
            environment=self.environment,
            use_case=scope.purpose,
            data_class=scope.data_class.value,
        )
        validate_active_runtime_binding(
            active_runtime_binding,
            router=self.router,
            budget_runtime=budget_runtime,
            safety_runtime=safety_runtime,
            environment=self.environment,
            use_case=scope.purpose,
            data_class=scope.data_class.value,
        )
        release_set = active_runtime_binding.release_set
        contract_binding = self.contract_binding
        if contract_binding is None:  # pragma: no cover - constructor invariant
            raise RuntimeError("production contract binding is unavailable")
        bound_contract = replace(
            contract_binding,
            release_expectation=ReleaseContractExpectation(
                agent_id=release_set.agent_id,
                prompt_ref=release_set.prompt_ref,
                prompt_version=release_set.prompt_version,
                schema_ref=release_set.schema_ref,
                schema_version=release_set.schema_version,
                safety_policy_version=release_set.safety_policy_version,
                knowledge_refs=release_set.knowledge_refs,
                asset_digest=release_set.asset_digest,
            ),
        )

        application = _RequestScopedMultimodalApplication(
            session_factory=self.session_factory,
            gateway=self.gateway,
            router=self.router,
            context_broker=self.context_broker,
            model_draft_subject_resolver=self.model_draft_subject_resolver,
            attempt_sink_factory=self.attempt_sink_factory,
            safety_sink_factory=self.safety_sink_factory,
            telemetry_sink_factory=self.telemetry_sink_factory,
            active_release_resolver=release_resolver,
            active_runtime_binding=active_runtime_binding,
        )
        ledger = SessionPerCallExperienceRunLedger(self.session_factory)
        # Keep the bridge explicit even though the session-per-call adapter
        # already implements the async lifecycle.  This object is the stable
        # boundary for future legacy adapters and makes the composition choice
        # visible to startup diagnostics.
        bridged_ledger = AsyncExperienceRunLedgerBridge(ledger)
        return MultimodalDraftRuntime(
            scope=scope,
            application=application,
            environment=self.environment,
            run_ledger=bridged_ledger,
            contract_binding=bound_contract,
        )


__all__ = ["ProductionExperienceRuntimeResolver", "install_sql_experience_runtime_wiring"]
