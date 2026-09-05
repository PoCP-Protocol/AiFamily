"""Standalone HTTP adapter for ``VS-GROWTH-01`` signal acceptance.

The canonical ``family_api`` composition root is owned by another workstream,
so this module exports a dependency-injected router instead of modifying the
shared ``routes.py`` or any environment wiring.  A production composition root
must provide a real actor resolver and an ``AsyncEngine.begin()`` repository
context.  The handler itself keeps the same 401/403/404/409/400 refusal
semantics as the domain contract and appends audit/outbox only inside the
repository transaction.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from backend.platform.consent import ConsentGrant, ConsentPurpose

from ..application.outcome_loop import GrowthOutcomeLoop
from ..application.s01_vertical_slice import (
    InMemoryAssessmentSignalPort,
    S01VerticalSlice,
)
from ..domain.errors import (
    JourneyConflictError,
    JourneyDomainError,
    JourneyForbiddenError,
    JourneyNotFoundError,
    JourneyValidationError,
)
from ..infrastructure.s01_postgres import S01PostgresAssessmentRepository


@dataclass(frozen=True, slots=True)
class S01ActorContext:
    """Trusted identity + tenant context returned by the composition root."""

    actor_id: str
    tenant_id: str
    family_id: str


class S01ActorResolver(Protocol):
    async def __call__(self, authorization: str | None, family_id: str) -> S01ActorContext: ...


RepositoryContext = Callable[[], AbstractAsyncContextManager[S01PostgresAssessmentRepository]]


@dataclass(frozen=True, slots=True)
class S01HttpDependencies:
    """Ports required by the standalone route; no global state is hidden."""

    resolve_actor: S01ActorResolver
    open_repository: RepositoryContext


class AcceptSignalBody(BaseModel):
    locale: str = "zh-CN"


def build_vs_growth_01_router(dependencies: S01HttpDependencies) -> APIRouter:
    """Build a router that can be mounted by a trusted application root."""

    router = APIRouter(prefix="/families")

    @router.post("/{family_id}/growth/vs-growth-01/signals/{assessment_session_id}/accept")
    async def accept_signal(
        family_id: str,
        assessment_session_id: str,
        body: AcceptSignalBody,
        authorization: Annotated[str | None, Header()] = None,
        x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-Id")] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        x_correlation_id: Annotated[str | None, Header(alias="X-Correlation-Id")] = None,
    ) -> dict:
        if idempotency_key is None or not idempotency_key.strip():
            raise HTTPException(status_code=400, detail="invalid_idempotency_key")
        try:
            actor = await dependencies.resolve_actor(authorization, family_id)
            _assert_actor_scope(actor, family_id, x_tenant_id)
            _assert_uuid(assessment_session_id, "assessment_session_id")
            async with dependencies.open_repository() as repository:
                signal = await repository.load_submitted_signal(
                    tenant_id=actor.tenant_id,
                    family_id=family_id,
                    assessment_session_id=assessment_session_id,
                    locale=body.locale,
                )
                if signal is None:
                    raise JourneyNotFoundError("submitted_assessment_signal_not_found")
                grants_by_purpose = {
                    purpose: await repository.load_consent_grants(
                        family_id=family_id,
                        subject_person_id=signal.subject_ref,
                        purpose=purpose,
                    )
                    for purpose in ConsentPurpose
                }

                def consent_loader(
                    subject: str, purpose: ConsentPurpose
                ) -> tuple[ConsentGrant, ...]:
                    if subject != signal.subject_ref:
                        return ()
                    return grants_by_purpose[purpose]

                slice_ = S01VerticalSlice(
                    signal_port=InMemoryAssessmentSignalPort((signal,)),
                    outcome_loop=GrowthOutcomeLoop(consent_loader=consent_loader),
                    consent_loader=consent_loader,
                    locale=body.locale,
                )
                accepted = slice_.accept_signal(
                    tenant_id=actor.tenant_id,
                    family_id=family_id,
                    assessment_session_id=assessment_session_id,
                    actor_id=actor.actor_id,
                    idempotency_key=idempotency_key,
                    correlation_id=x_correlation_id or idempotency_key,
                )
                response = {
                    "capability_id": "VS-GROWTH-01",
                    "stage": "SIGNAL_ACCEPTED",
                    "signal_id": accepted.signal_id,
                    "assessment_session_id": accepted.assessment_session_id,
                    "tenant_id": accepted.tenant_id,
                    "family_id": accepted.family_id,
                    "evidence_refs": list(accepted.evidence_refs),
                    "locale": accepted.locale,
                    "boundary": "ASSESSMENT_SUBMITTED_EVIDENCE_NOT_FACT",
                }
                persisted, replay = await repository.append_signal_acceptance(
                    signal=accepted,
                    actor_id=actor.actor_id,
                    idempotency_key=idempotency_key,
                    correlation_id=x_correlation_id or idempotency_key,
                    response=response,
                )
                return {**persisted, "replayed": replay}
        except HTTPException:
            raise
        except JourneyForbiddenError as error:
            raise HTTPException(status_code=403, detail=error.code) from error
        except JourneyNotFoundError as error:
            raise HTTPException(status_code=404, detail=error.code) from error
        except JourneyConflictError as error:
            raise HTTPException(status_code=409, detail=error.code) from error
        except JourneyValidationError as error:
            raise HTTPException(status_code=400, detail=error.code) from error
        except JourneyDomainError as error:
            raise HTTPException(status_code=400, detail=error.code) from error

    return router


def _assert_actor_scope(actor: S01ActorContext, family_id: str, tenant_id: str | None) -> None:
    if actor.family_id != family_id:
        raise JourneyForbiddenError("family_tenant_scope_violation")
    if tenant_id is None or tenant_id != actor.tenant_id:
        raise JourneyForbiddenError("tenant_scope_required")


def _assert_uuid(value: str, name: str) -> None:
    try:
        UUID(value)
    except (ValueError, AttributeError, TypeError) as error:
        raise JourneyValidationError(f"{name}_must_be_uuid") from error


__all__ = [
    "AcceptSignalBody",
    "S01ActorContext",
    "S01ActorResolver",
    "S01HttpDependencies",
    "build_vs_growth_01_router",
]
