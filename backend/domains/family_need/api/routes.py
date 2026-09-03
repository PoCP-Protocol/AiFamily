"""HTTP adapter for the first Family Need vertical slice (N0 → N1).

This adapter accepts a family expression and returns a captured need.  It does
not ask a model to diagnose a child, create a commercial order, or write a
memory.  Identity, tenant and family scope come from an injected actor
resolver; the body cannot override them.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.domains.product_intelligence.application.family_experience_signal import (
    record_family_experience_signal,
)
from backend.domains.product_intelligence.application.improvement_candidate import (
    record_improvement_candidate,
)
from backend.intelligence.model_gateway.errors import ModelGatewayError

from ..application.ai_coach import request_coach_perspective
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
    FamilyOutcomeDecision,
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
from .ai_coach_dependencies import AiCoachDeps, get_ai_coach_deps
from .dependencies import FamilyNeedActor, get_family_need_actor, get_family_need_service
from .fulfillment_dependencies import (
    FulfillmentDeps,
    get_fulfillment_deps,
)

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
        "intervention_tier": profile.intervention_tier.value,
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
                # Set only when the profile's intervention_tier is
                # ENHANCED_SUPPORT (Triple P Level 5): the draft is flagged
                # for mandatory human case review and must not be treated as
                # ready to auto-fulfill by any caller.
                "requires_human_case_review": draft.requires_human_case_review,
                "human_case_review_note": draft.human_case_review_note,
            }
            if draft is not None
            else None
        ),
        "resource_gap": _serialize_gap(result.resource_gap),
        "resolved_components": [_serialize_component(item) for item in result.resolved_components],
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


class ConfirmSolutionDraftBody(BaseModel):
    """The family's go-ahead: approve the draft and, if commercial_intent was
    set when the draft was proposed, push it into a real order/booking."""

    model_config = ConfigDict(extra="forbid")

    subject_person_id: str = Field(min_length=1, max_length=256)


class CompleteAndReviewBody(BaseModel):
    """Mark one booked service session delivered and leave a growth-journey
    trace of it. `day_number` anchors the touchpoint on the outcome loop's
    21-day action window (`journey.application.outcome_loop`); it is not a
    score."""

    model_config = ConfigDict(extra="forbid")

    day_number: int = Field(ge=1, le=21, default=1)
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=32)


def _serialize_fulfillment(result) -> dict:
    return {
        "action": "FULFIL_CONFIRMED_SOLUTION_DRAFT",
        "boundary": "NO_DISTRIBUTED_TRANSACTION_COMPENSATION_GAPS_ARE_REPORTED_NOT_HIDDEN",
        "draft_id": result.draft_id,
        "order_intent_id": result.order_intent_id,
        "entitlement_id": result.entitlement_id,
        "booking_id": result.booking_id,
        "booking_service_record_id": result.booking_service_record_id,
        "availability_slot_id": result.availability_slot_id,
        "succeeded": result.succeeded,
        "failed_step": result.failed_step,
        "failure_reason": result.failure_reason,
        # Populated only when this fulfilment found a real self-help-failed
        # (N6/N7 DID_NOT_HELP) outcome and therefore routed the real-teacher
        # match through FGCN's AI-suggests/human-approves gate before
        # booking. `None` on all four means no such evidence existed and the
        # booking proceeded exactly as it did before FGCN was wired in.
        "fgcn_case_id": result.fgcn_case_id,
        "fgcn_task_id": result.fgcn_task_id,
        "fgcn_assignment_id": result.fgcn_assignment_id,
        "fgcn_assignee_ref": result.fgcn_assignee_ref,
    }


@router.post("/{family_id}/needs/{need_id}/solution-drafts/{draft_id}/confirm")
async def confirm_solution_draft(
    family_id: str,
    need_id: str,
    draft_id: str,
    body: ConfirmSolutionDraftBody,
    actor: Annotated[FamilyNeedActor, Depends(get_family_need_actor)],
    service: Annotated[FamilyNeedApplicationService, Depends(get_family_need_service)],
    fulfillment: Annotated[FulfillmentDeps, Depends(get_fulfillment_deps)],
    idempotency_key: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> dict:
    """Approve N3 and, if the family signalled commercial intent, fulfil it.

    Approval and fulfilment happen in one request because a draft that is
    approved but never pushed to commerce/service would leave the family
    looking confirmed with nothing actually booked. Fulfilment failure does
    not un-approve the draft: the family did confirm, that fact stands, and
    the failure is reported explicitly instead.
    """

    _assert_actor_scope(actor, family_id)
    correlation_id = x_correlation_id or _require_idempotency(idempotency_key)
    key = _require_idempotency(idempotency_key)

    draft = await service._repository.get_solution_draft(
        tenant_id=actor.tenant_id, family_id=family_id, draft_id=draft_id
    )
    if draft is None:
        raise HTTPException(status_code=404, detail="solution_draft_not_found")
    if draft.need_id != need_id:
        raise HTTPException(status_code=409, detail="solution_draft_need_mismatch")

    if draft.status.value == "DRAFT":
        profile = await service._repository.get_profile(
            tenant_id=actor.tenant_id, family_id=family_id, profile_id=draft.need_profile_id
        )
        if profile is None:
            raise HTTPException(status_code=409, detail="need_profile_not_found")
        draft = draft.submit_for_family_review(profile=profile)
    if draft.status.value == "FAMILY_REVIEW":
        # Apply both transitions to the in-memory draft before the single
        # `save_solution_draft` call below. Persisting after each transition
        # would call `save_solution_draft` twice in the same request with two
        # `updated_at=utcnow()` stamps that can collide at this platform's
        # clock resolution — the repository's replay guard would then compare
        # the pre- and post-approval drafts under an identical timestamp and
        # raise a false-positive `solution_draft_replay_mismatch`. One save
        # with the final state avoids that race entirely.
        draft = draft.approve(actor.actor_id, actor.actor_type)
        await service._repository.save_solution_draft(draft)
    elif draft.status.value != "APPROVED":
        raise HTTPException(
            status_code=409, detail=f"solution_draft_not_confirmable:{draft.status.value}"
        )

    if not draft.commercial_intent:
        return {
            "action": "CONFIRM_SOLUTION_DRAFT",
            "boundary": "APPROVED_ONLY_NO_COMMERCIAL_INTENT_NOTHING_ORDERED_OR_BOOKED",
            "draft": _serialize_component_draft(draft),
            "fulfillment": None,
        }

    # N4: record the assignment decision itself as a queryable fact — which
    # resources this need was matched to, and on what authority — before
    # anything is pushed to commerce/service_booking. Previously this only
    # existed implicitly inside `fulfil_confirmed_draft`'s call arguments.
    assignment_context = _to_operation_context(
        purpose="FAMILY_NEED",
        consent_version="v1",
        data_class=DataClass.MINOR_PERSONAL_DATA,
        locale="zh-CN",
        subject_person_ids=(body.subject_person_id,),
        actor=actor,
        correlation_id=correlation_id,
    )
    assignment_plan = await service.create_assignment_plan(context=assignment_context, draft=draft)

    result = await fulfillment.fulfil_confirmed_draft(
        draft,
        commerce_service=fulfillment.commerce_repository,
        service_booking_service=fulfillment.service_repository,
        consent_query=fulfillment.consent_query,
        audit_recorder=fulfillment.audit_recorder,
        actor=actor.actor_id,
        actor_person_id=actor.actor_id,
        subject_person_id=body.subject_person_id,
        correlation_id=correlation_id,
        idempotency_key=key,
        environment="DEV" if actor.environment != "PRODUCTION" else "TEST",
        family_need_repository=service._repository,
        fgcn_provider_admission=fulfillment.fgcn_provider_admission,
    )

    # N4 (continued): once fulfilment actually succeeded, replace the
    # assignment plan with one that records *what it was really assigned
    # to* — the real slot/booking/order-intent — not merely the family's
    # authorization to attempt it. A failed fulfilment leaves the plan
    # exactly as `create_assignment_plan` left it above: authorized, but
    # honestly not yet (or never) resolved to a real resource.
    if result.succeeded and (
        result.availability_slot_id or result.booking_id or result.order_intent_id
    ):
        assignment_plan = assignment_plan.resolve(
            resolved_slot_id=result.availability_slot_id,
            resolved_booking_ref=result.booking_service_record_id or result.booking_id,
            resolved_order_intent_ref=result.order_intent_id,
        )
        await service._repository.save_assignment_plan(assignment_plan)

    return {
        "action": "CONFIRM_SOLUTION_DRAFT",
        "boundary": "REAL_ORDER_INTENT_AND_OR_BOOKING_NO_COMPENSATION_ON_PARTIAL_FAILURE",
        "draft": _serialize_component_draft(draft),
        "assignment_plan": {
            "plan_id": assignment_plan.plan_id,
            "need_id": assignment_plan.need_id,
            "draft_id": assignment_plan.draft_id,
            "authorization_basis": assignment_plan.authorization_basis,
            "created_at": assignment_plan.created_at.isoformat(),
            "resolved_slot_id": assignment_plan.resolved_slot_id,
            "resolved_booking_ref": assignment_plan.resolved_booking_ref,
            "resolved_order_intent_ref": assignment_plan.resolved_order_intent_ref,
        },
        "fulfillment": _serialize_fulfillment(result),
    }


@router.post("/{family_id}/needs/{need_id}/bookings/{booking_id}/complete-and-review")
async def complete_booking_and_review(
    family_id: str,
    need_id: str,
    booking_id: str,
    body: CompleteAndReviewBody,
    actor: Annotated[FamilyNeedActor, Depends(get_family_need_actor)],
    fulfillment: Annotated[FulfillmentDeps, Depends(get_fulfillment_deps)],
    idempotency_key: Annotated[str | None, Header()] = None,
) -> dict:
    """Mark a booked service session delivered and leave a growth-journey trace.

    This is the last link of the "need -> match -> book -> deliver -> review"
    chain: without it, a completed session leaves no trace a family or a
    future recommendation could ever read back.
    """

    from backend.domains.journey.application.outcome_loop import ActionFactStatus
    from backend.domains.service.application.commands import fulfil_service_record
    from backend.domains.service.application.context import ActionContext
    from backend.domains.service.domain.errors import ServiceDomainError

    _assert_actor_scope(actor, family_id)
    key = _require_idempotency(idempotency_key)

    ctx = ActionContext(
        tenant_id=actor.tenant_id,
        family_id=family_id,
        actor_person_id=actor.actor_id,
        actor=actor.actor_id,
        correlation_id=str(uuid4()),
        environment="DEV",  # type: ignore[arg-type]
        idempotency_key=f"{key}:fulfil-record",
    )
    try:
        record = await fulfil_service_record(
            fulfillment.service_repository,
            ctx,
            fulfillment.audit_recorder,
            booking_service_record_id=booking_id,
        )
    except ServiceDomainError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    action = fulfillment.outcome_loop.record_action(
        tenant_id=actor.tenant_id,
        family_id=family_id,
        plan_id=f"need:{need_id}",
        task_id=f"booking-service-record:{booking_id}",
        day_number=body.day_number,
        status=ActionFactStatus.COMPLETED,
        actor_id=actor.actor_id,
        idempotency_key=f"{key}:journey-action",
        evidence_refs=tuple(body.evidence_refs) or (f"service-record:{booking_id}",),
    )
    return {
        "action": "COMPLETE_BOOKING_AND_REVIEW",
        "boundary": "SERVICE_DELIVERY_FACT_JOINED_TO_A_JOURNEY_ACTION_FACT_NOT_AN_OUTCOME_CLAIM",
        "service_record": {
            "booking_service_record_id": record.booking_service_record_id,
            "status": record.status,
        },
        "journey_action": {
            "action_id": action.action_id,
            "plan_id": action.plan_id,
            "task_id": action.task_id,
            "day_number": action.day_number,
            "status": action.status.value,
            "recorded_at": action.recorded_at.isoformat(),
        },
    }


@router.post("/{family_id}/needs/{need_id}/courses/{course_content_id}/complete-and-review")
async def complete_course_and_review(
    family_id: str,
    need_id: str,
    course_content_id: str,
    body: CompleteAndReviewBody,
    actor: Annotated[FamilyNeedActor, Depends(get_family_need_actor)],
    fulfillment: Annotated[FulfillmentDeps, Depends(get_fulfillment_deps)],
    idempotency_key: Annotated[str | None, Header()] = None,
) -> dict:
    """Mark a matched, PUBLISHED course completed and leave a growth-journey trace.

    Mirrors `complete_booking_and_review` for the SOLUTION/course branch of
    the same "need -> match -> complete -> review" chain: a family matched to
    a course via `CourseSupplyAdapter` must be able to record finishing it,
    or the match never becomes a fact the growth journey (or a future
    recommendation) can read back.
    """

    from backend.domains.journey.application.outcome_loop import ActionFactStatus
    from backend.domains.product_intelligence.application.context import (
        ActorContext as ProductIntelligenceActorContext,
    )
    from backend.domains.product_intelligence.application.course_completion import (
        mark_course_completed_for_family,
    )
    from backend.domains.product_intelligence.domain.errors import (
        ProductIntelligenceConflictError,
        ProductIntelligenceValidationError,
    )

    _assert_actor_scope(actor, family_id)
    key = _require_idempotency(idempotency_key)

    pi_actor = ProductIntelligenceActorContext(
        actor_id=actor.actor_id,
        actor_type="HUMAN",
        tenant_scope=fulfillment.course_catalog_tenant_scope,
    )
    try:
        completion = await mark_course_completed_for_family(
            fulfillment.course_content_repository,
            pi_actor,
            course_content_id=course_content_id,
            family_id=family_id,
            need_id=need_id,
            subject_person_id=actor.actor_id,
        )
    except (ProductIntelligenceConflictError, ProductIntelligenceValidationError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    action = fulfillment.outcome_loop.record_action(
        tenant_id=actor.tenant_id,
        family_id=family_id,
        plan_id=f"need:{need_id}",
        task_id=f"course-completion:{course_content_id}",
        day_number=body.day_number,
        status=ActionFactStatus.COMPLETED,
        actor_id=actor.actor_id,
        idempotency_key=f"{key}:journey-action",
        evidence_refs=tuple(body.evidence_refs)
        or (f"course-completion:{completion.completion_id}",),
    )
    return {
        "action": "COMPLETE_COURSE_AND_REVIEW",
        "boundary": "COURSE_COMPLETION_FACT_JOINED_TO_A_JOURNEY_ACTION_FACT_NOT_AN_OUTCOME_CLAIM",
        "course_completion": {
            "completion_id": completion.completion_id,
            "course_content_id": completion.course_content_id,
            "course_title": completion.course_title,
        },
        "journey_action": {
            "action_id": action.action_id,
            "plan_id": action.plan_id,
            "task_id": action.task_id,
            "day_number": action.day_number,
            "status": action.status.value,
            "recorded_at": action.recorded_at.isoformat(),
        },
    }


class ConfirmOutcomeBody(BaseModel):
    """N6/N7: the family's own verdict on whether a delivered fulfilment
    actually helped. `fulfillment_ref` names the N5 delivery fact this
    outcome is about (a `booking_service_record_id` or a
    `course_completion_id`/`course_content_id`) — it is not itself a new
    delivery fact, and confirming it never re-runs or re-checks the
    delivery."""

    model_config = ConfigDict(extra="forbid")

    fulfillment_ref: str = Field(min_length=1, max_length=256)
    decision: FamilyOutcomeDecision
    family_note: str | None = Field(default=None, max_length=2_000)
    draft_id: str | None = Field(default=None, max_length=128)
    day_number: int = Field(ge=1, le=21, default=1)


def _serialize_outcome_confirmation(outcome, *, recommended_next_action: str | None) -> dict:
    payload = {
        "action": "CONFIRM_FAMILY_OUTCOME",
        "boundary": "FAMILY_CONFIRMED_RESULT_NOT_AI_OR_SYSTEM_SELF_JUDGED",
        "outcome": {
            "outcome_id": outcome.outcome_id,
            "need_id": outcome.need_id,
            "draft_id": outcome.draft_id,
            "fulfillment_ref": outcome.fulfillment_ref,
            "decision": outcome.decision.value,
            "confirmed_by": outcome.confirmed_by,
            "confirmed_at": outcome.confirmed_at.isoformat(),
            "family_note": outcome.family_note,
        },
    }
    if recommended_next_action is not None:
        # DID_NOT_HELP only: an honest, non-automated pointer back toward
        # N8 (re-triage/re-match). This is a suggestion marker, not a new
        # NeedSignal — creating one automatically is explicitly out of scope
        # for this endpoint (see module docstring / task description).
        payload["recommended_next_action"] = recommended_next_action
    return payload


@router.post("/{family_id}/needs/{need_id}/outcomes/confirm")
async def confirm_family_outcome(
    family_id: str,
    need_id: str,
    body: ConfirmOutcomeBody,
    actor: Annotated[FamilyNeedActor, Depends(get_family_need_actor)],
    service: Annotated[FamilyNeedApplicationService, Depends(get_family_need_service)],
    fulfillment: Annotated[FulfillmentDeps, Depends(get_fulfillment_deps)],
    idempotency_key: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> dict:
    """N6/N7: the family confirms whether a delivered service/course helped.

    This is the missing half of "need -> match -> book -> deliver -> review":
    `complete_booking_and_review` / `complete_course_and_review` only record
    that *delivery happened* — a service-side or system-side fact. Whether it
    actually helped the family is a distinct, family-only fact, and this
    endpoint is the only place that fact can be written. An AI or SYSTEM
    actor calling this is rejected (403) by
    `FamilyNeedApplicationService.confirm_outcome` before any outcome is
    persisted — see that method's docstring for the R9 rationale.

    A `DID_NOT_HELP` decision is recorded exactly like any other decision (no
    special-casing, no hiding a negative result) and additionally opens N8's
    re-triage loop for real: a fresh `NeedSignal`/`FamilyNeed` is captured
    through the ordinary `capture_signal` use case (same code path as a
    brand-new family request — N8 does not get its own parallel intake
    logic), tagged with `causation_id=need_id` so the new need's origin is
    traceable back to the outcome that triggered it, and scoped to this same
    family/tenant only (no data crosses into any shared/public knowledge
    store — the retriage signal is exactly as private as the original one).
    """

    from backend.domains.journey.application.outcome_loop import ActionFactStatus

    _assert_actor_scope(actor, family_id)
    key = _require_idempotency(idempotency_key)
    existing_need = await service._repository.get_need(
        tenant_id=actor.tenant_id, family_id=family_id, need_id=need_id
    )
    if existing_need is None:
        raise HTTPException(status_code=404, detail="family_need_not_found")
    context = _to_operation_context(
        purpose="FAMILY_NEED",
        consent_version="v1",
        data_class=DataClass.MINOR_PERSONAL_DATA,
        locale="zh-CN",
        subject_person_ids=existing_need.subject_person_ids,
        actor=actor,
        correlation_id=x_correlation_id,
    )
    outcome = await service.confirm_outcome(
        context=context,
        need_id=need_id,
        fulfillment_ref=body.fulfillment_ref,
        decision=body.decision,
        draft_id=body.draft_id,
        family_note=body.family_note,
        idempotency_key=key,
    )

    # Distinct task_id prefix from `booking-service-record:`/`course-completion:`
    # so a reader of the journey can tell "the family said this" apart from
    # "the system/service recorded delivery" at a glance (per task description).
    action = fulfillment.outcome_loop.record_action(
        tenant_id=actor.tenant_id,
        family_id=family_id,
        plan_id=f"need:{need_id}",
        task_id=f"family-confirmed-outcome:{body.fulfillment_ref}",
        day_number=body.day_number,
        status=ActionFactStatus.COMPLETED,
        actor_id=actor.actor_id,
        idempotency_key=f"{key}:journey-action",
        evidence_refs=(f"family-outcome:{outcome.outcome_id}",),
    )

    retriage_signal_need_id: str | None = None
    recommended_next_action = (
        "N8_RETRIAGE_SUGGESTED" if body.decision is FamilyOutcomeDecision.DID_NOT_HELP else None
    )
    # N8/experience-pool (product/content + parent-facing side): a
    # *separate*, cross-family, de-identified signal is written for the
    # matched component(s), regardless of decision — see
    # `backend.domains.product_intelligence.domain.family_experience_signal`'s
    # module docstring for why every verdict (not only DID_NOT_HELP) is a
    # real family's experience worth recording, and why this is a distinct
    # aggregate from `ImprovementCandidate`. Both writes are skipped
    # honestly (not fabricated) when the draft that was confirmed is not
    # resolvable, or the process has not wired the relevant repository.
    if body.draft_id and (
        fulfillment.improvement_candidate_repository is not None
        or fulfillment.family_experience_signal_repository is not None
    ):
        resolved_draft = await service._repository.get_solution_draft(
            tenant_id=actor.tenant_id, family_id=family_id, draft_id=body.draft_id
        )
        if resolved_draft is not None and resolved_draft.components:
            resolved_profile = await service._repository.get_profile(
                tenant_id=actor.tenant_id,
                family_id=family_id,
                profile_id=resolved_draft.need_profile_id,
            )
            resolved_intervention_tier = (
                resolved_profile.intervention_tier.value
                if resolved_profile is not None
                else "LIGHT_GUIDANCE"
            )
            for component in resolved_draft.components:
                # Experience pool: every decision, for the "similar
                # problem" search a parent runs.
                if fulfillment.family_experience_signal_repository is not None:
                    await record_family_experience_signal(
                        fulfillment.family_experience_signal_repository,
                        component_id=component.component_id,
                        component_shape=component.shape.value,
                        decision=body.decision.value,
                        category=existing_need.category.value,
                        intervention_tier=resolved_intervention_tier,
                    )
                # N8 improvement candidate: only the negative verdict, for
                # the product/content team's "revise or retire" question.
                if (
                    body.decision is FamilyOutcomeDecision.DID_NOT_HELP
                    and fulfillment.improvement_candidate_repository is not None
                ):
                    await record_improvement_candidate(
                        fulfillment.improvement_candidate_repository,
                        component_id=component.component_id,
                        component_shape=component.shape.value,
                        decision=body.decision.value,
                        category=existing_need.category.value,
                        intervention_tier=resolved_intervention_tier,
                    )

    if body.decision is FamilyOutcomeDecision.DID_NOT_HELP:
        # N8 (family side): re-open the need through the exact same intake
        # use case a brand-new family request uses — no parallel "retriage"
        # pipeline — with `causation_id` naming the outcome-confirmed need
        # this grew out of, and scope (tenant/family) identical to the
        # original, so nothing crosses into any shared/public store.
        retriage_context = replace(
            _to_operation_context(
                purpose="FAMILY_NEED",
                consent_version="v1",
                data_class=DataClass.MINOR_PERSONAL_DATA,
                locale="zh-CN",
                subject_person_ids=existing_need.subject_person_ids,
                actor=actor,
                correlation_id=x_correlation_id,
            ),
            causation_id=need_id,
        )
        retriage_result = await service.capture_signal(
            NeedSignalInput(
                context=retriage_context,
                raw_text=f"[N8回流] {existing_need.statement}（此前方案未能真正帮到这个家庭）",
                source=NeedSignalSource.SERVICE_FEEDBACK,
                subject_person_ids=existing_need.subject_person_ids,
                statement=existing_need.statement,
                desired_outcome=existing_need.desired_outcome,
                category=existing_need.category,
                idempotency_key=f"{key}:n8-retriage",
            )
        )
        retriage_signal_need_id = retriage_result.need.need_id

    response = _serialize_outcome_confirmation(
        outcome, recommended_next_action=recommended_next_action
    )
    response["journey_action"] = {
        "action_id": action.action_id,
        "plan_id": action.plan_id,
        "task_id": action.task_id,
        "day_number": action.day_number,
        "status": action.status.value,
        "recorded_at": action.recorded_at.isoformat(),
    }
    response["retriage_signal_need_id"] = retriage_signal_need_id
    return response


class AiCoachMessageBody(BaseModel):
    """One parent message to the Socratic AI Coach; no domain fields to fake."""

    model_config = ConfigDict(extra="forbid")

    parent_message: str = Field(min_length=1, max_length=4_000)
    profile_id: str | None = Field(default=None, max_length=128)
    draft_id: str | None = Field(default=None, max_length=128)


def _serialize_coach_perspective(perspective) -> dict:
    return {
        "action": "AI_COACH_PERSPECTIVE",
        "boundary": perspective.boundary_note,
        "reflection": perspective.reflection,
        "guiding_question": perspective.guiding_question,
        "provenance": {
            "provider_id": perspective.provenance.provider_id,
            "model": perspective.provenance.model,
            "model_version": perspective.provenance.model_version,
            "prompt_version": perspective.provenance.prompt_version,
            "schema_version": perspective.provenance.schema_version,
            "context_snapshot_ref": perspective.provenance.context_snapshot_ref,
            "latency_ms": perspective.provenance.latency_ms,
            "confidence": perspective.provenance.confidence,
        },
    }


@router.post("/{family_id}/needs/{need_id}/ai-coach/messages")
async def send_ai_coach_message(
    family_id: str,
    need_id: str,
    body: AiCoachMessageBody,
    actor: Annotated[FamilyNeedActor, Depends(get_family_need_actor)],
    ai_coach: Annotated[AiCoachDeps, Depends(get_ai_coach_deps)],
    idempotency_key: Annotated[str | None, Header()] = None,
) -> dict:
    """A parent's message to the Socratic AI Coach for one family need.

    The reply is a Perspective (R9): it is the AI's understanding of the
    parent's situation plus a guiding question, not a fact about the family
    and not a recommendation the platform will act on. Nothing here mutates
    any `family_need` aggregate — this route only reads the existing need
    (and, optionally, an existing profile/draft) to build real context.
    """

    _assert_actor_scope(actor, family_id)
    request_id = _require_idempotency(idempotency_key)
    try:
        perspective = await request_coach_perspective(
            ai_coach.gateway,
            ai_coach.repository,
            provider_id=ai_coach.provider_id,
            tenant_id=actor.tenant_id,
            family_id=family_id,
            need_id=need_id,
            parent_message=body.parent_message,
            profile_id=body.profile_id,
            draft_id=body.draft_id,
            request_id=request_id,
            outcome_loop=ai_coach.outcome_loop,
        )
    except FamilyNeedNotFoundError:
        raise HTTPException(status_code=404, detail="family_need_not_found") from None
    except ModelGatewayError as exc:
        # Fail closed (R9/R14): a schema-invalid, rejected, or otherwise
        # unusable model response must never be patched into something that
        # looks like a valid guiding question. 502 because the failure is the
        # provider/gateway's, not this request's.
        raise HTTPException(
            status_code=502, detail=f"ai_coach_model_gateway_failed:{exc.kind}"
        ) from None
    return _serialize_coach_perspective(perspective)


def _serialize_component_draft(draft) -> dict:
    return {
        "draft_id": draft.draft_id,
        "need_id": draft.need_id,
        "status": draft.status.value,
        "commercial_intent": draft.commercial_intent,
        "components": [_serialize_component(item) for item in draft.components],
    }


__all__ = [
    "CaptureNeedBody",
    "ClarifyNeedBody",
    "CompleteAndReviewBody",
    "ConfirmOutcomeBody",
    "ConfirmSolutionDraftBody",
    "NeedEvidenceBody",
    "ProfileNeedBody",
    "SolutionComponentBody",
    "SolutionDraftBody",
    "register_exception_handlers",
    "router",
]
