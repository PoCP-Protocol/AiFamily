"""Assessment domain policies.

`assess_structured_safety_signals` is a byte-for-byte semantic port of
`apps/api/src/modules/family/safety-assessment.policy.ts`
(`assessStructuredSafetySignals`) — same three severity tiers, same escalation
signal set, same policy_version literal. Per
`architecture/FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md` section 10, this
guarantee must be preserved, not weakened, in translation.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

StructuredSafetySignal = Literal[
    "NONE", "SELF_HARM", "HARM_TO_OTHERS", "ABUSE", "VIOLENCE", "SEVERE_CRISIS"
]

POLICY_VERSION: Literal["M2_102_DETERMINISTIC_V1"] = "M2_102_DETERMINISTIC_V1"

_ESCALATION_SIGNALS: set[StructuredSafetySignal] = {
    "SELF_HARM",
    "HARM_TO_OTHERS",
    "ABUSE",
    "VIOLENCE",
    "SEVERE_CRISIS",
}

_CRITICAL_SIGNALS: set[StructuredSafetySignal] = {"SEVERE_CRISIS", "SELF_HARM", "HARM_TO_OTHERS"}


class SafetyDisposition(BaseModel):
    severity: Literal["LOW", "HIGH", "CRITICAL"]
    disposition: Literal["NORMAL", "SAFETY_ESCALATION"]
    policy_version: Literal["M2_102_DETERMINISTIC_V1"]
    signals: list[StructuredSafetySignal]


def _normalize_safety_signals(signals: list[StructuredSafetySignal]) -> list[StructuredSafetySignal]:
    without_none = [signal for signal in signals if signal != "NONE"]
    unique = sorted(set(without_none)) if without_none else ["NONE"]
    return unique  # type: ignore[return-value]


def assess_structured_safety_signals(signals: list[StructuredSafetySignal]) -> SafetyDisposition:
    normalized = _normalize_safety_signals(signals)

    if any(signal in _CRITICAL_SIGNALS for signal in normalized):
        return SafetyDisposition(
            severity="CRITICAL", disposition="SAFETY_ESCALATION", policy_version=POLICY_VERSION, signals=normalized
        )

    if any(signal in _ESCALATION_SIGNALS for signal in normalized):
        return SafetyDisposition(
            severity="HIGH", disposition="SAFETY_ESCALATION", policy_version=POLICY_VERSION, signals=normalized
        )

    return SafetyDisposition(
        severity="LOW", disposition="NORMAL", policy_version=POLICY_VERSION, signals=normalized
    )


def assert_response_value(
    response_type: Literal["SINGLE_CHOICE", "TEXT", "BOOLEAN"],
    options: list[str] | None,
    value: str | bool,
) -> None:
    """Port of `AssessmentService.assertResponseValue` (assessment.service.ts)."""
    from .errors import AssessmentValidationError

    if response_type == "BOOLEAN" and not isinstance(value, bool):
        raise AssessmentValidationError("assessment_boolean_response_required")
    if response_type in ("SINGLE_CHOICE", "TEXT") and not isinstance(value, str):
        raise AssessmentValidationError("assessment_text_response_required")
    if response_type == "TEXT" and isinstance(value, str) and (len(value.strip()) == 0 or len(value) > 500):
        raise AssessmentValidationError("assessment_text_response_invalid")
    if response_type == "SINGLE_CHOICE" and (not options or str(value) not in options):
        raise AssessmentValidationError("assessment_choice_not_in_tool_version")
