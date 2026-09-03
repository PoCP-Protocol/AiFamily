"""Gate1 Human Visual Review schema.

Machine metric fields may exist as null / NOT_MEASURED. Human review is the
final Gate1 authority. IDENTITY_HARD_FAIL forces FAIL regardless of score.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from backend.intelligence.media_factory.contracts import Gate1Verdict, MediaFactoryError

GATE1_WEIGHTS: dict[str, int] = {
    "IDENTITY_PRESERVATION": 30,
    "LIP_SYNC": 20,
    "MOTION_NATURALNESS": 15,
    "TEMPORAL_FACE_STABILITY": 15,
    "EXPRESSION_QUALITY": 10,
    "EYE_BLINK_GAZE": 5,
    "PERFORMANCE": 5,
}

ScoreValue = float | Literal["NOT_MEASURED"] | None


@dataclass(frozen=True, slots=True)
class HumanReviewScores:
    identity_preservation: float
    lip_sync: float
    motion_naturalness: float
    temporal_face_stability: float
    expression_quality: float
    eye_blink_gaze: float
    performance: float
    identity_hard_fail: bool
    identity_hard_fail_reasons: tuple[str, ...] = ()
    # Automatic metrics — must stay null / NOT_MEASURED until a real evaluator exists.
    identity_similarity: ScoreValue = "NOT_MEASURED"
    lip_sync_score: ScoreValue = "NOT_MEASURED"
    temporal_stability: ScoreValue = "NOT_MEASURED"
    reviewer: str = "human"
    notes: str = ""

    def __post_init__(self) -> None:
        for name, value in (
            ("identity_preservation", self.identity_preservation),
            ("lip_sync", self.lip_sync),
            ("motion_naturalness", self.motion_naturalness),
            ("temporal_face_stability", self.temporal_face_stability),
            ("expression_quality", self.expression_quality),
            ("eye_blink_gaze", self.eye_blink_gaze),
            ("performance", self.performance),
        ):
            if not 0.0 <= float(value) <= 5.0:
                raise MediaFactoryError(f"{name} must be in [0, 5], got {value}")


def evaluate_gate1(review: HumanReviewScores) -> Gate1Verdict:
    if review.identity_hard_fail:
        reasons = ", ".join(review.identity_hard_fail_reasons) or "unspecified"
        return Gate1Verdict(
            gate1="FAIL",
            identity_hard_fail=True,
            weighted_score=None,
            reason=f"IDENTITY_HARD_FAIL: {reasons}",
        )

    weighted = (
        review.identity_preservation * GATE1_WEIGHTS["IDENTITY_PRESERVATION"]
        + review.lip_sync * GATE1_WEIGHTS["LIP_SYNC"]
        + review.motion_naturalness * GATE1_WEIGHTS["MOTION_NATURALNESS"]
        + review.temporal_face_stability * GATE1_WEIGHTS["TEMPORAL_FACE_STABILITY"]
        + review.expression_quality * GATE1_WEIGHTS["EXPRESSION_QUALITY"]
        + review.eye_blink_gaze * GATE1_WEIGHTS["EYE_BLINK_GAZE"]
        + review.performance * GATE1_WEIGHTS["PERFORMANCE"]
    ) / 100.0

    # Pass threshold is intentionally high; identity dominates.
    gate = "PASS" if weighted >= 3.5 else "FAIL"
    return Gate1Verdict(
        gate1=gate,
        identity_hard_fail=False,
        weighted_score=round(weighted, 4),
        reason="weighted_human_score",
    )


def empty_human_review_template() -> dict[str, Any]:
    return {
        "schema": "FAMILI_GATE1_HUMAN_REVIEW_V0",
        "status": "PENDING_HUMAN_REVIEW",
        "weights": dict(GATE1_WEIGHTS),
        "scores": {
            "IDENTITY_PRESERVATION": None,
            "LIP_SYNC": None,
            "MOTION_NATURALNESS": None,
            "TEMPORAL_FACE_STABILITY": None,
            "EXPRESSION_QUALITY": None,
            "EYE_BLINK_GAZE": None,
            "PERFORMANCE": None,
        },
        "identity_hard_fail": None,
        "identity_hard_fail_reasons": [],
        "automatic_metrics": {
            "identity_similarity": "NOT_MEASURED",
            "lip_sync_score": "NOT_MEASURED",
            "temporal_stability": "NOT_MEASURED",
        },
        "gate1": None,
        "notes": "Machine must not auto-set gate1=PASS. Human review required.",
    }
