"""Read-only ports for H-LIVE-01.

This file defines an adapter seam, not a second service backend.  The port has
one read operation and deliberately has no methods for entering, booking,
starting, replaying, or mutating a session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.platform.identity.context import ActorType

from .live_read_models import LiveSessionCandidate


class LiveReadError(Exception):
    """Base error for the fail-closed H-LIVE-01 read contract."""

    code = "live_session_read_failed"

    def __init__(self, code: str | None = None) -> None:
        self.code = code or type(self).code
        super().__init__(self.code)


class LiveReadNotFoundError(LiveReadError):
    """No publishable session is visible in the requested scope."""

    code = "live_session_not_found"


class LiveReadForbiddenError(LiveReadError):
    """A scope, audience, approval, or source invariant failed."""

    code = "live_session_scope_forbidden"


@dataclass(frozen=True, slots=True)
class LiveReadScope:
    """Server-derived scope for one guardian read.

    ``family_id`` and ``actor_person_id`` come from trusted context, never from
    the request body.  The candidate must independently list that person in its
    guardian audience; a family URL alone is not sufficient authorization.
    """

    tenant_id: str
    family_id: str
    actor_person_id: str
    actor_type: ActorType
    correlation_id: str


class LiveSessionReadPort(Protocol):
    """Canonical source adapter for one tenant/family-scoped read."""

    async def get_session(
        self, *, tenant_id: str, family_id: str, session_ref: str
    ) -> LiveSessionCandidate | None:
        """Return the candidate already scoped by tenant/family, or ``None``."""

        ...


__all__ = [
    "LiveReadError",
    "LiveReadForbiddenError",
    "LiveReadNotFoundError",
    "LiveReadScope",
    "LiveSessionReadPort",
]
