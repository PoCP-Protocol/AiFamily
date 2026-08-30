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
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.intelligence.context_engine.contracts import ContextScope
from backend.intelligence.context_engine.store import ContextBroker
from backend.intelligence.experience.api import (
    MultimodalDraftApplication,
    MultimodalDraftRuntime,
    MultimodalDraftRuntimeResolver,
)
from backend.intelligence.experience.async_ledger_bridge import (
    AsyncExperienceRunLedgerBridge,
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
from backend.intelligence.experience.sql_run_ledger import (
    SessionPerCallExperienceRunLedger,
)
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provenance import (
    SqlAlchemyModelDraftRegistry,
)
from backend.platform.persistence.unit_of_work import SqlAlchemyUnitOfWork

ScopeResolver = Callable[[str], ContextScope | Awaitable[ContextScope]]
DraftSubjectResolver = Callable[[ContextScope], str | None]
PRODUCTION_ENVIRONMENTS = frozenset({"staging", "production"})


@dataclass(frozen=True, slots=True)
class _RequestScopedMultimodalApplication(MultimodalDraftApplication):
    """Use one short-lived SQL session for the model-draft transaction."""

    session_factory: async_sessionmaker[AsyncSession]
    gateway: ModelGateway
    router: MultimodalRouter
    context_broker: ContextBroker
    model_draft_subject_resolver: DraftSubjectResolver | None

    async def generate_draft(
        self, command: ContextBoundMultimodalCommand
    ) -> ContextBoundMultimodalDraft:
        async with SqlAlchemyUnitOfWork(self.session_factory) as unit_of_work:
            session = unit_of_work.session
            if session is None:  # pragma: no cover - UoW contract guard
                raise RuntimeError("production experience UoW did not open a session")
            registry = SqlAlchemyModelDraftRegistry(session)
            application = ContextBoundMultimodalExperienceService(
                context=self.context_broker,
                routed=RoutedMultimodalExperienceService(
                    router=self.router,
                    generation=MultimodalExperienceService(
                        self.gateway,
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
    from dataclasses import replace

    return replace(command, model_draft_subject_id=subject_id)


@dataclass(frozen=True, slots=True)
class ProductionExperienceRuntimeResolver(MultimodalDraftRuntimeResolver):
    """Resolve authenticated scope and build a fresh production runtime.

    ``scope_resolver`` is the identity/authorization/consent boundary owned by
    the deployment.  It receives only the URL family id, never request JSON.
    ``ModelGateway`` and ``MultimodalRouter`` are injected so provider admission
    remains centralized and testable.  SQL sessions are opened per operation;
    no request connection is retained by this resolver.
    """

    scope_resolver: ScopeResolver
    session_factory: async_sessionmaker[AsyncSession]
    gateway: ModelGateway
    router: MultimodalRouter
    context_broker: ContextBroker
    environment: str
    model_draft_subject_resolver: DraftSubjectResolver | None = None

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
        if not isinstance(self.gateway, ModelGateway):
            raise TypeError("gateway must be a ModelGateway")
        if not isinstance(self.router, MultimodalRouter):
            raise TypeError("router must be a MultimodalRouter")
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
        if self.model_draft_subject_resolver is not None and not callable(
            self.model_draft_subject_resolver
        ):
            raise TypeError("model_draft_subject_resolver must be callable")

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

        application = _RequestScopedMultimodalApplication(
            session_factory=self.session_factory,
            gateway=self.gateway,
            router=self.router,
            context_broker=self.context_broker,
            model_draft_subject_resolver=self.model_draft_subject_resolver,
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
        )


__all__ = ["ProductionExperienceRuntimeResolver"]
