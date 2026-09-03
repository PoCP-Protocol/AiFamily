"""ConsentGate — pure in-process consent check, no caching, no DB.

The one non-negotiable requirement carried over from
`FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md` section 10 (and kept in force by
REPOSITORY_CONSTITUTION.md's disposition for `platform_consent`): a withdrawn
consent must take effect immediately. `ConsentGate` enforces this by
construction — it holds no cache and re-evaluates the grants it is given on
every call. There is nothing here that could go stale, because there is
nothing stored between calls at all.

Expiry follows the same rule. `check` evaluates each grant against a moment
(defaulting to now) via `ConsentGrant.is_active_at`, so a grant past its
`expires_at` stops permitting things the instant it passes, with no scheduled job
in the loop. A background job that flipped stored statuses to EXPIRED would be a
second source of truth that is wrong for as long as it is behind.

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
        at: datetime | None = None,
    ) -> bool:
        """Return True iff there exists an in-force grant for this subject/purpose.

        `grants` must be freshly read by the caller (e.g. from a repository
        inside the current UnitOfWork) — this method performs no I/O and
        keeps no state across calls, so a withdrawn grant is honored the
        instant the caller passes in the updated grant list. There is no
        code path here that can return a stale ALLOW.

        `at` exists so expiry is testable and so a caller reconstructing a past
        decision can ask what was permitted *then*. It defaults to now; it does
        not default to "ignore expiry", because a default that skipped the
        retention period would make 第12条 unenforceable by omission.

        REFUSED, WITHDRAWN and EXPIRED all deny. They remain distinct on the
        grant itself: this method answers a yes/no question, and a caller that
        needs to know *why* (to avoid re-prompting a refusal, for instance) reads
        `ConsentGrant.status_at`.
        """
        moment = at or datetime.now(UTC)
        for grant in grants:
            if (
                grant.subject_person_id == subject_id
                and grant.purpose is purpose
                and grant.is_active_at(moment)
            ):
                return True
        return False
