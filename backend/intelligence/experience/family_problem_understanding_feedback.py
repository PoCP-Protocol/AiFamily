"""Parent feedback loop for generated family-problem understanding drafts."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Literal, Protocol

from backend.intelligence.experience.family_problem_understanding_eval import (
    FamilyUnderstandingEvalSpec,
)
from backend.intelligence.experience.run_http import (
    InteractionReceipt,
    InteractionType,
    RunReplaySnapshot,
    RunScope,
)

FamilyUnderstandingFeedbackSignal = Literal["helpful", "not_helpful", "request_human"]


class FamilyUnderstandingFeedbackLedger(Protocol):
    def append_interaction(
        self,
        *,
        scope: RunScope,
        run_id: str,
        interaction_type: InteractionType,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> InteractionReceipt | Any: ...


@dataclass(frozen=True, slots=True)
class FamilyUnderstandingFeedback:
    """Structured adult feedback; correction content remains an external ref."""

    understood_rating: int
    felt_judged: bool
    willing_to_continue: bool
    correction_needed: bool
    correction_ref: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.understood_rating, bool) or not 1 <= self.understood_rating <= 5:
            raise ValueError("understood_rating must be an integer from 1 to 5")
        for value in (self.felt_judged, self.willing_to_continue, self.correction_needed):
            if not isinstance(value, bool):
                raise ValueError("family understanding feedback flags must be boolean")
        if self.correction_needed != bool(self.correction_ref and self.correction_ref.strip()):
            raise ValueError("correction_ref is required exactly when correction is needed")
        if self.reason is not None and not self.reason.strip():
            raise ValueError("feedback reason must be non-empty when provided")

    def as_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "feedback_kind": "family_understanding",
            "feedback_version": "family-understanding-feedback.v1",
            "understood_rating": self.understood_rating,
            "felt_judged": self.felt_judged,
            "willing_to_continue": self.willing_to_continue,
            "correction_needed": self.correction_needed,
        }
        if self.correction_ref is not None:
            payload["correction_ref"] = self.correction_ref
        if self.reason is not None:
            payload["reason"] = self.reason
        return payload


@dataclass(frozen=True, slots=True)
class FamilyUnderstandingFeedbackProjection:
    status: Literal["MEASURED", "NOT_MEASURED"]
    response_count: int
    felt_understood_mean: float | None
    felt_judged_rate: float | None
    willing_to_continue_rate: float | None
    correction_rate: float | None
    latest_correction_ref: str | None

    def __post_init__(self) -> None:
        if self.status == "NOT_MEASURED" and self.response_count != 0:
            raise ValueError("unmeasured feedback cannot contain responses")
        if self.status == "MEASURED" and self.response_count <= 0:
            raise ValueError("measured feedback requires responses")
        for value in (
            self.felt_understood_mean,
            self.felt_judged_rate,
            self.willing_to_continue_rate,
            self.correction_rate,
        ):
            if value is not None and not 0.0 <= value <= 1.0:
                raise ValueError("feedback projection rates must be between 0 and 1")


async def record_family_understanding_feedback(
    ledger: FamilyUnderstandingFeedbackLedger,
    *,
    scope: RunScope,
    run_id: str,
    signal: FamilyUnderstandingFeedbackSignal,
    feedback: FamilyUnderstandingFeedback,
    idempotency_key: str,
) -> InteractionReceipt:
    payload = feedback.as_payload()
    payload["signal"] = signal
    result = ledger.append_interaction(
        scope=scope,
        run_id=run_id,
        interaction_type=InteractionType.FEEDBACK,
        idempotency_key=idempotency_key,
        payload=payload,
    )
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, InteractionReceipt):
        raise ValueError("feedback ledger returned an invalid receipt")
    return result


def project_family_understanding_feedback(
    replay: RunReplaySnapshot,
) -> FamilyUnderstandingFeedbackProjection:
    values = [
        entry.payload
        for entry in replay.interactions
        if entry.interaction_type is InteractionType.FEEDBACK
        and entry.payload.get("feedback_kind") == "family_understanding"
    ]
    if not values:
        return FamilyUnderstandingFeedbackProjection(
            "NOT_MEASURED", 0, None, None, None, None, None
        )
    count = len(values)
    ratings = [int(value["understood_rating"]) for value in values]
    correction_refs = [
        str(value["correction_ref"])
        for value in values
        if isinstance(value.get("correction_ref"), str)
    ]
    return FamilyUnderstandingFeedbackProjection(
        status="MEASURED",
        response_count=count,
        felt_understood_mean=round(sum((rating - 1) / 4 for rating in ratings) / count, 6),
        felt_judged_rate=round(sum(bool(value["felt_judged"]) for value in values) / count, 6),
        willing_to_continue_rate=round(
            sum(bool(value["willing_to_continue"]) for value in values) / count, 6
        ),
        correction_rate=round(sum(bool(value["correction_needed"]) for value in values) / count, 6),
        latest_correction_ref=correction_refs[-1] if correction_refs else None,
    )


def apply_parent_feedback_to_eval_spec(
    spec: FamilyUnderstandingEvalSpec,
    projection: FamilyUnderstandingFeedbackProjection,
) -> FamilyUnderstandingEvalSpec:
    return replace(spec, parent_felt_understood=projection.felt_understood_mean)


__all__ = [
    "FamilyUnderstandingFeedback",
    "FamilyUnderstandingFeedbackProjection",
    "FamilyUnderstandingFeedbackSignal",
    "apply_parent_feedback_to_eval_spec",
    "project_family_understanding_feedback",
    "record_family_understanding_feedback",
]
