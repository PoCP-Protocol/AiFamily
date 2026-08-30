"""HTTP adapter for the first Family Need vertical slice (N0 → N1).

This adapter accepts a family expression and returns a captured need.  It does
not ask a model to diagnose a child, create a commercial order, or write a
memory.  Identity, tenant and family scope come from an injected actor
resolver; the body cannot override them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..application.ports import NeedSignalInput
from ..application.service import CaptureSignalResult, FamilyNeedApplicationService
from ..domain.errors import (
    FamilyNeedConflictError,
    FamilyNeedDomainError,
    FamilyNeedForbiddenError,
    FamilyNeedNotFoundError,
    FamilyNeedResourceGapError,
    FamilyNeedValidationError,
)
from ..domain.value_objects import (
    DataClass,
    EvidenceKind,
    EvidenceRef,
    NeedCategory,
    NeedContext,
    NeedSignalSource,
)
from .dependencies import FamilyNeedActor, get_family_need_actor, get_family_need_service

router = APIRouter(prefix="/families")


class NeedEvidenceBody(BaseModel):
    """Reference to already-authorized media/text evidence; no raw payload."""

    model_config = ConfigDict(extra="forbid")

    media_ref: str = Field(min_length=1, max_length=256)
    kind: EvidenceKind
    provenance_ref: str = Field(min_length=1, max_length=256)
    consent_version: str = Field(min_length=1, max_length=128)
    data_class: DataClass
    authorized: bool = True
    expires_at: datetime | None = None


class CaptureNeedBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_text: str = Field(min_length=1, max_length=20_000)
    statement: str = Field(min_length=1, max_length=2_000)
    desired_outcome: str = Field(min_length=1, max_length=2_000)
    source: NeedSignalSource
    purpose: str = Field(min_length=1, max_length=64)
    consent_version: str = Field(min_length=1, max_length=128)
    data_class: DataClass
    locale: str = Field(default="zh-CN", min_length=2, max_length=16)
    subject_person_ids: tuple[str, ...] = ()
    category: NeedCategory = NeedCategory.EDUCATION
    provenance_ref: str | None = Field(default=None, max_length=256)
    causation_id: str | None = Field(default=None, max_length=128)
    signal_id: str | None = Field(default=None, max_length=128)
    expires_at: datetime | None = None
    evidence_refs: tuple[NeedEvidenceBody, ...] = ()


def register_exception_handlers(app: FastAPI) -> None:
    statuses = {
        FamilyNeedValidationError: 400,
        FamilyNeedForbiddenError: 403,
        FamilyNeedNotFoundError: 404,
        FamilyNeedConflictError: 409,
        FamilyNeedResourceGapError: 409,
    }

    @app.exception_handler(FamilyNeedDomainError)
    async def _handle_family_need_error(request, error: FamilyNeedDomainError) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=statuses.get(type(error), 400), content={"detail": error.code}
        )


def _assert_actor_scope(actor: FamilyNeedActor, family_id: str) -> None:
    if actor.family_id != family_id:
        raise HTTPException(status_code=403, detail="family_access_denied")


def _require_idempotency(value: str | None) -> str:
    if value is None or not value.strip() or len(value) > 128:
        raise HTTPException(status_code=400, detail="invalid_idempotency_key")
    return value.strip()


def _to_context(
    body: CaptureNeedBody,
    actor: FamilyNeedActor,
    *,
    correlation_id: str | None,
) -> NeedContext:
    return NeedContext(
        tenant_id=actor.tenant_id,
        family_id=actor.family_id,
        purpose=body.purpose,
        consent_version=body.consent_version,
        data_class=body.data_class,
        locale=body.locale,
        # Region and environment are process/identity derived. A client body
        # must not move a record across regional cells or select production
        # semantics.
        region=actor.region,
        subject_person_ids=body.subject_person_ids,
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        global_id=f"need-request:{uuid4()}",
        source_system="aifamily-family-api",
        environment=actor.environment,
        provenance_ref=body.provenance_ref,
        correlation_id=correlation_id or str(uuid4()),
        causation_id=body.causation_id,
    )


def _to_evidence(body: NeedEvidenceBody, actor: FamilyNeedActor) -> EvidenceRef:
    return EvidenceRef(
        media_ref=body.media_ref,
        kind=body.kind,
        tenant_id=actor.tenant_id,
        family_id=actor.family_id,
        provenance_ref=body.provenance_ref,
        consent_version=body.consent_version,
        data_class=body.data_class,
        authorized=body.authorized,
        expires_at=body.expires_at,
    )


def _serialize(result: CaptureSignalResult) -> dict:
    signal = result.signal
    need = result.need
    return {
        "action": "CAPTURE_FAMILY_NEED",
        "replayed": result.replayed,
        "boundary": "FAMILY_EXPRESSION_NOT_AI_DIAGNOSIS",
        "signal": {
            "signal_id": signal.signal_id,
            "source": signal.source.value,
            "raw_text": signal.raw_text,
            "captured_at": signal.captured_at.isoformat(),
            "status": signal.status.value,
            "tenant_id": signal.tenant_id,
            "family_id": signal.family_id,
            "subject_person_ids": list(signal.context.subject_person_ids),
        },
        "need": {
            "need_id": need.need_id,
            "status": need.status.value,
            "emotional_gate": need.emotional_gate.value,
            "statement": need.statement,
            "desired_outcome": need.desired_outcome,
            "category": need.category.value,
            "version": need.version,
            "tenant_id": need.tenant_id,
            "family_id": need.family_id,
            "subject_person_ids": list(need.subject_person_ids),
            "source_signal_ids": list(need.source_signal_ids),
        },
    }


@router.post("/{family_id}/needs/signals", status_code=201)
async def capture_family_need(
    family_id: str,
    body: CaptureNeedBody,
    actor: Annotated[FamilyNeedActor, Depends(get_family_need_actor)],
    service: Annotated[FamilyNeedApplicationService, Depends(get_family_need_service)],
    idempotency_key: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> dict:
    """Capture N0 and create the N1 need aggregate."""

    _assert_actor_scope(actor, family_id)
    context = _to_context(body, actor, correlation_id=x_correlation_id)
    result = await service.capture_signal(
        NeedSignalInput(
            context=context,
            raw_text=body.raw_text,
            source=body.source,
            signal_id=body.signal_id,
            expires_at=body.expires_at,
            subject_person_ids=body.subject_person_ids,
            statement=body.statement,
            desired_outcome=body.desired_outcome,
            category=body.category,
            idempotency_key=_require_idempotency(idempotency_key),
            evidence_refs=tuple(_to_evidence(item, actor) for item in body.evidence_refs),
        )
    )
    return _serialize(result)


__all__ = ["CaptureNeedBody", "NeedEvidenceBody", "register_exception_handlers", "router"]
