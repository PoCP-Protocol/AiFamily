"""Read-only H-LIVE-01 HTTP route for the Xiaojudeng Live product."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.platform.audit.recorder import AuditRecorder
from backend.platform.authorization.policy import PolicyEngine
from backend.platform.identity.context import ActorContext

from ..application.context import ActionContext
from ..application.live_ports import (
    LiveProjectionConflictError,
    LiveProjectionNotFoundError,
    LiveProjectionProviderError,
    LiveSessionProjectionPort,
)
from ..application.live_queries import (
    LiveSessionScopeError,
    LiveSessionUnavailableError,
    get_approved_session_detail,
)
from ..application.live_read_models import LiveSessionDetailView
from . import dependencies as service_dependencies
from .dependencies import (
    LIVE_SESSION_RESOURCE,
    READ_LIVE_SESSION_ACTION,
    get_live_policy_engine,
    get_live_projection,
)

router = APIRouter(tags=["live"])


def _assert_authenticated_family(
    family_id: str, context: ActionContext, actor: ActorContext
) -> None:
    """The URL cannot select a family different from authenticated context."""

    if family_id != context.family_id or actor.tenant_id != context.tenant_id:
        raise HTTPException(status_code=403, detail="family_scope_violation")


def require_authenticated_family(
    family_id: str,
    context: ActionContext = Depends(service_dependencies.get_action_context),
    actor: ActorContext = Depends(service_dependencies.get_actor_context),
) -> None:
    """Reject a cross-family request before resolving the live provider."""

    _assert_authenticated_family(family_id, context, actor)


@router.get(
    "/families/{family_id}/live-sessions/{session_ref}",
    response_model=LiveSessionDetailView,
)
async def get_live_session_detail(
    family_id: str,
    session_ref: str,
    _scope: None = Depends(require_authenticated_family),
    projection: LiveSessionProjectionPort = Depends(get_live_projection),
    context: ActionContext = Depends(service_dependencies.get_action_context),
    actor: ActorContext = Depends(service_dependencies.get_actor_context),
    policy: PolicyEngine = Depends(get_live_policy_engine),
    recorder: AuditRecorder = Depends(service_dependencies.get_audit_recorder),
) -> LiveSessionDetailView:
    """Read an approved, current, Family-scoped live-session projection only."""

    _assert_authenticated_family(family_id, context, actor)
    decision = policy.check(actor, READ_LIVE_SESSION_ACTION, LIVE_SESSION_RESOURCE)
    if not decision.allowed:
        raise HTTPException(status_code=403, detail=decision.reason)

    try:
        detail = await get_approved_session_detail(
            projection,
            tenant_id=context.tenant_id,
            family_id=context.family_id,
            session_ref=session_ref,
        )
    except LiveProjectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LiveSessionUnavailableError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LiveSessionScopeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LiveProjectionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LiveProjectionProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    recorder.record_read(
        actor_id=actor.actor_id,
        tenant_id=context.tenant_id,
        action=READ_LIVE_SESSION_ACTION,
        resource_type=LIVE_SESSION_RESOURCE,
        resource_id=detail.session_ref,
        subject_person_id=context.actor_person_id,
        accessed_fields=(
            "session_ref",
            "title",
            "presenter_name",
            "audience_scope",
            "starts_at",
            "ends_at",
            "review_ref",
            "review_version",
            "status",
            "family_visibility",
            "as_of",
            "source",
            "fixture_only",
        ),
        access_purpose="LIVE_DISCOVERY",
        reason="adult_family_scoped_live_discovery",
        correlation_id=context.correlation_id,
        subject_is_minor=False,
    )
    return detail
