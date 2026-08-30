"""H-LIVE-01 read query with all visibility gates applied."""

from __future__ import annotations

from datetime import UTC, datetime

from .live_ports import (
    LiveReadForbiddenError,
    LiveReadNotFoundError,
    LiveReadScope,
    LiveSessionReadPort,
)
from .live_read_models import LiveSessionDetail, public_detail


async def get_live_session_detail(
    port: LiveSessionReadPort,
    *,
    scope: LiveReadScope,
    session_ref: str,
    now: datetime | None = None,
) -> LiveSessionDetail:
    """Return one approved, unexpired family-guardian detail.

    The port receives the trusted scope, and the query repeats the scope check
    against the returned candidate.  This protects the route if an adapter
    accidentally ignores one of its parameters.
    """

    if not session_ref.strip():
        raise LiveReadNotFoundError
    if scope.actor_type.value != "human":
        raise LiveReadForbiddenError("live_session_guardian_human_required")

    candidate = await port.get_session(
        tenant_id=scope.tenant_id,
        family_id=scope.family_id,
        session_ref=session_ref,
    )
    if candidate is None:
        raise LiveReadNotFoundError
    if candidate.tenant_id != scope.tenant_id or candidate.family_id != scope.family_id:
        raise LiveReadForbiddenError("live_session_scope_violation")
    if scope.actor_person_id not in candidate.guardian_person_ids:
        raise LiveReadForbiddenError("live_session_guardian_scope_violation")
    if not candidate.approved:
        raise LiveReadNotFoundError
    current = now or datetime.now(UTC)
    if not candidate.is_unexpired_at(current):
        raise LiveReadNotFoundError

    return public_detail(candidate)


__all__ = ["get_live_session_detail"]
