"""Ports for H-LIVE-01's canonical live-session read projection."""

from __future__ import annotations

from typing import Protocol

from .live_read_models import LiveSessionProjection


class LiveProjectionNotFoundError(Exception):
    """The canonical projection has no visible row for this session."""


class LiveProjectionConflictError(Exception):
    """The canonical source cannot provide one unambiguous projection."""


class LiveProjectionProviderError(Exception):
    """The canonical projection provider failed or returned invalid data."""


class LiveSessionProjectionPort(Protocol):
    """Read-only seam to the owning canonical live projection.

    Implementations must query the authoritative source.  A test fixture may
    implement this port only in DEV/TEST and must set ``fixture_only=True``.
    """

    async def get_session_projection(
        self, *, tenant_id: str, family_id: str, session_ref: str
    ) -> LiveSessionProjection | None: ...
