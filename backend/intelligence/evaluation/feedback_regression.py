"""Provider-neutral regression evaluation derived from guardian feedback.

This module is deliberately an evaluation boundary.  It accepts only bounded,
de-identified feedback references and versioned expected structures; it never
reads family records, calls a provider, promotes a model, or writes business
facts.  A report can be handed to the existing release gate by an operator.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from backend.intelligence.model_gateway.validation import SchemaValidator

FeedbackKind = Literal["GUARDIAN_ACCEPT", "GUARDIAN_EDIT", "GUARDIAN_REJECT"]


class FeedbackRegressionError(ValueError):
    """Raised when a feedback case is not safe to enter the eval boundary."""


@dataclass(frozen=True, slots=True)
class FeedbackRegressionCase:
    """A media-free, de-identified regression case from one feedback event."""

    case_ref: str
    case_version: str
    feedback_ref: str
    feedback_kind: FeedbackKind
    input_contract: Mapping[str, Any]
    expected_output: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    scope_digest: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (
                self.case_ref,
                self.case_version,
                self.feedback_ref,
                self.scope_digest,
            )
        ):
            raise FeedbackRegressionError("feedback case identity is required")
        if self.feedback_kind not in {"GUARDIAN_ACCEPT", "GUARDIAN_EDIT", "GUARDIAN_REJECT"}:
            raise FeedbackRegressionError("unsupported feedback kind")
        if not self.input_contract or not self.expected_output or not self.output_schema:
            raise FeedbackRegressionError("feedback case contracts are required")
        _assert_bounded_json(self.input_contract)
        _assert_bounded_json(self.expected_output)
        _assert_bounded_json(self.output_schema)


@dataclass(frozen=True, slots=True)
class FeedbackRegressionResult:
    case_ref: str
    feedback_ref: str
    passed: bool
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class FeedbackRegressionReport:
    case_version: str
    total_cases: int
    passed_cases: int
    results: tuple[FeedbackRegressionResult, ...] = field(default_factory=tuple)

    @property
    def report_ref(self) -> str:
        payload = {
            "case_version": self.case_version,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "results": [
                {
                    "case_ref": item.case_ref,
                    "feedback_ref": item.feedback_ref,
                    "passed": item.passed,
                    "failure_reason": item.failure_reason,
                }
                for item in self.results
            ],
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24]
        return f"benchmark:feedback-regression:{self.case_version}:{digest}"

    @property
    def release_eligibility(self) -> Literal["ELIGIBLE", "BLOCKED"]:
        eligible = self.total_cases > 0 and self.passed_cases == self.total_cases
        return "ELIGIBLE" if eligible else "BLOCKED"


FeedbackRegressionAdapter = Callable[[FeedbackRegressionCase], Mapping[str, Any]]


def evaluate_feedback_regression(
    cases: Sequence[FeedbackRegressionCase],
    adapter: FeedbackRegressionAdapter,
    *,
    case_version: str,
) -> FeedbackRegressionReport:
    """Evaluate a feedback-derived suite without contacting a model provider."""

    if not case_version.strip():
        raise FeedbackRegressionError("case_version is required")
    if not callable(adapter):
        raise TypeError("adapter must be callable")
    if not cases:
        raise FeedbackRegressionError("at least one feedback case is required")
    results: list[FeedbackRegressionResult] = []
    for case in cases:
        try:
            output = adapter(case)
            if not isinstance(output, Mapping):
                raise FeedbackRegressionError("adapter output must be an object")
            _assert_bounded_json(output)
            SchemaValidator().validate(
                output,
                dict(case.output_schema),
                provider_id="feedback-eval",
            )
            if dict(output) != dict(case.expected_output):
                raise FeedbackRegressionError("expected output mismatch")
        except Exception as error:
            results.append(
                FeedbackRegressionResult(
                    case_ref=case.case_ref,
                    feedback_ref=case.feedback_ref,
                    passed=False,
                    failure_reason=type(error).__name__ + ": " + str(error),
                )
            )
        else:
            results.append(
                FeedbackRegressionResult(
                    case_ref=case.case_ref,
                    feedback_ref=case.feedback_ref,
                    passed=True,
                )
            )
    return FeedbackRegressionReport(
        case_version=case_version,
        total_cases=len(results),
        passed_cases=sum(item.passed for item in results),
        results=tuple(results),
    )


_FORBIDDEN_KEYS = frozenset(
    {
        "raw_media",
        "media_bytes",
        "need_statement",
        "evidence_excerpt",
        "child_name",
        "guardian_name",
        "family_id",
        "tenant_id",
    }
)


def _assert_bounded_json(value: Any, *, depth: int = 0) -> None:
    if depth > 6:
        raise FeedbackRegressionError("feedback payload nesting is too deep")
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str) or key in _FORBIDDEN_KEYS:
                raise FeedbackRegressionError("feedback payload contains forbidden field")
            _assert_bounded_json(child, depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        if len(value) > 64:
            raise FeedbackRegressionError("feedback payload list is too large")
        for child in value:
            _assert_bounded_json(child, depth=depth + 1)
        return
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, str) and len(value) > 2000:
            raise FeedbackRegressionError("feedback payload text is too large")
        return
    raise FeedbackRegressionError("feedback payload must be bounded JSON")


__all__ = [
    "FeedbackKind",
    "FeedbackRegressionAdapter",
    "FeedbackRegressionCase",
    "FeedbackRegressionError",
    "FeedbackRegressionReport",
    "FeedbackRegressionResult",
    "evaluate_feedback_regression",
]
