"""Dependency seams for the FGCN Human Gate HTTP control plane.

The route layer intentionally does not construct identity, scope, a database
session, or a business repository.  Production wiring must provide all of
those explicitly.  Until the account/tenant/family stores are connected, the
defaults fail closed with a configuration error instead of inventing a family
or treating a request body as trusted identity.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Protocol

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.domains.service.api import dependencies as service_dependencies
from backend.domains.service.application.context import ActionContext
from backend.intelligence.human_gate import ActorType as GateActorType
from backend.intelligence.human_gate import SqlAlchemyHumanGate
from backend.intelligence.human_gate.contracts import HUMAN_ACTOR_TYPES
from backend.intelligence.model_gateway.contracts import ModelDraft
from backend.intelligence.model_gateway.provenance import (
    ModelDraftNotFound as DraftProvenanceNotFound,
)
from backend.intelligence.model_gateway.provenance import (
    SqlAlchemyModelDraftRegistry,
    StoredModelDraft,
)
from backend.platform.audit import AuditRecorder
from backend.platform.identity.context import ActorContext

from ..admission import AsyncProviderAdmissionQuery
from ..persistence import SqlAlchemyFGCNRepository


@dataclass(frozen=True, slots=True)
class HumanReviewerContext:
    """Trusted reviewer identity resolved by the platform identity boundary."""

    actor_id: str
    actor_type: GateActorType
    tenant_id: str

    def __post_init__(self) -> None:
        if not self.actor_id or not self.tenant_id:
            raise ValueError("HumanReviewerContext actor_id and tenant_id are required")
        actor_type = GateActorType(self.actor_type)
        if actor_type not in HUMAN_ACTOR_TYPES:
            raise ValueError("HumanReviewerContext must contain a human actor type")
        object.__setattr__(self, "actor_type", actor_type)


class DraftProvenanceResolver(Protocol):
    """Resolve a stored ModelDraft and verify it belongs to the request scope."""

    async def resolve(
        self,
        provenance_ref: str,
        *,
        tenant_id: str,
        family_id: str,
        subject_person_id: str,
        purpose: str,
        correlation_id: str,
    ) -> ModelDraft: ...

    async def resolve_stored(
        self,
        provenance_ref: str,
        *,
        tenant_id: str,
        family_id: str,
        subject_person_id: str,
        purpose: str,
        correlation_id: str,
    ) -> StoredModelDraft: ...


_session_factory: async_sessionmaker[AsyncSession] | None = None


def configure_session_factory(
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> None:
    """Install the process session factory during application startup.

    This setter is deliberately explicit.  It is not called at import time and
    has no default, because silently falling back to a local database would
    make an API appear available while its state is not the canonical database.
    Passing ``None`` deliberately unbinds the seam for an app without an
    explicit database configuration.
    """

    global _session_factory
    _session_factory = session_factory


def clear_session_factory() -> None:
    """Remove process wiring when an app instance has no database configured.

    ``create_app`` is called more than once in tests and by some deployment
    tooling.  Leaving the previous app's factory in this module-global seam
    would make a later production app inherit a stale database connection
    instead of failing closed.  This is intentionally explicit rather than a
    lazy fallback to SQLite.
    """

    configure_session_factory(None)


async def get_fgcn_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield one request session shared by the gate and FGCN repository."""

    if _session_factory is None:
        raise RuntimeError(
            "FGCN session factory not configured — production persistence wiring is required"
        )
    async with _session_factory() as session:
        yield session


async def get_fgcn_repository(
    session: AsyncSession = Depends(get_fgcn_session),
) -> SqlAlchemyFGCNRepository:
    return SqlAlchemyFGCNRepository(session)


async def get_human_gate(
    session: AsyncSession = Depends(get_fgcn_session),
) -> SqlAlchemyHumanGate:
    return SqlAlchemyHumanGate(session)


async def get_action_context(
    context: ActionContext = Depends(service_dependencies.get_action_context),
) -> ActionContext:
    """Reuse the service identity/scope resolver; do not parse URL/body scope."""

    return context


async def get_actor_context(
    actor: ActorContext = Depends(service_dependencies.get_actor_context),
) -> ActorContext:
    """Reuse the trusted platform actor resolver."""

    return actor


def get_human_reviewer_context() -> HumanReviewerContext:
    """Production identity/role resolver; no permissive default exists yet."""

    raise RuntimeError(
        "FGCN human reviewer identity not configured — actor and reviewer role "
        "must come from the trusted identity service"
    )


def get_draft_provenance_resolver(
    session: AsyncSession = Depends(get_fgcn_session),
) -> DraftProvenanceResolver:
    """Resolve drafts from the durable AI-runtime registry.

    The registry is deliberately constructed from the same request session as
    the FGCN repository and Human Gate.  If the process has no explicit
    database wiring, ``get_fgcn_session`` fails closed before a client string
    can be treated as provenance.
    """

    return SqlAlchemyModelDraftRegistry(session)


def get_workflow_worker_context() -> ActorContext:
    """Production worker authentication seam; clients cannot self-identify."""

    raise RuntimeError(
        "FGCN workflow worker identity not configured — internal worker auth is required"
    )


def get_provider_admission() -> AsyncProviderAdmissionQuery:
    """Production provider admission query; no permissive default exists."""

    raise RuntimeError(
        "FGCN provider admission not configured — provider qualification and capability "
        "must come from the trusted service/provider boundary"
    )


def get_audit_recorder() -> AuditRecorder:
    """Use a request-local buffer so concurrent requests cannot share events."""

    return AuditRecorder()


__all__ = [
    "HumanReviewerContext",
    "configure_session_factory",
    "clear_session_factory",
    "DraftProvenanceNotFound",
    "DraftProvenanceResolver",
    "get_action_context",
    "get_actor_context",
    "get_audit_recorder",
    "get_fgcn_repository",
    "get_fgcn_session",
    "get_human_gate",
    "get_draft_provenance_resolver",
    "get_human_reviewer_context",
    "get_workflow_worker_context",
    "get_provider_admission",
]
