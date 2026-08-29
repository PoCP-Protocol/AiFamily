"""Membership value objects.

Source of truth: `docs/FAMILY_MEMBERSHIP_OS_V2_BASELINE.md`.

Two things in this module are load-bearing guardrails, not conveniences:

1. `TierCode` has exactly three values and **no numeric level**. There is no
   `level`, `score`, `rank` or `progress` value object anywhere in this
   domain — baseline invariant 7 ("a tier cannot imply a child/family
   ability, safety level, or ranking") plus the repo hard rules
   "不做 Family Total Score / 不做家庭 Ranking".
2. `ActivationSourceType` is a closed allow-list, and
   `FORBIDDEN_ACTIVATION_SOURCE_TYPES` names the sources that must never be
   able to move a tier — points (invariant 4), AI (invariant 3), community
   role (invariant 6), referral draft (invariant 5).
"""

from __future__ import annotations

from typing import Final, Literal

TierCode = Literal["M0_FREE", "M1_GROWTH", "M2_ANNUAL"]

TIER_CODES: Final[tuple[str, ...]] = ("M0_FREE", "M1_GROWTH", "M2_ANNUAL")

# Relationship depth ordering. Used ONLY to label a transition direction in
# the audit fact (UPGRADE / DOWNGRADE / LATERAL). It is deliberately private
# to this module's helpers and never persisted, exposed on an entity, or
# rendered — a tier is not a score and must not acquire one by the back door.
_TIER_DEPTH: Final[dict[str, int]] = {"M0_FREE": 0, "M1_GROWTH": 1, "M2_ANNUAL": 2}

TransitionDirection = Literal["UPGRADE", "DOWNGRADE", "LATERAL", "INITIAL"]

ActivationSourceType = Literal[
    "FAMILY_ACCOUNT_CREATED",
    "GROWTH_PRODUCT_ACTIVATED",
    "ANNUAL_MEMBERSHIP_ACTIVATED",
    "ANNUAL_MEMBERSHIP_RENEWED",
    "ADMIN_MANUAL_GRANT",
    "MEMBERSHIP_PERIOD_EXPIRED",
    "SUBSCRIPTION_CANCELLED",
]

ACTIVATION_SOURCE_TYPES: Final[tuple[str, ...]] = (
    "FAMILY_ACCOUNT_CREATED",
    "GROWTH_PRODUCT_ACTIVATED",
    "ANNUAL_MEMBERSHIP_ACTIVATED",
    "ANNUAL_MEMBERSHIP_RENEWED",
    "ADMIN_MANUAL_GRANT",
    "MEMBERSHIP_PERIOD_EXPIRED",
    "SUBSCRIPTION_CANCELLED",
)

# Named explicitly so the refusal is testable and greppable rather than an
# implicit consequence of the allow-list.
FORBIDDEN_ACTIVATION_SOURCE_TYPES: Final[frozenset[str]] = frozenset(
    {
        "POINTS_REDEMPTION",  # invariant 4
        "POINTS_BALANCE",  # invariant 4
        "AI_RECOMMENDATION",  # invariant 3
        "AI_AUTO_UPGRADE",  # invariant 3
        "REFERRAL_DRAFT",  # invariant 5
        "COMMUNITY_ROLE",  # invariant 6
        "GROWTH_STAGE",  # four-axis separation
        "FAMILY_SCORE",  # 不做 Family Total Score
        "CHILD_ASSESSMENT_SCORE",  # 不做 Child Score
        "FAMILY_RANKING",  # 不做家庭 Ranking
    }
)

# Which target tier each activation source is allowed to produce. A source
# outside its target set is rejected even though both values are individually
# legal — invariant 1 requires the transition to be deterministic, which means
# source and target must agree.
ACTIVATION_TARGET_MATRIX: Final[dict[str, frozenset[str]]] = {
    "FAMILY_ACCOUNT_CREATED": frozenset({"M0_FREE"}),
    "GROWTH_PRODUCT_ACTIVATED": frozenset({"M1_GROWTH"}),
    "ANNUAL_MEMBERSHIP_ACTIVATED": frozenset({"M2_ANNUAL"}),
    "ANNUAL_MEMBERSHIP_RENEWED": frozenset({"M2_ANNUAL"}),
    "ADMIN_MANUAL_GRANT": frozenset({"M0_FREE", "M1_GROWTH", "M2_ANNUAL"}),
    "MEMBERSHIP_PERIOD_EXPIRED": frozenset({"M0_FREE"}),
    "SUBSCRIPTION_CANCELLED": frozenset({"M0_FREE"}),
}

SubscriptionStatus = Literal["PENDING", "ACTIVE", "PAUSED", "EXPIRED", "CANCELLED"]
PeriodStatus = Literal["ACTIVE", "CLOSED"]
PlanStatus = Literal["DRAFT", "ACTIVE", "SUSPENDED", "RETIRED"]
BenefitStatus = Literal["PENDING", "AVAILABLE", "CONSUMED", "REVOKED", "EXPIRED"]
BenefitAction = Literal["GRANT", "CONSUME", "REVOKE"]
AllocationType = Literal["COUNT", "ACCESS", "CREDIT"]
ReservationStatus = Literal["HELD", "RELEASED", "CONSUMED", "EXPIRED"]
ScopeType = Literal["PLATFORM", "TENANT"]

# Production boundary from the baseline "Production Boundary" section. Kept as
# value objects so the domain layer — not just the DB CHECK constraints — can
# refuse anything outside it.
Environment = Literal["DEV", "TEST"]
SourceSystem = Literal["TEST_NOOP_ADAPTER"]

# `family_membership_benefit_ledger.source_page_id` CHECK in migration 0033.
LedgerSourcePageId = Literal["UI-30", "UI-31", "UI-32"]

AI_ACTOR_PREFIX: Final[str] = "ai:"


def transition_direction(from_tier: str | None, to_tier: str) -> TransitionDirection:
    """Label a transition for the audit fact. Not a score, not comparable
    across families, never surfaced as a progress bar.
    """
    if from_tier is None:
        return "INITIAL"
    before, after = _TIER_DEPTH[from_tier], _TIER_DEPTH[to_tier]
    if after > before:
        return "UPGRADE"
    if after < before:
        return "DOWNGRADE"
    return "LATERAL"
