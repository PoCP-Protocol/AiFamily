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
from datetime import datetime

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
        """Return True iff a matching grant is active at the evaluation time.

        `grants` must be freshly read by the caller (e.g. from a repository
        inside the current UnitOfWork) — this method performs no I/O and
        keeps no state across calls, so a withdrawn grant is honored the
        instant the caller passes in the updated grant list. There is no
        code path here that can return a stale ALLOW.

        ``at`` is optional for compatibility with the original three-argument
        contract. Newer ``ConsentGrant`` implementations expose
        ``is_active_at`` so expiry and future effective windows are evaluated
        against the caller's explicit moment. Older grants only expose the
        ``is_active`` property, which remains the compatibility fallback.
        """
        for grant in grants:
            if grant.subject_person_id == subject_id and grant.purpose is purpose:
                if at is None:
                    is_active = grant.is_active
                else:
                    is_active_at = getattr(grant, "is_active_at", None)
                    is_active = is_active_at(at) if callable(is_active_at) else grant.is_active
                if is_active:
                    return True
        return False
