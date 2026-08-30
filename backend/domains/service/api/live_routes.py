"""H-LIVE-01 read-only Service control-plane endpoint.

This router deliberately is not a booking or media router. It exposes GET
discovery and detail operations and requires explicit application composition
for its source adapter. The clean-base task proves import and contract
behavior; mounting it in the production app is a separate composition-owner
change.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.platform.audit.models import AuditEvent
from backend.platform.audit.recorder import AuditRecorder
from backend.platform.authorization.policy import PolicyEngine
from backend.platform.identity.context import ActorContext

from ..application.context import ActionContext
from ..application.live_ports import (
    LiveReadConflictError,
    LiveReadError,
    LiveReadScope,
    LiveSessionReadPort,
)
from ..application.live_queries import get_live_session_detail, list_live_sessions
from ..application.live_read_models import (
    PUBLIC_LIVE_SESSION_FIELDS,
    LiveSessionDetail,
)
from .dependencies import (
    get_action_context,
    get_actor_context,
    get_audit_recorder,
    get_live_session_read_port,
    get_policy_engine,
    resource_for,
)

router = APIRouter(tags=["service-live-read"])


def _read_error_status(exc: LiveReadError) -> int:
    if isinstance(exc, LiveReadConflictError):
        return 409
    if exc.code.endswith("forbidden") or "scope" in exc.code:
        return 403
    return 404


def _authorize_live_read(
    *,
    actor: ActorContext,
    ctx: ActionContext,
    engine: PolicyEngine,
    recorder: AuditRecorder,
) -> None:
    if actor.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=403, detail="tenant_scope_violation")
    if not actor.is_human:
        raise HTTPException(status_code=403, detail="guardian_human_required")
    decision = engine.check(actor, "read_live_session", resource_for("read_live_session"))
    if not decision.allowed:
        recorder.record(
            AuditEvent(
                actor_id=actor.actor_id,
                tenant_id=ctx.tenant_id,
                action="read_live_session:denied",
                resource_type="LiveSession",
                resource_id=ctx.family_id,
                reason=decision.reason,
                correlation_id=ctx.correlation_id,
            )
        )
        raise HTTPException(status_code=403, detail=decision.reason)


@router.get(
    "/families/{family_id}/live-sessions",
    response_model=list[LiveSessionDetail],
)
async def list_live_session_discovery(
    family_id: str,
    port: LiveSessionReadPort = Depends(get_live_session_read_port),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
) -> Any:
    """Discover approved, active family-guardian sessions; read only."""

    if family_id != ctx.family_id:
        raise HTTPException(status_code=403, detail="family_scope_violation")
    _authorize_live_read(actor=actor, ctx=ctx, engine=engine, recorder=recorder)
    try:
        sessions = await list_live_sessions(
            port,
            scope=LiveReadScope(
                tenant_id=ctx.tenant_id,
                family_id=ctx.family_id,
                actor_person_id=ctx.actor_person_id,
                actor_type=actor.actor_type,
                correlation_id=ctx.correlation_id,
            ),
        )
    except LiveReadError as exc:
        raise HTTPException(status_code=_read_error_status(exc), detail=exc.code) from exc

    recorder.record_read(
        actor_id=actor.actor_id,
        tenant_id=ctx.tenant_id,
        action="read_live_session_discovery",
        resource_type="LiveSession",
        resource_id=ctx.family_id,
        subject_person_id=ctx.actor_person_id,
        accessed_fields=PUBLIC_LIVE_SESSION_FIELDS,
        access_purpose="service_live_session_discovery",
        reason="guardian requested approved live-session discovery",
        correlation_id=ctx.correlation_id,
        subject_is_minor=False,
    )
    return list(sessions)


@router.get(
    "/families/{family_id}/live-sessions/{session_ref}",
    response_model=LiveSessionDetail,
)
async def get_live_session(
    family_id: str,
    session_ref: str,
    port: LiveSessionReadPort = Depends(get_live_session_read_port),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
) -> Any:
    """Read an approved family-guardian detail; no enter/playback semantics."""

    if family_id != ctx.family_id:
        raise HTTPException(status_code=403, detail="family_scope_violation")
    _authorize_live_read(actor=actor, ctx=ctx, engine=engine, recorder=recorder)
    try:
        detail = await get_live_session_detail(
            port,
            scope=LiveReadScope(
                tenant_id=ctx.tenant_id,
                family_id=ctx.family_id,
                actor_person_id=ctx.actor_person_id,
                actor_type=actor.actor_type,
                correlation_id=ctx.correlation_id,
            ),
            session_ref=session_ref,
        )
    except LiveReadError as exc:
        raise HTTPException(status_code=_read_error_status(exc), detail=exc.code) from exc

    # This endpoint returns no minor data.  The read audit still names the
    # guardian actor and exact public fields; if a future shape includes a child
    # subject it must add a purpose-bound minor approval before being exposed.
    recorder.record_read(
        actor_id=actor.actor_id,
        tenant_id=ctx.tenant_id,
        action="read_live_session_detail",
        resource_type="LiveSession",
        resource_id=detail.session_ref,
        subject_person_id=ctx.actor_person_id,
        accessed_fields=PUBLIC_LIVE_SESSION_FIELDS,
        access_purpose="service_live_session_detail",
        reason="guardian requested an approved live-session detail",
        correlation_id=ctx.correlation_id,
        subject_is_minor=False,
    )
    return detail


__all__ = ["router"]
