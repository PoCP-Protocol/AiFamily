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

from ..application.ports import (
    NeedClarificationInput,
    NeedProfileInput,
    NeedSignalInput,
    SolutionDraftInput,
)
from ..application.service import (
    CaptureSignalResult,
    ClarifyNeedResult,
    FamilyNeedApplicationService,
    ProfileNeedResult,
    SolutionDraftResult,
)
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
    NeedComplexity,
    NeedContext,
    NeedSignalSource,
    NeedUrgency,
    ResourceGap,
    RiskLevel,
    SolutionComponentRef,
    SupplyShape,
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


class ClarifyNeedBody(BaseModel):
    """Human-confirmed N1 statement; identity and deployment scope are server side."""

    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1, max_length=2_000)
    desired_outcome: str = Field(min_length=1, max_length=2_000)
    expected_version: int = Field(ge=1)
    purpose: str = Field(min_length=1, max_length=64)
    consent_version: str = Field(min_length=1, max_length=128)
    data_class: DataClass
    locale: str = Field(default="zh-CN", min_length=2, max_length=16)
    subject_person_ids: tuple[str, ...] = ()


class ProfileNeedBody(BaseModel):
    """N2 profile inputs; classification is not a family score or ranking."""

    model_config = ConfigDict(extra="forbid")

    expected_need_version: int = Field(ge=1)
    urgency: NeedUrgency
    complexity: NeedComplexity
    risk_level: RiskLevel
    preferred_shapes: tuple[SupplyShape, ...] = Field(min_length=1)
    required_capability_keys: tuple[str, ...] = ()
    purpose: str = Field(min_length=1, max_length=64)
    consent_version: str = Field(min_length=1, max_length=128)
    data_class: DataClass
    locale: str = Field(default="zh-CN", min_length=2, max_length=16)
    subject_person_ids: tuple[str, ...] = ()


class SolutionComponentBody(BaseModel):
    """Versioned read-only reference into product/service/solution catalogs."""

    model_config = ConfigDict(extra="forbid")

    component_id: str = Field(min_length=1, max_length=256)
    shape: SupplyShape
    version: str = Field(min_length=1, max_length=128)
    required: bool = True
    quantity: int = Field(default=1, ge=1, le=10_000)


class SolutionDraftBody(BaseModel):
    """Compose a draft; execution, booking and payment remain other contexts."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(min_length=1, max_length=128)
    expected_profile_version: int = Field(ge=1)
    shape: SupplyShape
    component_refs: tuple[SolutionComponentBody, ...] = Field(min_length=1)
    commercial_intent: bool = False
    purpose: str = Field(min_length=1, max_length=64)
    consent_version: str = Field(min_length=1, max_length=128)
    data_class: DataClass
    locale: str = Field(default="zh-CN", min_length=2, max_length=16)
    subject_person_ids: tuple[str, ...] = ()


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


def _to_operation_context(
    *,
    purpose: str,
    consent_version: str,
    data_class: DataClass,
    locale: str,
    subject_person_ids: tuple[str, ...],
    actor: FamilyNeedActor,
    correlation_id: str | None,
) -> NeedContext:
    """Build a command context from server identity plus explicit consent."""

    return NeedContext(
        tenant_id=actor.tenant_id,
        family_id=actor.family_id,
        purpose=purpose,
        consent_version=consent_version,
        data_class=data_class,
        locale=locale,
        region=actor.region,
        subject_person_ids=subject_person_ids,
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        global_id=f"need-operation:{uuid4()}",
        source_system="aifamily-family-api",
        environment=actor.environment,
        correlation_id=correlation_id or str(uuid4()),
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


def _serialize_need(need) -> dict:
    return {
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
    }


def _serialize_profile(profile) -> dict:
    return {
        "profile_id": profile.profile_id,
        "need_id": profile.need_id,
        "need_version": profile.need_version,
        "version": profile.version,
        "category": profile.category.value,
        "urgency": profile.urgency.value,
        "complexity": profile.complexity.value,
        "risk_level": profile.risk_level.value,
        "preferred_shapes": [shape.value for shape in profile.preferred_shapes],
        "required_capability_keys": list(profile.required_capability_keys),
        "tenant_id": profile.tenant_id,
        "family_id": profile.family_id,
        "subject_person_ids": list(profile.context.subject_person_ids),
    }


def _serialize_component(component: SolutionComponentRef) -> dict:
    return {
        "component_id": component.component_id,
        "shape": component.shape.value,
        "version": component.version,
        "required": component.required,
        "quantity": component.quantity,
    }


def _serialize_gap(gap: ResourceGap | None) -> dict | None:
    if gap is None:
        return None
    return {
        "need_id": gap.need_id,
        "reason": gap.reason.value,
        "detail": gap.detail,
        "observed_at": gap.observed_at.isoformat(),
    }


def _serialize_clarify(result: ClarifyNeedResult) -> dict:
    return {
        "action": "CONFIRM_FAMILY_NEED",
        "replayed": result.replayed,
        "boundary": "FAMILY_CONFIRMED_NEED_NOT_AI_DIAGNOSIS",
        "need": _serialize_need(result.need),
    }


def _serialize_profile_result(result: ProfileNeedResult) -> dict:
    return {
        "action": "PROFILE_FAMILY_NEED",
        "replayed": result.replayed,
        "boundary": "NEED_PROFILE_NOT_FAMILY_SCORE",
        "profile": _serialize_profile(result.profile),
    }


def _serialize_solution(result: SolutionDraftResult) -> dict:
    draft = result.draft
    return {
        "action": "DRAFT_FAMILY_SOLUTION",
        "replayed": result.replayed,
        "boundary": "REFERENCES_ONLY_NO_BOOKING_OR_PAYMENT",
        "draft": (
            {
                "draft_id": draft.draft_id,
                "need_id": draft.need_id,
                "need_profile_id": draft.need_profile_id,
                "profile_version": draft.profile_version,
                "shape": draft.shape.value,
                "status": draft.status.value,
                "emotional_gate": draft.emotional_gate.value,
                "commercial_intent": draft.commercial_intent,
                "tenant_id": draft.tenant_id,
                "family_id": draft.family_id,
                "components": [_serialize_component(item) for item in draft.components],
            }
            if draft is not None
            else None
        ),
        "resource_gap": _serialize_gap(result.resource_gap),
        "resolved_components": [
            _serialize_component(item) for item in result.resolved_components
        ],
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


@router.post("/{family_id}/needs/{need_id}/clarify")
@router.post("/{family_id}/needs/{need_id}/clarification", include_in_schema=False)
async def clarify_family_need(
    family_id: str,
    need_id: str,
    body: ClarifyNeedBody,
    actor: Annotated[FamilyNeedActor, Depends(get_family_need_actor)],
    service: Annotated[FamilyNeedApplicationService, Depends(get_family_need_service)],
    idempotency_key: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> dict:
    """Confirm N1 with an explicit family statement and desired outcome."""

    _assert_actor_scope(actor, family_id)
    context = _to_operation_context(
        purpose=body.purpose,
        consent_version=body.consent_version,
        data_class=body.data_class,
        locale=body.locale,
        subject_person_ids=body.subject_person_ids,
        actor=actor,
        correlation_id=x_correlation_id,
    )
    result = await service.clarify_need_result(
        NeedClarificationInput(
            need_id=need_id,
            context=context,
            statement=body.statement,
            desired_outcome=body.desired_outcome,
            subject_person_ids=body.subject_person_ids,
            expected_version=body.expected_version,
            idempotency_key=_require_idempotency(idempotency_key),
        )
    )
    return _serialize_clarify(result)


@router.post("/{family_id}/needs/{need_id}/profile")
@router.post("/{family_id}/needs/{need_id}/profiles", include_in_schema=False)
async def profile_family_need(
    family_id: str,
    need_id: str,
    body: ProfileNeedBody,
    actor: Annotated[FamilyNeedActor, Depends(get_family_need_actor)],
    service: Annotated[FamilyNeedApplicationService, Depends(get_family_need_service)],
    idempotency_key: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> dict:
    """Create N2 profile attributes without producing a family score/rank."""

    _assert_actor_scope(actor, family_id)
    context = _to_operation_context(
        purpose=body.purpose,
        consent_version=body.consent_version,
        data_class=body.data_class,
        locale=body.locale,
        subject_person_ids=body.subject_person_ids,
        actor=actor,
        correlation_id=x_correlation_id,
    )
    result = await service.profile_need_result(
        NeedProfileInput(
            need_id=need_id,
            context=context,
            expected_need_version=body.expected_need_version,
            urgency=body.urgency,
            complexity=body.complexity,
            risk_level=body.risk_level,
            preferred_shapes=body.preferred_shapes,
            required_capability_keys=body.required_capability_keys,
            idempotency_key=_require_idempotency(idempotency_key),
        )
    )
    return _serialize_profile_result(result)


@router.post("/{family_id}/needs/{need_id}/solution-drafts")
@router.post("/{family_id}/needs/{need_id}/solutions/drafts", include_in_schema=False)
async def draft_family_solution(
    family_id: str,
    need_id: str,
    body: SolutionDraftBody,
    actor: Annotated[FamilyNeedActor, Depends(get_family_need_actor)],
    service: Annotated[FamilyNeedApplicationService, Depends(get_family_need_service)],
    idempotency_key: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> dict:
    """Compose product/service/solution references and expose resource gaps."""

    _assert_actor_scope(actor, family_id)
    context = _to_operation_context(
        purpose=body.purpose,
        consent_version=body.consent_version,
        data_class=body.data_class,
        locale=body.locale,
        subject_person_ids=body.subject_person_ids,
        actor=actor,
        correlation_id=x_correlation_id,
    )
    result = await service.draft_solution(
        SolutionDraftInput(
            need_id=need_id,
            profile_id=body.profile_id,
            context=context,
            expected_profile_version=body.expected_profile_version,
            shape=body.shape,
            component_refs=tuple(
                SolutionComponentRef(
                    component_id=item.component_id,
                    shape=item.shape,
                    version=item.version,
                    required=item.required,
                    quantity=item.quantity,
                )
                for item in body.component_refs
            ),
            commercial_intent=body.commercial_intent,
            idempotency_key=_require_idempotency(idempotency_key),
        )
    )
    return _serialize_solution(result)


__all__ = [
    "CaptureNeedBody",
    "ClarifyNeedBody",
    "NeedEvidenceBody",
    "ProfileNeedBody",
    "SolutionComponentBody",
    "SolutionDraftBody",
    "register_exception_handlers",
    "router",
]
