"""FamilyExperienceSignal: a cross-family, de-identified "did this help a
family like mine" data point — the "small red book" (小红书) experience
pool this platform substitutes for UGC personal stories.

Distinct from `ImprovementCandidate` (see that module's docstring) by
purpose, not by shape: `ImprovementCandidate` answers "should the product/
content team revise or retire this component?" and is written only on a
negative (`DID_NOT_HELP`) verdict. `FamilyExperienceSignal` answers a
different question a *parent* asks — "other families who had a problem like
mine, what did they try, and how often did it actually help?" — and is
written for every verdict (`HELPED`/`PARTIALLY_HELPED`/`DID_NOT_HELP`),
because a positive result is just as much a real family's experience as a
negative one; only recording the negative half would make this a complaints
ledger, not an experience pool.

The two aggregates are kept separate (not merged into one) because they
serve different consumers with different lifecycles: a product team revises
a course because enough families said `DID_NOT_HELP`; a parent decides
whether to try a course because most families who tried it said `HELPED`.
Merging them would make a future change to one calculation (e.g. how
`ImprovementCandidate` decides "revise this") silently change the other
(e.g. the "helped rate" a parent sees) — the same reasoning that already
keeps `CourseCompletionRecord` separate from family-scoped booking facts.

Hard privacy invariant (identical to `ImprovementCandidate`'s): this
aggregate must never carry `family_id`, `tenant_id` (the family's own
tenant), `child`/subject identity, or the family's free-text note
(`FamilyConfirmedOutcome.family_note`). Every field below has been checked
against that rule; if you are adding a field, check it against the same
rule before you do.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from .errors import ProductIntelligenceValidationError

# Mirrors `family_need.domain.value_objects.SupplyShape` by value — see
# `improvement_candidate.py`'s `ComponentShape` for why this domain never
# imports `family_need`'s domain package directly.
ComponentShape = Literal["PRODUCT", "SERVICE", "SOLUTION"]

# Mirrors `family_need.domain.value_objects.FamilyOutcomeDecision` by value.
# Unlike `ImprovementCandidate.OutcomeDecision`, all three members are
# actually written here — a positive verdict is as much a real experience
# data point as a negative one.
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
class FamilyExperienceSignal:
    """One de-identified "did this help" data point, for any verdict.

    No `family_id`, no `tenant_id` naming the family's own tenant, no
    subject/child identity, no family free-text — see module docstring.
    Thin by design, same shape as `ImprovementCandidate` — a data point for
    aggregation, not a case record.
    """

    signal_id: str
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
        signal_id: str | None = None,
        recorded_at: datetime | None = None,
    ) -> FamilyExperienceSignal:
        if not component_id.strip():
            raise ProductIntelligenceValidationError(
                "family_experience_signal_component_id_required"
            )
        return cls(
            signal_id=signal_id or f"family-experience-signal-{uuid4()}",
            component_id=component_id.strip(),
            component_shape=component_shape,
            decision=decision,
            category=category,
            intervention_tier=intervention_tier,
            recorded_at=recorded_at or _now(),
        )


__all__ = ["FamilyExperienceSignal"]
