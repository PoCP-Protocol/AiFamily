"""Application query for the H-LIVE-01 approved-detail read."""

from __future__ import annotations

from datetime import UTC, datetime

from .live_ports import (
    LiveProjectionConflictError,
    LiveProjectionNotFoundError,
    LiveProjectionProviderError,
    LiveSessionProjectionPort,
)
from .live_read_models import LiveSessionDetailView, LiveSessionProjection


class LiveSessionScopeError(Exception):
    """The provider returned data outside the authenticated scope."""


class LiveSessionUnavailableError(Exception):
    """A row exists but is not currently eligible for adult discovery."""


def _utc(value: datetime) -> datetime:
    """Normalise provider timestamps before comparing them with current UTC."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def get_approved_session_detail(
    provider: LiveSessionProjectionPort,
    *,
    tenant_id: str,
    family_id: str,
    session_ref: str,
    now: datetime | None = None,
) -> LiveSessionDetailView:
    """Return one approved, unexpired, Family-scoped session projection.

    The route never manufactures a session when the provider is absent.  The
    provider owns truth; this query only applies the read contract and removes
    internal scope fields before returning the public model.
    """

    try:
        projection = await provider.get_session_projection(
            tenant_id=tenant_id,
            family_id=family_id,
            session_ref=session_ref,
        )
    except (LiveProjectionConflictError, LiveProjectionProviderError):
        raise
    except Exception as exc:  # pragma: no cover - defensive provider boundary
        raise LiveProjectionProviderError("live_projection_provider_failed") from exc

    if projection is None:
        raise LiveProjectionNotFoundError("live_session_not_found")
    if not isinstance(projection, LiveSessionProjection):
        raise LiveProjectionProviderError("live_projection_shape_invalid")
    if projection.tenant_id != tenant_id or projection.family_id != family_id:
        raise LiveSessionScopeError("live_projection_scope_mismatch")
    if projection.session_ref != session_ref:
        raise LiveProjectionProviderError("live_projection_ref_mismatch")

    current_time = _utc(now or datetime.now(UTC))
    if projection.review_status != "APPROVED":
        raise LiveSessionUnavailableError("live_session_not_approved")
    if not projection.audience_scope:
        raise LiveSessionUnavailableError("live_session_audience_scope_missing")
    if _utc(projection.ends_at) <= current_time:
        raise LiveSessionUnavailableError("live_session_expired")
    if projection.status in {"WITHDRAWN", "EXPIRED"}:
        raise LiveSessionUnavailableError(f"live_session_{projection.status.lower()}")
    if projection.family_visibility != "FAMILY_SCOPED":
        raise LiveSessionUnavailableError("live_session_visibility_not_family_scoped")

    return LiveSessionDetailView.from_projection(projection)
