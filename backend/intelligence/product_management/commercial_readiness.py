"""Evidence-based commercial readiness checks for service products.

This module does not create orders, grant entitlements, or call a payment
provider.  It makes the release gate explicit so a course draft cannot be
described as commercially available merely because its content exists.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CommercialReadiness:
    """Immutable result of the commercial release gate."""

    ready: bool
    checks: Mapping[str, bool]
    blockers: tuple[str, ...]


def evaluate_commercial_readiness(
    *,
    lesson_count: int,
    courseware_approved: bool,
    product_package_released: bool,
    evidence_verified: bool,
    payment_sandbox_verified: bool,
    entitlement_grant_verified: bool,
    delivery_readback_verified: bool,
    refund_recovery_verified: bool,
    human_gate_accepted: bool,
) -> CommercialReadiness:
    """Evaluate the minimum evidence needed for a paid pilot release.

    The evaluator is deliberately strict and pure.  Every check must be
    supplied by an external test/evidence runner; a missing or false value is
    a blocker.  ``lesson_count`` is kept separate so a 4-lesson pilot cannot
    be confused with the full 24-lesson catalogue.
    """

    checks = {
        "lesson_scope_valid": lesson_count in {4, 24},
        "courseware_approved": courseware_approved,
        "product_package_released": product_package_released,
        "evidence_verified": evidence_verified,
        "payment_sandbox_verified": payment_sandbox_verified,
        "entitlement_grant_verified": entitlement_grant_verified,
        "delivery_readback_verified": delivery_readback_verified,
        "refund_recovery_verified": refund_recovery_verified,
        "human_gate_accepted": human_gate_accepted,
    }
    blockers = tuple(name for name, passed in checks.items() if not passed)
    return CommercialReadiness(ready=not blockers, checks=checks, blockers=blockers)


__all__ = ["CommercialReadiness", "evaluate_commercial_readiness"]
