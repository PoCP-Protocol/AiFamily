"""HTTP layer for the service booking chain.

Path shapes come from `contracts/openapi/UI_API_ENDPOINT_INVENTORY.md`'s SERVICE
group, so the mobile client that already calls these six URLs does not have to
change. Two things about them are worth stating rather than discovering later:

**The `{familyId}` path parameter is not the authorization subject.** It is in
the URL because the published contract puts it there, and the mobile client
sends it. Every route re-derives `(tenant_id, family_id)` from the authenticated
`ActionContext` and then *compares* the path value against it, refusing on
mismatch (`assert_family_scope`). The path segment is therefore an assertion the
caller makes about itself and the server checks, never a selector the server
obeys. `test_api_routes.py` proves this by requesting another family's URL with a
valid token and asserting 403.

**The `orchestration/test-loop/` segment is inherited, and the inventory already
flagged it (§note 3: "疑为源仓库测试回路残留挂在生产路由前缀下，触及 R5"). It
is reproduced here because breaking the client contract is not this task's call
to make, and because the domain behind it *is* honestly fixture-only: every
booking carries `environment IN (DEV,TEST)`, `source_system = TEST_FIXTURE` and
`external_effect = false`, so the route name and the semantics agree for once.
Renaming the path is an API-contract decision that needs an ADR and a coordinated
client change; it is registered as a known gap, not silently kept.

Human Gate (R8): `_authorize` routes every write through the fail-closed
`PolicyEngine`. Confirm / fulfil / cancel are registered `human_only=True`, so an
AI actor is denied unconditionally by the engine's own veto rather than by
whatever happened to get registered.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from backend.platform.audit.models import AuditEvent
from backend.platform.audit.recorder import AuditRecorder
from backend.platform.authorization.policy import PolicyEngine
from backend.platform.identity.context import ActorContext

from ..application import commands, queries
from ..application.context import ActionContext
from ..application.ports import ConsentQueryPort, ServiceRepositoryPort
from ..domain.errors import ServiceDomainError, ServiceForbiddenError
from . import requests as req
from .dependencies import (
    HUMAN_GATED_ACTIONS,
    get_action_context,
    get_actor_context,
    get_audit_recorder,
    get_consent_query,
    get_policy_engine,
    get_repository,
    resource_for,
)

router = APIRouter(tags=["service"])

_ERROR_STATUS = {
    "ServiceValidationError": 400,
    "ServiceForbiddenError": 403,
    "ServiceNotFoundError": 404,
    "ServiceConflictError": 409,
}


def _raise_http(exc: ServiceDomainError) -> None:
    raise HTTPException(
        status_code=_ERROR_STATUS.get(type(exc).__name__, 400), detail=exc.code
    ) from exc


def _assert_path_family(family_id: str, ctx: ActionContext) -> None:
    """The URL's family must be the authenticated one.

    403 rather than 404: the caller is authenticated, the family exists, it is
    simply not theirs — and a 404 here would leak "no such family" for families
    that do exist while hiding a genuine authorization failure.
    """
    if family_id != ctx.family_id:
        raise HTTPException(status_code=403, detail="family_scope_violation")


def _require_idempotency_key(ctx: ActionContext) -> None:
    """Every mutation needs one.

    Checked against the context rather than the raw header because the context is
    where the rest of the stack reads it from; validating the header and then
    using a context that was built from something else is the kind of gap that
    only shows up under a retry storm.
    """
    if not ctx.idempotency_key:
        raise HTTPException(status_code=400, detail="idempotency-key header is required")


def _authorize(
    engine: PolicyEngine,
    actor: ActorContext,
    action: str,
    recorder: AuditRecorder,
    ctx: ActionContext,
) -> None:
    """Fail-closed gate. Denials are audited too — a refused booking attempt is
    exactly the kind of event an operator needs to see later."""
    decision = engine.check(actor, action, resource_for(action))
    if not decision.allowed:
        recorder.record(
            AuditEvent(
                actor_id=actor.actor_id,
                tenant_id=ctx.tenant_id,
                action=f"{action}:denied",
                resource_type=resource_for(action),
                resource_id=ctx.family_id,
                reason=decision.reason,
                correlation_id=ctx.correlation_id,
            )
        )
        raise HTTPException(status_code=403, detail=decision.reason)
    if action in HUMAN_GATED_ACTIONS:
        recorder.record(
            AuditEvent(
                actor_id=actor.actor_id,
                tenant_id=ctx.tenant_id,
                action=f"{action}:human_gate_passed",
                resource_type=resource_for(action),
                resource_id=ctx.family_id,
                reason=decision.reason,
                correlation_id=ctx.correlation_id,
            )
        )


# --------------------------------------------------------------------------
# Reads — scope re-derived from the context, path only asserted against it.
# --------------------------------------------------------------------------

_TEST_LOOP = "/families/{family_id}/orchestration/test-loop/services"


@router.get(f"{_TEST_LOOP}/offerings")
async def get_service_offerings(
    family_id: str,
    repo: ServiceRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
) -> Any:
    """`getServiceOfferings` — UI-19 browse. Tenant-scoped supply, no family facts."""
    _assert_path_family(family_id, ctx)
    _authorize(engine, actor, "read_service_supply", recorder, ctx)
    return await queries.list_service_offerings(repo, tenant_id=ctx.tenant_id)


@router.get(f"{_TEST_LOOP}/activities")
async def get_activity_catalog(
    family_id: str,
    repo: ServiceRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
) -> Any:
    """UI-22/UI-23 browsing; no registration or attendance side effect."""
    _assert_path_family(family_id, ctx)
    _authorize(engine, actor, "read_service_supply", recorder, ctx)
    return await queries.list_activity_catalog(repo)


@router.get(f"{_TEST_LOOP}/slots")
async def get_service_slots(
    family_id: str,
    service_offering_id: str | None = None,
    repo: ServiceRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
) -> Any:
    """`getServiceSlots` — UI-20/21 slot picker."""
    _assert_path_family(family_id, ctx)
    _authorize(engine, actor, "read_service_supply", recorder, ctx)
    return await queries.list_availability_slots(
        repo, tenant_id=ctx.tenant_id, service_offering_id=service_offering_id
    )


@router.get(f"{_TEST_LOOP}/customer-projection")
async def get_service_customer_projection(
    family_id: str,
    repo: ServiceRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
) -> Any:
    """`getServiceCustomerProjection` — UI-24 我的预约."""
    _assert_path_family(family_id, ctx)
    _authorize(engine, actor, "read_service_booking", recorder, ctx)
    return await queries.get_customer_projection(
        repo, tenant_id=ctx.tenant_id, family_id=ctx.family_id
    )


@router.get("/families/{family_id}/growth/onboardings/{onboarding_id}/service-journey")
async def get_service_journey(
    family_id: str,
    onboarding_id: str,
    repo: ServiceRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
) -> Any:
    """`getServiceJourney` — UI-06, bookings plus the family's private drafts."""
    _assert_path_family(family_id, ctx)
    _authorize(engine, actor, "read_service_booking", recorder, ctx)
    return await queries.get_service_journey(
        repo, tenant_id=ctx.tenant_id, family_id=ctx.family_id, onboarding_id=onboarding_id
    )


# --------------------------------------------------------------------------
# Writes — one named resource per Named Action. No generic PATCH on core state.
# --------------------------------------------------------------------------


@router.post(f"{_TEST_LOOP}/booking-requests")
async def submit_service_booking(
    family_id: str,
    body: req.SubmitBookingRequest,
    idempotency_key: str | None = Header(default=None),
    repo: ServiceRepositoryPort = Depends(get_repository),
    consent: ConsentQueryPort = Depends(get_consent_query),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
) -> Any:
    """`submitServiceBooking` — UI-21 预约提交.

    The one endpoint that touches consent. `commands.submit_booking_request`
    reads the subject's current SERVICE grants and refuses without one; the route
    does not pre-judge that, so there is exactly one place the decision lives.
    """
    _assert_path_family(family_id, ctx)
    _require_idempotency_key(ctx)
    _authorize(engine, actor, "submit_booking_request", recorder, ctx)
    try:
        return await commands.submit_booking_request(
            repo, ctx, recorder, consent, **body.model_dump()
        )
    except ServiceDomainError as exc:
        _raise_http(exc)


@router.post(
    "/families/{family_id}/growth/onboardings/{onboarding_id}/service-journey/checkin-drafts"
)
async def create_private_checkin_draft(
    family_id: str,
    onboarding_id: str,
    body: req.CreatePrivateCheckinDraftRequest,
    idempotency_key: str | None = Header(default=None),
    repo: ServiceRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
) -> Any:
    """`createPrivateCheckinDraft` — UI-06 §4.1 私密复盘草稿."""
    _assert_path_family(family_id, ctx)
    _require_idempotency_key(ctx)
    _authorize(engine, actor, "create_private_checkin_draft", recorder, ctx)
    try:
        return await commands.create_private_checkin_draft(
            repo, ctx, recorder, onboarding_id=onboarding_id, action_ref=body.action_ref
        )
    except ServiceDomainError as exc:
        _raise_http(exc)


# --------------------------------------------------------------------------
# Operator-side writes. Not in the six published client endpoints — the mobile
# client has no supply-management or confirmation surface — but the chain is not
# runnable end to end without them, and leaving them application-layer-only
# would mean the acceptance chain is provable while the deployed system stops at
# "requested". Grouped under an explicit `/service/` prefix rather than the
# inherited `test-loop` shape, because these are not client-contract paths and
# should not look like they are.
# --------------------------------------------------------------------------


@router.post("/families/{family_id}/service/providers")
async def register_service_provider(
    family_id: str,
    body: req.RegisterServiceProviderRequest,
    idempotency_key: str | None = Header(default=None),
    repo: ServiceRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
) -> Any:
    _assert_path_family(family_id, ctx)
    _require_idempotency_key(ctx)
    _authorize(engine, actor, "register_service_provider", recorder, ctx)
    try:
        return await commands.register_service_provider(repo, ctx, recorder, **body.model_dump())
    except ServiceDomainError as exc:
        _raise_http(exc)


@router.post("/families/{family_id}/service/offerings")
async def publish_service_offering(
    family_id: str,
    body: req.PublishServiceOfferingRequest,
    idempotency_key: str | None = Header(default=None),
    repo: ServiceRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
) -> Any:
    _assert_path_family(family_id, ctx)
    _require_idempotency_key(ctx)
    _authorize(engine, actor, "publish_service_offering", recorder, ctx)
    try:
        return await commands.publish_service_offering(repo, ctx, recorder, **body.model_dump())
    except ServiceDomainError as exc:
        _raise_http(exc)


@router.post("/families/{family_id}/service/availability-slots")
async def open_availability_slot(
    family_id: str,
    body: req.OpenAvailabilitySlotRequest,
    idempotency_key: str | None = Header(default=None),
    repo: ServiceRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
) -> Any:
    _assert_path_family(family_id, ctx)
    _require_idempotency_key(ctx)
    _authorize(engine, actor, "open_availability_slot", recorder, ctx)
    try:
        return await commands.open_availability_slot(repo, ctx, recorder, **body.model_dump())
    except ServiceDomainError as exc:
        _raise_http(exc)


@router.post("/families/{family_id}/service/booking-requests/{booking_request_id}/confirm")
async def confirm_booking_request(
    family_id: str,
    booking_request_id: str,
    idempotency_key: str | None = Header(default=None),
    repo: ServiceRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
) -> Any:
    """Human-gated (R8): confirming commits a named provider's time."""
    _assert_path_family(family_id, ctx)
    _require_idempotency_key(ctx)
    _authorize(engine, actor, "confirm_booking_request", recorder, ctx)
    try:
        booking, record = await commands.confirm_booking_request(
            repo, ctx, recorder, booking_request_id=booking_request_id
        )
    except ServiceForbiddenError as exc:
        _raise_http(exc)
    except ServiceDomainError as exc:
        _raise_http(exc)
    return {"booking": booking, "service_record": record}


@router.post("/families/{family_id}/service/booking-requests/{booking_request_id}/cancel")
async def cancel_booking_request(
    family_id: str,
    booking_request_id: str,
    idempotency_key: str | None = Header(default=None),
    repo: ServiceRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
) -> Any:
    _assert_path_family(family_id, ctx)
    _require_idempotency_key(ctx)
    _authorize(engine, actor, "cancel_booking_request", recorder, ctx)
    try:
        return await commands.cancel_booking_request(
            repo, ctx, recorder, booking_request_id=booking_request_id
        )
    except ServiceDomainError as exc:
        _raise_http(exc)


@router.post("/families/{family_id}/service/service-records/{booking_service_record_id}/fulfil")
async def fulfil_service_record(
    family_id: str,
    booking_service_record_id: str,
    body: req.FulfilServiceRecordRequest,
    idempotency_key: str | None = Header(default=None),
    repo: ServiceRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
) -> Any:
    """Human-gated (R8): asserting a service was delivered is a human's claim."""
    _assert_path_family(family_id, ctx)
    _require_idempotency_key(ctx)
    _authorize(engine, actor, "fulfil_service_record", recorder, ctx)
    try:
        return await commands.fulfil_service_record(
            repo,
            ctx,
            recorder,
            booking_service_record_id=booking_service_record_id,
            quality_rating=body.quality_rating,
        )
    except ServiceDomainError as exc:
        _raise_http(exc)
