"""Closed vocabularies for the service booking chain.

Every literal here mirrors a CHECK constraint or enum in
`database/baseline/0035_family_service_booking_objects.sql` (the linearised copy
of legacy `0032_family_service_booking_objects.sql`), so the Python side and the
schema cannot drift. That file is a *baselined historical artefact* and must not
be edited; the direction of authority is SQL → Python.

There is deliberately **no** `family_rating`, `child_progress` or any other
family-scored vocabulary here. `ServiceQualityRating` below rates *the service
provider* — see its docstring for why that is a different thing from R9's
prohibition, and `FORBIDDEN_SUBJECT_ATTRIBUTE_TOKENS` for the guard that keeps
the two apart.
"""

from __future__ import annotations

from typing import Literal

# `families`/`persons` scope. The booking chain is DEV/TEST-only supply: legacy
# `0032` pins `external_effect = false` and `environment IN ('DEV','TEST')` as
# CHECK constraints, and R5 forbids fixture data on a production route, so the
# Python side refuses PRODUCTION rather than letting a caller ask for it.
Environment = Literal["DEV", "TEST"]

# `family_booking_requests.source_system` / `family_booking_service_records.source_system`.
# Two distinct defaults in the DDL: a booking request is a TEST_FIXTURE, the
# service record is produced by a no-op adapter. Keeping both values in one
# vocabulary would let a record claim to be a fixture and vice versa.
BookingSourceSystem = Literal["TEST_FIXTURE"]
ServiceRecordSourceSystem = Literal["TEST_NOOP_ADAPTER"]

ScopeType = Literal["PLATFORM", "TENANT"]

# `family_service_provider_status` enum.
ProviderStatus = Literal["DRAFT", "ACTIVE", "SUSPENDED", "RETIRED"]
# `family_product_status` (shared enum) as used by family_service_offerings.
OfferingStatus = Literal["DRAFT", "ACTIVE", "SUSPENDED", "RETIRED"]
# `family_availability_slot_status` enum.
SlotStatus = Literal["AVAILABLE", "RESERVED", "BLOCKED", "EXPIRED"]
# `family_booking_request_status` enum.
BookingStatus = Literal["DRAFT", "REQUESTED", "CONFIRMED", "CANCELLED", "EXPIRED"]
# `family_booking_record_status` enum.
ServiceRecordStatus = Literal["PENDING", "SCHEDULED", "CANCELLED", "COMPLETED"]

# Family feedback is a bounded adult response, not a free-text child or family
# score.  The values describe whether the service helped and deliberately do
# not become a growth/quality score.
FamilyFeedbackOutcome = Literal["HELPFUL", "SOMEWHAT_HELPFUL", "NOT_HELPFUL_YET"]
FeedbackAuthorRole = Literal["GUARDIAN", "ADULT_FAMILY_MEMBER"]
QualityDecisionStatus = Literal["ACCEPTED", "REWORK_REQUIRED", "REFUND_REQUIRED"]
ServiceActionType = Literal[
    "WELCOME",
    "NEEDS_IDENTIFIED",
    "FIRST_RESPONSE",
    "FOLLOW_UP",
    "REMEDY_REWORK",
    "REMEDY_REASSIGN",
    "REFUND_REQUESTED",
]
ServiceEventStatus = Literal["PENDING", "PUBLISHED", "DEAD_LETTER"]
FeedbackIssueCode = Literal[
    "NO_SHOW",
    "LATE_START",
    "NEED_MISSED",
    "DELIVERY_INCOMPLETE",
    "SAFETY_CONCERN",
    "OTHER_SERVICE_ISSUE",
]

FAMILY_FEEDBACK_OUTCOMES = frozenset({"HELPFUL", "SOMEWHAT_HELPFUL", "NOT_HELPFUL_YET"})
QUALITY_DECISION_STATUSES = frozenset({"ACCEPTED", "REWORK_REQUIRED", "REFUND_REQUIRED"})
SERVICE_ACTION_TYPES = frozenset(
    {
        "WELCOME",
        "NEEDS_IDENTIFIED",
        "FIRST_RESPONSE",
        "FOLLOW_UP",
        "REMEDY_REWORK",
        "REMEDY_REASSIGN",
        "REFUND_REQUESTED",
    }
)
FEEDBACK_ISSUE_CODES = frozenset(
    {
        "NO_SHOW",
        "LATE_START",
        "NEED_MISSED",
        "DELIVERY_INCOMPLETE",
        "SAFETY_CONCERN",
        "OTHER_SERVICE_ISSUE",
    }
)

ProviderKind = Literal["TEACHER", "SALON_HOST", "SERVICE_TEAM"]
QualificationStatus = Literal["ACTIVE", "MISSING", "EXPIRED"]
AdmissionStatus = Literal["ADMITTED", "EXPIRED", "SUSPENDED"]
Channel = Literal["VIDEO", "TEXT", "OFFLINE"]

# `family_booking_requests.source_page_id` CHECK. UI-19 browse, UI-20 detail,
# UI-21 book, UI-24 my-bookings — the four surfaces the verified loop covers.
BookingSourcePageId = Literal["UI-19", "UI-20", "UI-21", "UI-24"]
BOOKING_SOURCE_PAGE_IDS: frozenset[str] = frozenset({"UI-19", "UI-20", "UI-21", "UI-24"})

# `CreatePrivateCheckinDraft` allow-list, from the UI-06 contract §4.1. Free text
# is deliberately not accepted in this slice: an allow-list cannot carry a child
# fact, a free-text field can.
CheckinActionRef = Literal["WEEKLY_ACTION_SEE", "WEEKLY_ACTION_ADJUST", "PAUSE_AND_RETURN"]
CHECKIN_ACTION_REFS: frozenset[str] = frozenset(
    {"WEEKLY_ACTION_SEE", "WEEKLY_ACTION_ADJUST", "PAUSE_AND_RETURN"}
)

# Quality feedback about the *provider's* service delivery. This is allowed and
# is not what R9 forbids:
#
#   R9 forbids scoring or ranking **families and children** — the platform must
#   never tell a family "you are a 72". Rating a purchased service is the
#   customer evaluating the vendor, which is the opposite direction of power and
#   carries none of the harm R9 exists to prevent.
#
# The distinction is enforced structurally, not by comment: the rating lives on
# `ServiceRecord` (a delivery fact about the provider's session) and the field
# name has no family/child subject token, so
# `tests/architecture/test_compliance_constraints.py::
# test_no_scoring_or_ranking_fields_anywhere` stays green *because the shape is
# right*, not because it was exempted.
ServiceQualityRating = Literal["POSITIVE", "NEUTRAL", "NEEDS_FOLLOW_UP"]

AI_ACTOR_PREFIX = "ai:"

# Tokens that must never appear as a key in a booking's or record's `attributes`
# JSON. `attributes` is the one untyped escape hatch in the chain, so it is the
# one place `{"child_score": 87}` could be smuggled past the typed fields.
#
# Note this deliberately does NOT ban the bare word "rating"/"score": it bans
# them **paired with a family/child/parent subject**, matching the two-part rule
# the repository-level checker uses. Banning them outright would forbid the
# legitimate provider-quality vocabulary above while protecting nobody extra.
FORBIDDEN_SUBJECT_TOKENS: frozenset[str] = frozenset(
    {"family", "child", "parent", "guardian", "student", "member", "kid"}
)
FORBIDDEN_SCORING_TOKENS: frozenset[str] = frozenset(
    {"score", "rank", "ranking", "grade", "percentile", "leaderboard", "progress_pct", "rating"}
)
