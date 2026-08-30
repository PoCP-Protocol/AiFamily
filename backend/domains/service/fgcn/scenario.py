"""The frozen S-01 business scenario for the first FGCN service slice.

FGCN is not an open resource marketplace.  This slice exists only for a
family that has repeatedly tried self-help, explicitly asks for support, and
needs one qualified human delivery to create a calm start without escalating
conflict.  The scenario deliberately excludes child performance, family
scores, and rankings from both delivery and quality decisions.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from backend.domains.service.domain.errors import ServiceValidationError

S01_SCENARIO_KEY = "S-01"
S01_OUTCOME_KEY = "CALM_START_CONFLICT_REDUCTION"
S01_FAMILY_PROBLEM = (
    "The family has repeatedly tried self-help, but cannot start a calm shared "
    "action without conflict escalating."
)
S01_PROVIDER_DELIVERABLE = (
    "A qualified human provider delivers one adult-led calm-start intervention "
    "from the frozen blueprint and submits auditable delivery evidence."
)
S01_SERVICE_OUTCOME = (
    "The family completes one calm start and conflict does not escalate; child "
    "performance, family scores, and rankings are out of scope."
)
S01_TASK_ACCEPTANCE_CRITERION = (
    "The adult-led calm start was completed and conflict did not escalate; child "
    "performance, family scores, and rankings are not an acceptance measure."
)
S01_QUALITY_VERIFICATION_MARKER = (
    "S-01 outcome verified: calm start completed and conflict did not escalate."
)
S01_OUTCOME_OBSERVATION = "S-01 calm start completed; conflict did not escalate."


@dataclass(frozen=True, slots=True)
class ServiceScenario:
    """Immutable scenario content frozen into a published BlueprintSnapshot."""

    scenario_key: str
    family_problem: str
    provider_deliverable: str
    service_outcome: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.scenario_key, "scenario_key"),
            (self.family_problem, "family_problem"),
            (self.provider_deliverable, "provider_deliverable"),
            (self.service_outcome, "service_outcome"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ServiceValidationError(f"fgcn_s01_{field_name}_required")


S01_SCENARIO = ServiceScenario(
    scenario_key=S01_SCENARIO_KEY,
    family_problem=S01_FAMILY_PROBLEM,
    provider_deliverable=S01_PROVIDER_DELIVERABLE,
    service_outcome=S01_SERVICE_OUTCOME,
)


def validate_s01_scenario(scenario: ServiceScenario) -> ServiceScenario:
    """Allow only the frozen S-01 scenario into a service blueprint."""

    if not isinstance(scenario, ServiceScenario):
        raise ServiceValidationError("fgcn_s01_scenario_required")
    if scenario != S01_SCENARIO:
        raise ServiceValidationError("fgcn_only_s01_scenario_is_supported")
    return scenario


def validate_s01_task_acceptance(criteria: Iterable[str]) -> tuple[str, ...]:
    """Require the task to evaluate the S-01 service outcome, not a score."""

    normalized = tuple(criteria)
    if S01_TASK_ACCEPTANCE_CRITERION not in normalized:
        raise ServiceValidationError("fgcn_s01_task_outcome_criterion_required")
    return normalized


def validate_s01_outcome_observation(observation: str) -> str:
    """Require provider delivery to name the observable S-01 outcome."""

    if not isinstance(observation, str) or not observation.strip():
        raise ServiceValidationError("fgcn_s01_delivery_outcome_required")
    normalized = observation.strip()
    folded = normalized.casefold()
    if "calm start" not in folded or "conflict" not in folded:
        raise ServiceValidationError("fgcn_s01_delivery_outcome_required")
    forbidden = ("score", "ranking", "rank", "grade", "成绩", "排名", "总分")
    if any(token in folded for token in forbidden):
        raise ServiceValidationError("fgcn_s01_scoring_semantics_forbidden")
    return normalized


def validate_s01_quality_note(note: str) -> str:
    """Require a human reviewer to explicitly attest the S-01 outcome."""

    if not isinstance(note, str) or S01_QUALITY_VERIFICATION_MARKER not in note.strip():
        raise ServiceValidationError("fgcn_s01_quality_outcome_attestation_required")
    return note.strip()


__all__ = [
    "S01_FAMILY_PROBLEM",
    "S01_OUTCOME_KEY",
    "S01_OUTCOME_OBSERVATION",
    "S01_PROVIDER_DELIVERABLE",
    "S01_QUALITY_VERIFICATION_MARKER",
    "S01_SCENARIO",
    "S01_SCENARIO_KEY",
    "S01_SERVICE_OUTCOME",
    "S01_TASK_ACCEPTANCE_CRITERION",
    "ServiceScenario",
    "validate_s01_outcome_observation",
    "validate_s01_quality_note",
    "validate_s01_scenario",
    "validate_s01_task_acceptance",
]
