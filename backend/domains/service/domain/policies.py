"""Service booking invariants — one function per rule, no repository needed.

These live here rather than inline in `application/commands.py` for the reason
membership's `policies.py` gives: a rule that is only enforced at one call site
stops being enforced the moment a second call site appears. Every command goes
through these.
"""

from __future__ import annotations

from .errors import ServiceForbiddenError, ServiceValidationError
from .value_objects import (
    AI_ACTOR_PREFIX,
    BOOKING_SOURCE_PAGE_IDS,
    CHECKIN_ACTION_REFS,
    FORBIDDEN_SCORING_TOKENS,
    FORBIDDEN_SUBJECT_TOKENS,
)


def assert_human_actor(actor: str, *, code: str) -> None:
    """R9 — AI may surface a recommendation, never commit a family to a service.

    Booking a real human being's time is precisely the class of act R8 lists as
    high-impact. An `ai:`-prefixed actor is refused at the domain boundary, so
    the refusal holds even if a route forgets to register a policy rule.
    """
    if not actor or not actor.strip():
        raise ServiceValidationError(f"{code}_actor_required")
    if actor.startswith(AI_ACTOR_PREFIX):
        raise ServiceForbiddenError(f"{code}_requires_human_actor")


def assert_fixture_boundary(
    *, environment: str, source_system: str, external_effect: bool, allowed_source_system: str
) -> None:
    """R5 — the whole booking chain is fixture-only supply.

    Legacy `0032` pins `external_effect = false` and `environment IN
    ('DEV','TEST')` as CHECK constraints, and the source repository's service
    was explicit that a booking "is not a confirmed real-world appointment": it
    sends no notification, contacts nobody, and reserves no real calendar. That
    boundary is re-asserted here as a domain invariant so it survives a
    repository swap — a CHECK constraint protects Postgres, not the SQLite test
    path or the in-memory fake.
    """
    if environment not in ("DEV", "TEST"):
        raise ServiceForbiddenError(f"environment_not_allowed:{environment}")
    if source_system != allowed_source_system:
        raise ServiceForbiddenError(f"source_system_not_allowed:{source_system}")
    if external_effect:
        raise ServiceForbiddenError("external_effect_not_allowed")


def assert_booking_source_page(source_page_id: str) -> None:
    """`family_booking_requests.source_page_id` CHECK — a booking may only
    originate from one of the four verified surfaces."""
    if source_page_id not in BOOKING_SOURCE_PAGE_IDS:
        raise ServiceForbiddenError(f"booking_source_page_forbidden:{source_page_id}")


def assert_checkin_action_ref(action_ref: str) -> None:
    """UI-06 contract §4.1 — allow-listed selections only, no free text.

    422 in the source contract (`unsupported_private_checkin_action_ref`), which
    the API layer maps from `ServiceValidationError`.
    """
    if action_ref not in CHECKIN_ACTION_REFS:
        raise ServiceValidationError(f"unsupported_private_checkin_action_ref:{action_ref}")


def assert_no_family_scoring_semantics(attributes: dict) -> None:
    """R9 applied to the untyped `attributes` escape hatch.

    Two-part rule matching `tests/architecture/test_compliance_constraints.py`:
    a key is refused when it pairs a *family/child subject* with a *scoring
    verb*. `{"service_quality_rating": "POSITIVE"}` passes (rates the vendor);
    `{"child_rating": 4}` does not (rates a child).
    """
    for key in attributes:
        lowered = str(key).lower()
        has_subject = any(token in lowered for token in FORBIDDEN_SUBJECT_TOKENS)
        scoring_hit = next((t for t in FORBIDDEN_SCORING_TOKENS if t in lowered), None)
        if has_subject and scoring_hit:
            raise ServiceForbiddenError(f"family_scoring_semantics_forbidden:{lowered}")


def assert_family_scope(*, expected_family_id: str, actual_family_id: str) -> None:
    """Cross-family access is a refusal, not a 404.

    Scope always comes from the authenticated context in this domain, so this
    is the second line of defence for the places where an entity loaded by id
    must be re-checked against the caller's family before being returned.
    """
    if expected_family_id != actual_family_id:
        raise ServiceForbiddenError("family_scope_violation")
