"""Application query for the H-LIVE-01 approved-session detail."""

from __future__ import annotations

from datetime import UTC, datetime

from .live_ports import LiveSessionReadPort
from .live_read_models import ApprovedLiveSessionDetail

_EXPLICIT_FIXTURE_SOURCES = frozenset({"DEV_FIXTURE", "TEST_FIXTURE", "SYNTHETIC_FIXTURE"})


def _now() -> datetime:
    return datetime.now(UTC)


async def get_approved_live_session(
    reader: LiveSessionReadPort | None,
    *,
    tenant_id: str,
    family_id: str,
    session_ref: str,
    as_of: datetime | None = None,
) -> ApprovedLiveSessionDetail | None:
    """Return only an admitted, current, family-visible session.

    A missing reader is a deployment configuration gap, represented by the
    route as 503.  A missing or non-admitted record is indistinguishable from a
    not-found response, preventing disclosure of review state or another
    family's session.
    """

    if reader is None:
        return None

    observed_at = as_of or _now()
    candidate = await reader.find_session(
        tenant_id=tenant_id,
        family_id=family_id,
        session_ref=session_ref,
        as_of=observed_at,
    )
    if candidate is None:
        return None
    if candidate.tenant_id != tenant_id or candidate.family_id != family_id:
        return None
    if candidate.session_ref != session_ref:
        return None
    if not candidate.approved:
        return None
    if candidate.family_visibility != "FAMILY":
        return None
    if candidate.status not in {"SCHEDULED", "LIVE"}:
        return None
    if candidate.ends_at <= observed_at:
        return None
    if not candidate.audience_scope.strip():
        return None
    source = candidate.source.upper()
    if source == "BASELINE_CONTENT":
        return None
    if candidate.fixture_only and source not in _EXPLICIT_FIXTURE_SOURCES:
        return None
    if not candidate.fixture_only and source in _EXPLICIT_FIXTURE_SOURCES:
        return None

    return ApprovedLiveSessionDetail(
        session_ref=candidate.session_ref,
        title=candidate.title,
        host_display_name=candidate.host_display_name,
        audience_scope=candidate.audience_scope,
        starts_at=candidate.starts_at,
        ends_at=candidate.ends_at,
        approval_ref=candidate.approval_ref,
        approval_version=candidate.approval_version,
        status=candidate.status,
        family_visibility="FAMILY",
        as_of=observed_at,
        source=candidate.source,
        fixture_only=candidate.fixture_only,
    )
