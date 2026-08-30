"""ConsentGate — pure in-process consent check, no caching, no DB.

The one non-negotiable requirement carried over from
`FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md` section 10 (and kept in force by
REPOSITORY_CONSTITUTION.md's disposition for `platform_consent`): a withdrawn
consent must take effect immediately. `ConsentGate` enforces this by
construction — it holds no cache and re-evaluates the grants it is given on
every call. There is nothing here that could go stale, because there is
nothing stored between calls at all.

Wiring this to a real database (querying current ConsentGrant rows for a
subject/purpose) is explicitly deferred to whichever domain repository first
needs it (per the task instructions) — that repository must call
`ConsentGate.check` with the *current* grants it just read, not a cached
list from an earlier request.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from backend.platform.consent.models import ConsentGrant, ConsentPurpose


class ConsentGate:
    """Stateless consent check over an explicitly supplied set of grants."""

    @staticmethod
    def check(
        subject_id: str,
        purpose: ConsentPurpose,
        grants: Iterable[ConsentGrant],
        *,
        at: datetime | None = None,
    ) -> bool:
        """Return True iff a grant is active for this subject/purpose at ``at``.

        `grants` must be freshly read by the caller (e.g. from a repository
        inside the current UnitOfWork) — this method performs no I/O and
        keeps no state across calls, so a withdrawn grant is honored the
        instant the caller passes in the updated grant list. There is no
        code path here that can return a stale ALLOW.

        ``at`` is the evaluation time for the grant's effective window. It is
        optional to preserve the original call contract; omitted means the
        current UTC time. Supplying it is required for deterministic replay
        and lets legacy grants use their ``granted_at``/``expires_at`` window
        without a separate status-flipping job.
        """
        moment = at if at is not None else datetime.now(UTC)
        for grant in grants:
            if (
                grant.subject_person_id == subject_id
                and grant.purpose is purpose
                and grant.is_active_at(moment)
            ):
                return True
        return False
