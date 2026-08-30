"""Family-scoped, read-only H-LIVE-01 route."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.platform.audit.recorder import AuditRecorder
from backend.platform.authorization.policy import PolicyEngine
from backend.platform.identity.context import ActorContext

from ..application import live_queries
from ..application.context import ActionContext
from ..application.live_ports import LiveSessionReadPort
from ..application.live_read_models import (
    PUBLIC_LIVE_SESSION_FIELDS,
    ApprovedLiveSessionDetail,
)
from .dependencies import (
    get_action_context,
    get_actor_context,
    get_audit_recorder,
    get_live_session_reader,
    get_policy_engine,
    resource_for,
)
from .routes import _assert_path_family, _authorize

router = APIRouter(tags=["live"])


@router.get(
    "/families/{family_id}/live-sessions/{session_ref}",
    response_model=ApprovedLiveSessionDetail,
)
async def get_live_session_detail(
    family_id: str,
    session_ref: str,
    reader: LiveSessionReadPort | None = Depends(get_live_session_reader),
    ctx: ActionContext = Depends(get_action_context),
    actor: ActorContext = Depends(get_actor_context),
    engine: PolicyEngine = Depends(get_policy_engine),
    recorder: AuditRecorder = Depends(get_audit_recorder),
) -> ApprovedLiveSessionDetail:
    """Read one approved session without any booking or media side effect."""

    _assert_path_family(family_id, ctx)
    if actor.tenant_id != ctx.tenant_id or actor.actor_id != ctx.actor_person_id:
        raise HTTPException(status_code=403, detail="actor_scope_violation")
    _authorize(engine, actor, "read_live_session", recorder, ctx)

    if reader is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="live_session_read_provider_unavailable",
        )

    detail = await live_queries.get_approved_live_session(
        reader,
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
        session_ref=session_ref,
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="live_session_not_found_or_not_admitted",
        )

    recorder.record_read(
        actor_id=actor.actor_id,
        tenant_id=ctx.tenant_id,
        action="read_live_session",
        resource_type=resource_for("read_live_session"),
        resource_id=detail.session_ref,
        subject_person_id=actor.actor_id,
        accessed_fields=PUBLIC_LIVE_SESSION_FIELDS,
        access_purpose="LIVE_SESSION_DISCOVERY",
        reason="approved_family_scoped_live_session_detail",
        correlation_id=ctx.correlation_id,
        subject_is_minor=False,
    )
    return detail
