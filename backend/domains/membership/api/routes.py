"""HTTP layer for the membership domain.

Three properties this module is responsible for, none of which the application
or domain layer can guarantee on its own:

1. **Scope never comes from the URL.** Every read and write takes
   `(tenant_id, family_id)` from the authenticated `ActionContext`. There is no
   path or query parameter a caller could edit to reach another family. A test
   asserts this by putting a foreign `family_id` in the request body and showing
   it has no effect.

2. **The decider is the caller.** `decided_by` was removed from the request
   models (see the comment there): the domain's `assert_human_actor` inspects a
   *claim*, so as long as the claim was client-supplied, an AI-authenticated
   caller could launder itself into a human decider. Here it is derived from
   `ctx.actor`.

3. **Human Gate on high-impact actions (R8).** 会员升级 is named in R8's list.
   `_authorize` routes every write through the fail-closed `PolicyEngine`, whose
   rules for those actions carry `human_only=True`, so an AI actor is denied
   unconditionally — not by convention of what got registered, but by the
   engine's own override.

Known gap, stated rather than papered over: R8 also requires the gate decision
to be *落库可审计*. `AuditRecorder.flush()` is currently a no-op (its own
docstring says Wave 1 has no durable audit table), so gate decisions land in
process memory only. There is no `backend/platform/human_gate` primitive either.
Both are platform-level gaps; this module records what it can and does not
pretend the durability requirement is met.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.platform.audit.models import AuditEvent
from backend.platform.audit.recorder import AuditRecorder
from backend.platform.authorization.policy import PolicyEngine
from backend.platform.identity.context import ActorContext

from ..application import commands, queries
from ..application.context import ActionContext
from ..application.ports import MembershipRepositoryPort
from ..domain.errors import MembershipDomainError
from . import requests as req
from .dependencies import (
    HUMAN_GATED_ACTIONS,
    get_action_context,
    get_actor_context,
    get_audit_recorder,
    get_policy_engine,
    get_repository,
    resource_for,
)

router = APIRouter(prefix="/membership", tags=["membership"])

_ERROR_STATUS = {
    "MembershipValidationError": 400,
    "MembershipForbiddenError": 403,
    "MembershipNotFoundError": 404,
    "MembershipConflictError": 409,
}

# Only these four surfaces have a membership query function. `MEMBERSHIP_READ_SURFACES`
# is wider (it includes UI-13 and UI-31, where membership data is *shown* inside a
# screen another domain owns), so the dispatch table — not the surface set — decides
# what this router can serve.
_SCREEN_HANDLERS = {
    "UI-06": queries.get_ui06_my_membership,
    "UI-18": queries.get_ui18_membership_center,
    "UI-30": queries.get_ui30_annual_companion,
    "UI-32": queries.get_ui32_orders_and_assets,
}


def _raise_http(exc: MembershipDomainError) -> None:
    raise HTTPException(
        status_code=_ERROR_STATUS.get(type(exc).__name__, 400), detail=exc.code
    ) from exc


def _authorize(
    engine: PolicyEngine,
    actor: ActorContext,
    action: str,
    recorder: AuditRecorder,
    ctx: ActionContext,
) -> None:
    """Fail-closed gate. Denials are audited too — a refused upgrade attempt is
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


def _audit_write(
    recorder: AuditRecorder,
    actor: ActorContext,
    ctx: ActionContext,
    *,
    action: str,
    resource_id: str,
    after: dict[str, Any] | None = None,
) -> None:
    """R6: no state mutation without an audit event."""
    recorder.record(
        AuditEvent(
            actor_id=actor.actor_id,
            tenant_id=ctx.tenant_id,
            action=action,
            resource_type=resource_for(action),
            resource_id=resource_id,
            reason=f"named action {action} via HTTP",
            correlation_id=ctx.correlation_id,
            after=after,
        )
    )


# --------------------------------------------------------------------------
# Writes — one named resource per Named Action. No generic PATCH on core state.
# --------------------------------------------------------------------------


@router.post("/subscriptions")
async def subscribe_membership(
    body: req.SubscribeMembershipRequest,
    repo: MembershipRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
):
    _authorize(engine, actor, "subscribe_membership", recorder, ctx)
    try:
        subscription = await commands.subscribe_membership(repo, ctx, **body.model_dump())
    except MembershipDomainError as exc:
        _raise_http(exc)
    _audit_write(
        recorder,
        actor,
        ctx,
        action="subscribe_membership",
        resource_id=subscription.membership_subscription_id,
        after={"status": subscription.status, "plan_ref": subscription.plan_ref},
    )
    return subscription


@router.post("/tier-activations")
async def activate_membership_tier(
    body: req.ActivateMembershipTierRequest,
    repo: MembershipRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
):
    """The only endpoint that can move a family's membership tier."""
    _authorize(engine, actor, "activate_membership_tier", recorder, ctx)
    try:
        transition, period = await commands.activate_membership_tier(
            repo, ctx, decided_by=ctx.actor, **body.model_dump()
        )
    except MembershipDomainError as exc:
        _raise_http(exc)
    _audit_write(
        recorder,
        actor,
        ctx,
        action="activate_membership_tier",
        resource_id=transition.tier_transition_id,
        after={
            "from_tier_code": transition.from_tier_code,
            "to_tier_code": transition.to_tier_code,
            "activation_source_type": transition.activation_source_type,
            "activation_source_ref": transition.activation_source_ref,
        },
    )
    return {"transition": transition, "period": period}


@router.post("/period-renewals")
async def renew_membership_period(
    body: req.RenewMembershipPeriodRequest,
    repo: MembershipRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
):
    _authorize(engine, actor, "renew_membership_period", recorder, ctx)
    try:
        transition, period = await commands.renew_membership_period(
            repo, ctx, decided_by=ctx.actor, **body.model_dump()
        )
    except MembershipDomainError as exc:
        _raise_http(exc)
    _audit_write(
        recorder,
        actor,
        ctx,
        action="renew_membership_period",
        resource_id=period.membership_period_id,
        after={"seq_no": period.seq_no, "tier_code": period.tier_code},
    )
    return {"transition": transition, "period": period}


@router.post("/period-expirations")
async def expire_membership_period(
    body: req.ExpireMembershipPeriodRequest,
    repo: MembershipRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
):
    _authorize(engine, actor, "expire_membership_period", recorder, ctx)
    try:
        transition, period = await commands.expire_membership_period(
            repo, ctx, decided_by=ctx.actor, **body.model_dump()
        )
    except MembershipDomainError as exc:
        _raise_http(exc)
    _audit_write(
        recorder,
        actor,
        ctx,
        action="expire_membership_period",
        resource_id=transition.tier_transition_id,
        after={"to_tier_code": transition.to_tier_code},
    )
    return {"transition": transition, "period": period}


@router.post("/benefit-grants")
async def grant_membership_benefit(
    body: req.GrantMembershipBenefitRequest,
    repo: MembershipRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
):
    _authorize(engine, actor, "grant_membership_benefit", recorder, ctx)
    try:
        grant = await commands.grant_membership_benefit(repo, ctx, **body.model_dump())
    except MembershipDomainError as exc:
        _raise_http(exc)
    _audit_write(
        recorder,
        actor,
        ctx,
        action="grant_membership_benefit",
        resource_id=grant.benefit_grant_id,
        after={"allocated_units": grant.allocated_units, "benefit_ref": grant.benefit_ref},
    )
    return grant


@router.post("/benefit-reservations")
async def reserve_membership_benefit(
    body: req.ReserveMembershipBenefitRequest,
    repo: MembershipRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
):
    _authorize(engine, actor, "reserve_membership_benefit", recorder, ctx)
    try:
        reservation = await commands.reserve_membership_benefit(repo, ctx, **body.model_dump())
    except MembershipDomainError as exc:
        _raise_http(exc)
    _audit_write(
        recorder,
        actor,
        ctx,
        action="reserve_membership_benefit",
        resource_id=reservation.benefit_reservation_id,
        after={"units": reservation.units, "status": reservation.status},
    )
    return reservation


@router.post("/benefit-reservations/{benefit_reservation_id}/release")
async def release_membership_benefit_reservation(
    benefit_reservation_id: str,
    repo: MembershipRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
):
    _authorize(engine, actor, "release_membership_benefit_reservation", recorder, ctx)
    try:
        reservation = await commands.release_membership_benefit_reservation(
            repo, ctx, benefit_reservation_id=benefit_reservation_id
        )
    except MembershipDomainError as exc:
        _raise_http(exc)
    _audit_write(
        recorder,
        actor,
        ctx,
        action="release_membership_benefit_reservation",
        resource_id=reservation.benefit_reservation_id,
        after={"status": reservation.status},
    )
    return reservation


@router.post("/benefit-consumptions")
async def consume_membership_benefit(
    body: req.ConsumeMembershipBenefitRequest,
    repo: MembershipRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
):
    _authorize(engine, actor, "consume_membership_benefit", recorder, ctx)
    try:
        grant = await commands.consume_membership_benefit(repo, ctx, **body.model_dump())
    except MembershipDomainError as exc:
        _raise_http(exc)
    _audit_write(
        recorder,
        actor,
        ctx,
        action="consume_membership_benefit",
        resource_id=grant.benefit_grant_id,
        after={"remaining_units": grant.remaining_units, "status": grant.status},
    )
    return grant


@router.post("/benefit-revocations")
async def revoke_membership_benefit(
    body: req.RevokeMembershipBenefitRequest,
    repo: MembershipRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
):
    _authorize(engine, actor, "revoke_membership_benefit", recorder, ctx)
    try:
        grant = await commands.revoke_membership_benefit(
            repo, ctx, decided_by=ctx.actor, **body.model_dump()
        )
    except MembershipDomainError as exc:
        _raise_http(exc)
    _audit_write(
        recorder,
        actor,
        ctx,
        action="revoke_membership_benefit",
        resource_id=grant.benefit_grant_id,
        after={"status": grant.status, "remaining_units": grant.remaining_units},
    )
    return grant


# --------------------------------------------------------------------------
# Reads — scope from the context, never from the URL.
# --------------------------------------------------------------------------


@router.get("/projection")
async def get_projection(
    repo: MembershipRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
):
    _authorize(engine, actor, "read_membership_projection", recorder, ctx)
    return await queries.get_membership_projection(
        repo, tenant_id=ctx.tenant_id, family_id=ctx.family_id
    )


@router.get("/screens/{surface_id}")
async def get_screen(
    surface_id: str,
    repo: MembershipRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
):
    """Per-App-UI-surface read. Unknown surfaces are 404 here rather than
    reaching `queries.get_surface`, which raises `KeyError` (→ 500) for an id
    that is not one of the 34 screens at all."""
    _authorize(engine, actor, "read_membership_projection", recorder, ctx)
    handler = _SCREEN_HANDLERS.get(surface_id)
    if handler is None:
        raise HTTPException(status_code=404, detail=f"membership_screen_not_found:{surface_id}")
    try:
        return await handler(repo, tenant_id=ctx.tenant_id, family_id=ctx.family_id)
    except MembershipDomainError as exc:
        _raise_http(exc)
