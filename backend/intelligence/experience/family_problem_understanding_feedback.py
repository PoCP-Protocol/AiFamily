"""Append-only parent feedback for generated family understanding drafts."""

from __future__ import annotations

import inspect
from collections import Counter
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

FeedbackSignal = Literal["helpful", "not_helpful", "request_human"]
FeedbackReasonCode = Literal[
    "MISSED_CONTEXT",
    "TOO_GENERIC",
    "FELT_JUDGED",
    "WRONG_ASSUMPTION",
    "OTHER",
]


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

    def replay(self, *, scope: RunScope, run_id: str) -> RunReplaySnapshot | Any: ...


@dataclass(frozen=True, slots=True)
class FamilyUnderstandingFeedback:
    """One adult's feedback for one immutable draft/candidate version."""

    feedback_ref: str
    adult_actor_ref: str
    draft_version: str
    candidate_id: str
    understood_rating: int
    response_relevance: int
    felt_judged: bool
    willing_to_continue: bool
    correction_needed: bool
    correction_ref: str | None = None
    correction_resolved: bool | None = None
    reason_code: FeedbackReasonCode | None = None
    reason_ref: str | None = None
    supersedes_feedback_ref: str | None = None

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.feedback_ref, "feedback_ref"),
            (self.adult_actor_ref, "adult_actor_ref"),
            (self.draft_version, "draft_version"),
            (self.candidate_id, "candidate_id"),
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > 256:
                raise ValueError(f"{field_name} must be a bounded non-empty reference")
        for value, field_name in (
            (self.understood_rating, "understood_rating"),
            (self.response_relevance, "response_relevance"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
                raise ValueError(f"{field_name} must be an integer from 1 to 5")
        for value in (self.felt_judged, self.willing_to_continue, self.correction_needed):
            if not isinstance(value, bool):
                raise ValueError("family understanding feedback flags must be boolean")
        has_correction = bool(self.correction_ref and self.correction_ref.strip())
        if self.correction_needed != has_correction:
            raise ValueError("correction_ref is required exactly when correction is needed")
        if self.correction_ref is not None and not self.correction_ref.startswith("input:"):
            raise ValueError("correction_ref must be an opaque input reference")
        if not self.correction_needed and self.correction_resolved is not None:
            raise ValueError("correction_resolved applies only to requested corrections")
        if self.reason_code == "OTHER" and not self.reason_ref:
            raise ValueError("OTHER feedback requires reason_ref")
        if self.reason_ref is not None and not self.reason_ref.startswith("input:"):
            raise ValueError("reason_ref must be an opaque input reference")
        if self.supersedes_feedback_ref == self.feedback_ref:
            raise ValueError("feedback cannot supersede itself")

    @property
    def response_key(self) -> tuple[str, str, str]:
        return self.adult_actor_ref, self.draft_version, self.candidate_id

    def as_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "feedback_kind": "family_understanding",
            "feedback_version": "family-understanding-feedback.v2",
            "feedback_ref": self.feedback_ref,
            "adult_actor_ref": self.adult_actor_ref,
            "draft_version": self.draft_version,
            "candidate_id": self.candidate_id,
            "understood_rating": self.understood_rating,
            "response_relevance": self.response_relevance,
            "felt_judged": self.felt_judged,
            "willing_to_continue": self.willing_to_continue,
            "correction_needed": self.correction_needed,
        }
        for key, value in (
            ("correction_ref", self.correction_ref),
            ("correction_resolved", self.correction_resolved),
            ("reason_code", self.reason_code),
            ("reason_ref", self.reason_ref),
            ("supersedes_feedback_ref", self.supersedes_feedback_ref),
        ):
            if value is not None:
                payload[key] = value
        return payload


@dataclass(frozen=True, slots=True)
class FamilyUnderstandingFeedbackProjection:
    status: Literal["MEASURED", "NOT_MEASURED", "DELETED"]
    response_count: int
    expected_response_count: int | None
    coverage_rate: float | None
    rating_distribution: tuple[tuple[int, int], ...]
    felt_understood_mean: float | None
    high_understanding_rate: float | None
    low_understanding_rate: float | None
    response_relevance_mean: float | None
    felt_judged_rate: float | None
    willing_to_continue_rate: float | None
    correction_rate: float | None
    correction_resolution_rate: float | None
    latest_correction_ref: str | None


async def record_family_understanding_feedback(
    ledger: FamilyUnderstandingFeedbackLedger,
    *,
    scope: RunScope,
    run_id: str,
    signal: FeedbackSignal,
    feedback: FamilyUnderstandingFeedback,
    idempotency_key: str,
) -> InteractionReceipt:
    replay = ledger.replay(scope=scope, run_id=run_id)
    if inspect.isawaitable(replay):
        replay = await replay
    if not isinstance(replay, RunReplaySnapshot) or replay.deletion_state != "active":
        raise ValueError("feedback run is unavailable")
    latest = _latest_feedback_by_key(replay).get(feedback.response_key)
    if latest is None and feedback.supersedes_feedback_ref is not None:
        raise ValueError("superseded feedback does not exist for this response key")
    if latest is not None and feedback.supersedes_feedback_ref != latest.get("feedback_ref"):
        raise ValueError("updated feedback must supersede the latest response")

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
    *,
    expected_response_count: int | None = None,
) -> FamilyUnderstandingFeedbackProjection:
    if replay.deletion_state == "deleted":
        return _empty_projection("DELETED", expected_response_count)
    latest = tuple(_latest_feedback_by_key(replay).values())
    if not latest:
        return _empty_projection("NOT_MEASURED", expected_response_count)
    count = len(latest)
    ratings = [int(value["understood_rating"]) for value in latest]
    relevance = [int(value["response_relevance"]) for value in latest]
    correction_values = [value for value in latest if bool(value["correction_needed"])]
    correction_refs = [
        str(value["correction_ref"])
        for value in latest
        if isinstance(value.get("correction_ref"), str)
    ]
    distribution = Counter(ratings)
    coverage = None
    if expected_response_count is not None:
        if expected_response_count < count or expected_response_count <= 0:
            raise ValueError("expected_response_count must cover all effective responses")
        coverage = round(count / expected_response_count, 6)
    return FamilyUnderstandingFeedbackProjection(
        status="MEASURED",
        response_count=count,
        expected_response_count=expected_response_count,
        coverage_rate=coverage,
        rating_distribution=tuple((rating, distribution.get(rating, 0)) for rating in range(1, 6)),
        felt_understood_mean=round(sum((rating - 1) / 4 for rating in ratings) / count, 6),
        high_understanding_rate=round(sum(rating >= 4 for rating in ratings) / count, 6),
        low_understanding_rate=round(sum(rating <= 2 for rating in ratings) / count, 6),
        response_relevance_mean=round(sum((rating - 1) / 4 for rating in relevance) / count, 6),
        felt_judged_rate=round(sum(bool(value["felt_judged"]) for value in latest) / count, 6),
        willing_to_continue_rate=round(
            sum(bool(value["willing_to_continue"]) for value in latest) / count, 6
        ),
        correction_rate=round(len(correction_values) / count, 6),
        correction_resolution_rate=(
            round(
                sum(value.get("correction_resolved") is True for value in correction_values)
                / len(correction_values),
                6,
            )
            if correction_values
            else None
        ),
        latest_correction_ref=correction_refs[-1] if correction_refs else None,
    )


def apply_parent_feedback_to_eval_spec(
    spec: FamilyUnderstandingEvalSpec,
    projection: FamilyUnderstandingFeedbackProjection,
) -> FamilyUnderstandingEvalSpec:
    return replace(spec, parent_felt_understood=projection.felt_understood_mean)


def _latest_feedback_by_key(
    replay: RunReplaySnapshot,
) -> dict[tuple[str, str, str], Mapping[str, Any]]:
    latest: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for entry in replay.interactions:
        payload = entry.payload
        if entry.interaction_type is not InteractionType.FEEDBACK:
            continue
        if payload.get("feedback_kind") != "family_understanding":
            continue
        key = (
            str(payload.get("adult_actor_ref", "")),
            str(payload.get("draft_version", "")),
            str(payload.get("candidate_id", "")),
        )
        latest[key] = payload
    return latest


def _empty_projection(
    status: Literal["NOT_MEASURED", "DELETED"], expected: int | None
) -> FamilyUnderstandingFeedbackProjection:
    return FamilyUnderstandingFeedbackProjection(
        status=status,
        response_count=0,
        expected_response_count=expected,
        coverage_rate=0.0 if expected else None,
        rating_distribution=(),
        felt_understood_mean=None,
        high_understanding_rate=None,
        low_understanding_rate=None,
        response_relevance_mean=None,
        felt_judged_rate=None,
        willing_to_continue_rate=None,
        correction_rate=None,
        correction_resolution_rate=None,
        latest_correction_ref=None,
    )


__all__ = [
    "FamilyUnderstandingFeedback",
    "FamilyUnderstandingFeedbackProjection",
    "FeedbackReasonCode",
    "FeedbackSignal",
    "apply_parent_feedback_to_eval_spec",
    "project_family_understanding_feedback",
    "record_family_understanding_feedback",
]
