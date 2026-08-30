"""Ports for the read-only H-LIVE-01 projection."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .live_read_models import LiveSessionCandidate


class LiveSessionReadPort(Protocol):
    """Read-only seam for an admitted live-session source.

    The provider receives server-derived tenant/family scope and an explicit
    point in time.  It cannot be satisfied by the existing service-booking
    AvailabilitySlot repository, whose semantics remain consultation booking.
    """

    async def find_session(
        self,
        *,
        tenant_id: str,
        family_id: str,
        session_ref: str,
        as_of: datetime,
    ) -> LiveSessionCandidate | None: ...
