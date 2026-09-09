from __future__ import annotations

import pytest

from backend.intelligence.evaluation.feedback_regression import (
    FeedbackRegressionCase,
    FeedbackRegressionError,
    evaluate_feedback_regression,
)


def _case(**overrides):
    values = {
        "case_ref": "case-1",
        "case_version": "feedback-v1",
        "feedback_ref": "feedback-1",
        "feedback_kind": "GUARDIAN_EDIT",
        "input_contract": {"capability_refs": ["practice:morning"]},
        "expected_output": {"next_step": "记录一次晨间观察"},
        "output_schema": {
            "type": "object",
            "required": ["next_step"],
            "properties": {"next_step": {"type": "string"}},
        },
        "scope_digest": "sha256:opaque-family-scope",
    }
    values.update(overrides)
    return FeedbackRegressionCase(**values)


def test_feedback_regression_is_bounded_and_produces_release_signal() -> None:
    report = evaluate_feedback_regression(
        [_case()],
        lambda case: {"next_step": "记录一次晨间观察"},
        case_version="feedback-v1",
    )

    assert report.total_cases == 1
    assert report.passed_cases == 1
    assert report.release_eligibility == "ELIGIBLE"
    assert report.report_ref.startswith("benchmark:feedback-regression:feedback-v1:")


def test_mismatch_blocks_release_without_exposing_payload() -> None:
    report = evaluate_feedback_regression(
        [_case()],
        lambda case: {"next_step": "不同的草案"},
        case_version="feedback-v1",
    )

    assert report.release_eligibility == "BLOCKED"
    assert report.results[0].passed is False
    assert "不同的草案" not in report.report_ref


def test_forbidden_family_or_minor_fields_fail_closed() -> None:
    with pytest.raises(FeedbackRegressionError, match="forbidden field"):
        _case(input_contract={"family_id": "family-1"})


def test_adapter_failure_is_reported_as_failed_case() -> None:
    report = evaluate_feedback_regression(
        [_case()],
        lambda case: (_ for _ in ()).throw(RuntimeError("adapter unavailable")),
        case_version="feedback-v1",
    )

    assert report.passed_cases == 0
    assert report.results[0].failure_reason.startswith("RuntimeError:")
