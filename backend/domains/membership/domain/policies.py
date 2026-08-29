"""Membership transition invariants, one function per baseline rule.

`docs/FAMILY_MEMBERSHIP_OS_V2_BASELINE.md` "Transition Invariants" 1-8 are
implemented here rather than inline in the application layer, so that the
rules are (a) unit-testable without a repository, (b) impossible to bypass by
adding a new command that forgets one of them — `assert_tier_transition_legal`
is the single gate every tier write goes through.
"""

from __future__ import annotations

from .errors import (
    MembershipForbiddenError,
    MembershipValidationError,
)
from .value_objects import (
    ACTIVATION_TARGET_MATRIX,
    AI_ACTOR_PREFIX,
    FORBIDDEN_ACTIVATION_SOURCE_TYPES,
    TIER_CODES,
    TransitionDirection,
    transition_direction,
)

# Field names that must never appear on a membership entity. Enforced by a
# guardrail test that reflects over every model in `entities.py`.
FORBIDDEN_TIER_FIELD_TOKENS: frozenset[str] = frozenset(
    {"score", "level", "rank", "ranking", "grade", "percentile", "progress_pct"}
)

# Activation sources permitted to record a same-tier (LATERAL) transition.
#
# The general rule is that a from_tier == to_tier write is a no-op and must be
# refused, because it would create an audit fact claiming a change that did not
# happen. Two sources are genuine exceptions:
#
# * ADMIN_MANUAL_GRANT — an explicit operator re-grant.
# * ANNUAL_MEMBERSHIP_RENEWED — baseline invariant 8: renewal is an *append*.
#   The current period closes and a new `seq_no` opens at the same tier, so the
#   tier legitimately does not change while a real, auditable event did occur.
#
# ANNUAL_MEMBERSHIP_RENEWED was missing from this exemption when the domain was
# bulk-migrated, which made `renew_membership_period()` raise
# `tier_transition_is_noop` on every call — i.e. annual renewal could never
# succeed. The domain carried zero tests in the source repository, so nothing
# caught it. Found by `tests/domains/membership/test_acceptance_chain.py::
# test_annual_renewal_appends_a_new_period`.
SAME_TIER_ALLOWED_SOURCES: frozenset[str] = frozenset(
    {"ADMIN_MANUAL_GRANT", "ANNUAL_MEMBERSHIP_RENEWED"}
)


def assert_human_actor(actor: str, *, code: str) -> None:
    """Baseline invariant 3: AI may recommend an upgrade, but cannot grant or
    mutate the tier. An `ai:`-prefixed actor ref is refused at the domain
    boundary — same convention as
    `product_intelligence.GrowthHypothesis.mark_validated`.
    """
    if not actor or not actor.strip():
        raise MembershipValidationError(f"{code}_actor_required")
    if actor.startswith(AI_ACTOR_PREFIX):
        raise MembershipForbiddenError(f"{code}_requires_human_actor")


def assert_activation_source_allowed(activation_source_type: str) -> None:
    """Baseline invariants 4/5/6 + the four-axis separation.

    Checked against the explicit deny-list first so the error code tells the
    caller *why* (points/AI/referral/community) instead of a generic "unknown
    enum value".
    """
    if activation_source_type in FORBIDDEN_ACTIVATION_SOURCE_TYPES:
        raise MembershipForbiddenError(
            f"activation_source_forbidden:{activation_source_type.lower()}"
        )
    if activation_source_type not in ACTIVATION_TARGET_MATRIX:
        raise MembershipValidationError(f"activation_source_unknown:{activation_source_type}")


def assert_deterministic_activation(
    activation_source_type: str, activation_source_ref: str
) -> None:
    """Baseline invariant 1: a tier change must have a deterministic
    `activation_source_type` AND `activation_source_ref`. A type without a
    concrete ref is not deterministic — it is a story about a transition.
    """
    assert_activation_source_allowed(activation_source_type)
    if not activation_source_ref or not activation_source_ref.strip():
        raise MembershipValidationError("activation_source_ref_required")


def assert_tier_transition_legal(
    *,
    from_tier: str | None,
    to_tier: str,
    activation_source_type: str,
    activation_source_ref: str,
    decided_by: str,
) -> TransitionDirection:
    """The single gate for every tier write. Returns the audit direction label.

    Covers invariants 1 (deterministic source), 3 (human actor), 4/5/6
    (forbidden sources) and the source↔target agreement that makes the
    transition reproducible.
    """
    if to_tier not in TIER_CODES:
        raise MembershipValidationError(f"tier_code_unknown:{to_tier}")
    if from_tier is not None and from_tier not in TIER_CODES:
        raise MembershipValidationError(f"tier_code_unknown:{from_tier}")

    assert_deterministic_activation(activation_source_type, activation_source_ref)
    assert_human_actor(decided_by, code="tier_transition")

    allowed_targets = ACTIVATION_TARGET_MATRIX[activation_source_type]
    if to_tier not in allowed_targets:
        raise MembershipValidationError(
            f"activation_source_target_mismatch:{activation_source_type}->{to_tier}"
        )
    if from_tier == to_tier and activation_source_type not in SAME_TIER_ALLOWED_SOURCES:
        # A no-op transition would create an audit fact claiming a change that
        # did not happen. Only the sources in SAME_TIER_ALLOWED_SOURCES may be
        # lateral.
        raise MembershipValidationError("tier_transition_is_noop")
    return transition_direction(from_tier, to_tier)


def assert_fixture_boundary(*, environment: str, source_system: str, external_effect: bool) -> None:
    """Baseline "Production Boundary": DEV/TEST, no external effect, no-op
    adapter. Production activation (Order → PaymentSucceeded → …) is a
    separate approved wave and must not be reachable from this code.
    """
    if environment not in ("DEV", "TEST"):
        raise MembershipForbiddenError(f"environment_not_allowed:{environment}")
    if source_system != "TEST_NOOP_ADAPTER":
        raise MembershipForbiddenError(f"source_system_not_allowed:{source_system}")
    if external_effect:
        raise MembershipForbiddenError("external_effect_not_allowed")


def assert_no_score_semantics(attributes: dict) -> None:
    """`不做 Family Total Score` / `不做家庭 Ranking`, applied to the
    extensibility escape hatch. `attributes` is the one place a caller could
    smuggle `{"family_score": 87}` past the typed fields.
    """
    for key in attributes:
        lowered = str(key).lower()
        for token in FORBIDDEN_TIER_FIELD_TOKENS:
            if token in lowered:
                raise MembershipForbiddenError(f"score_semantics_forbidden:{lowered}")
