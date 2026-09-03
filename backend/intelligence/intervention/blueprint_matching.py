"""Provider-neutral matching from intervention drafts to service blueprints.

Blueprints are business-owned, immutable release snapshots.  This module
accepts only their read projection and emits a recommendation draft; it never
creates, edits, publishes, or executes a service blueprint.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from backend.intelligence.experience.contracts import ExperienceScope

BlueprintRecommendationStatus = Literal["DRAFT"]


class BlueprintMatchingError(ValueError):
    """Raised when a blueprint read projection is not safe to match."""


@dataclass(frozen=True, slots=True)
class BlueprintRecommendation:
    blueprint_ref: str
    primary_contradiction_ref: str
    action_refs: tuple[str, ...]
    fit_confidence: float
    evidence_refs: tuple[str, ...]
    status: BlueprintRecommendationStatus = "DRAFT"
    human_gate_required: bool = False

    def __post_init__(self) -> None:
        if not self.blueprint_ref or not self.primary_contradiction_ref:
            raise BlueprintMatchingError("BLUEPRINT_RECOMMENDATION_ID_REQUIRED")
        if not self.action_refs or any(not ref for ref in self.action_refs):
            raise BlueprintMatchingError("BLUEPRINT_ACTION_REFS_REQUIRED")
        if not self.evidence_refs:
            raise BlueprintMatchingError("BLUEPRINT_EVIDENCE_REQUIRED")
        if not 0.0 <= self.fit_confidence <= 1.0:
            raise BlueprintMatchingError("BLUEPRINT_FIT_CONFIDENCE_INVALID")
        if self.status != "DRAFT":
            raise BlueprintMatchingError("BLUEPRINT_RECOMMENDATION_DRAFT_ONLY")


class ServiceBlueprintMatcher:
    """Match only published blueprint snapshots to an intervention draft."""

    def match(
        self,
        *,
        scope: ExperienceScope,
        primary_contradiction_refs: Sequence[str],
        evidence_refs: Sequence[str],
        blueprints: Sequence[Mapping[str, Any]],
        high_impact: bool = False,
    ) -> tuple[BlueprintRecommendation, ...]:
        if not isinstance(scope, ExperienceScope):
            raise BlueprintMatchingError("EXPERIENCE_SCOPE_REQUIRED")
        if not scope.consent_granted:
            raise BlueprintMatchingError("BLUEPRINT_CONSENT_REQUIRED")
        contradictions = tuple(dict.fromkeys(ref for ref in primary_contradiction_refs if ref))
        evidence = tuple(dict.fromkeys(ref for ref in evidence_refs if ref))
        if not contradictions:
            raise BlueprintMatchingError("PRIMARY_CONTRADICTION_REQUIRED")
        if not evidence:
            raise BlueprintMatchingError("BLUEPRINT_EVIDENCE_REQUIRED")

        recommendations: list[BlueprintRecommendation] = []
        for blueprint in blueprints:
            if blueprint.get("status") != "PUBLISHED":
                continue
            blueprint_ref = blueprint.get("blueprint_ref")
            contradiction = blueprint.get("primary_contradiction_ref")
            actions = blueprint.get("action_refs")
            if not isinstance(blueprint_ref, str) or not blueprint_ref.strip():
                raise BlueprintMatchingError("BLUEPRINT_REF_REQUIRED")
            if not isinstance(contradiction, str) or not contradiction.strip():
                raise BlueprintMatchingError("BLUEPRINT_CONTRADICTION_REQUIRED")
            if contradiction not in contradictions:
                continue
            if not isinstance(actions, (list, tuple)) or not actions:
                raise BlueprintMatchingError("BLUEPRINT_ACTION_REFS_REQUIRED")
            action_refs = tuple(
                ref.strip() for ref in actions if isinstance(ref, str) and ref.strip()
            )
            if not action_refs:
                raise BlueprintMatchingError("BLUEPRINT_ACTION_REFS_REQUIRED")
            recommendations.append(
                BlueprintRecommendation(
                    blueprint_ref=blueprint_ref.strip(),
                    primary_contradiction_ref=contradiction,
                    action_refs=action_refs,
                    fit_confidence=1.0,
                    evidence_refs=evidence,
                    human_gate_required=(
                        high_impact or str(scope.data_class) == "MINOR_PERSONAL_DATA"
                    ),
                )
            )
        recommendations.sort(key=lambda item: item.blueprint_ref)
        return tuple(recommendations)


__all__ = [
    "BlueprintMatchingError",
    "BlueprintRecommendation",
    "ServiceBlueprintMatcher",
]
