"""ImprovementCandidate: a cross-family, de-identified "this component did
not help" signal for product/content teams.

This is deliberately not part of `family_need` (see
`backend/domains/family_need/api/routes.py::confirm_family_outcome`'s N8
block): a `FamilyConfirmedOutcome` with `decision=DID_NOT_HELP` is a real
family's private fact, scoped to that family/tenant, and its own N8 re-triage
already reopens a *new* `FamilyNeed` for that same family — that half of the
loop was already closed. What was missing is a second, entirely separate
question: "how many different families did this course/service fail to
help?" — a fact about the *component* (course/service/solution), not about
any one family, that a product/content team would use to decide whether to
revise or retire it.

`ImprovementCandidate` is that fact, and it is placed in
`product_intelligence` rather than `family_need` because it answers a
product-improvement question, not a family-need question — the same split
`product_intelligence` already draws for `CourseCompletionRecord` vs. the
family-scoped booking/course-completion facts in `family_need`/`service`.

Hard privacy invariant (read before touching this file): this aggregate must
never carry `family_id`, `tenant_id` (the *family's* tenant — see below),
`child`/subject identity, or the family's own free-text note
(`FamilyConfirmedOutcome.family_note`). It exists specifically so a product
team can see "component X did not help N families" without being able to
identify which families. Every field below has been checked against that
rule; if you are adding a field, check it against the same rule before you
do.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from .errors import ProductIntelligenceValidationError

# Mirrors `family_need.domain.value_objects.SupplyShape` by value (not by
# import — this domain must not depend on `family_need`'s domain package for
# the same reason `family_need` never imports `commerce`/`service`: each
# bounded context owns its own vocabulary, even when two enums happen to
# share the same member names).
ComponentShape = Literal["PRODUCT", "SERVICE", "SOLUTION"]

# Mirrors `family_need.domain.value_objects.FamilyOutcomeDecision` by value.
# Only `DID_NOT_HELP` is written today (see module docstring / the API route
# this is wired from), but the type stays open to a future positive signal
# without a migration.
OutcomeDecision = Literal["HELPED", "PARTIALLY_HELPED", "DID_NOT_HELP"]

# Mirrors `family_need.domain.value_objects.NeedCategory` by value.
NeedCategoryLabel = Literal[
    "EDUCATION",
    "FAMILY_RELATIONSHIP",
    "GROWTH_COMPANIONSHIP",
    "LIFE_SUPPORT",
    "SERVICE_SUPPORT",
    "OTHER",
]

# Mirrors `family_need.domain.value_objects.InterventionTier` by value.
InterventionTierLabel = Literal[
    "UNIVERSAL",
    "LIGHT_GUIDANCE",
    "BRIEF_CONSULTATION",
    "INTENSIVE_SUPPORT",
    "ENHANCED_SUPPORT",
]


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ImprovementCandidate:
    """One de-identified "this component did not help" data point.

    No `family_id`, no `tenant_id` naming the family's own tenant, no
    subject/child identity, no family free-text — see module docstring. This
    is deliberately as thin as `CourseCompletionRecord` — a data point for
    aggregation, not a case record.
    """

    candidate_id: str
    component_id: str
    component_shape: ComponentShape
    decision: OutcomeDecision
    category: NeedCategoryLabel
    intervention_tier: InterventionTierLabel
    recorded_at: datetime

    @classmethod
    def record(
        cls,
        *,
        component_id: str,
        component_shape: ComponentShape,
        decision: OutcomeDecision,
        category: NeedCategoryLabel,
        intervention_tier: InterventionTierLabel,
        candidate_id: str | None = None,
        recorded_at: datetime | None = None,
    ) -> ImprovementCandidate:
        if not component_id.strip():
            raise ProductIntelligenceValidationError("improvement_candidate_component_id_required")
        return cls(
            candidate_id=candidate_id or f"improvement-candidate-{uuid4()}",
            component_id=component_id.strip(),
            component_shape=component_shape,
            decision=decision,
            category=category,
            intervention_tier=intervention_tier,
            recorded_at=recorded_at or _now(),
        )


__all__ = ["ImprovementCandidate"]
