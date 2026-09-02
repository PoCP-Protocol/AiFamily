from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from poc.standalone_live_observability_sandbox.slo import (
    MetricSample,
    SloTargets,
    evaluate_slo,
)

TENANT = "tenant.synthetic.alpha"
FAMILY = "family.synthetic.alpha"
SESSION = "live.synthetic.mili-001"
NOW = datetime(2026, 9, 3, 10, 0, tzinfo=UTC)


def sample(
    component: str,
    metric: str,
    value: float,
    *,
    seconds_ago: int = 5,
    **changes: object,
) -> MetricSample:
    base = MetricSample(
        component=component,  # type: ignore[arg-type]
        metric=metric,
        value=value,
        observed_at=NOW - timedelta(seconds=seconds_ago),
        tenant_id=TENANT,
        family_id=FAMILY,
        session_ref=SESSION,
    )
    return replace(base, **changes)


def healthy_samples() -> list[MetricSample]:
    return [
        sample("media", "startup_success", 1),
        sample("media", "first_frame_ms", 420),
        sample("media", "stall_ratio", 0.004),
        sample("media", "recovery_ms", 850),
        sample("interaction", "interaction_latency_ms", 75),
        sample("control", "request_success", 1),
        sample("replay", "request_success", 1),
    ]


def evaluate(samples: list[MetricSample], **changes: object):
    inputs = {
        "tenant_id": TENANT,
        "family_id": FAMILY,
        "session_ref": SESSION,
        "now": NOW,
    }
    inputs.update(changes)
    return evaluate_slo(samples, **inputs)  # type: ignore[arg-type]


def test_healthy_window_is_green_and_never_issues_automatic_stop() -> None:
    report = evaluate(healthy_samples())

    assert report.recommendation == "GREEN"
    assert report.window_start == NOW - timedelta(minutes=5)
    assert report.window_end == NOW
    assert report.sample_count == 7
    assert report.startup_success == 1
    assert report.first_frame_ms == 420
    assert report.stall_ratio == pytest.approx(0.004)
    assert report.interaction_latency_ms == 75
    assert report.recovery_ms == 850
    assert report.error_budget == 1
    assert report.human_review_required is False
    assert report.automatic_stop_issued is False


def test_window_uses_mean_and_nearest_rank_p95() -> None:
    samples = healthy_samples()
    samples.extend(
        [
            sample("media", "startup_success", 1, seconds_ago=10),
            sample("media", "first_frame_ms", 1_200, seconds_ago=10),
            sample("media", "stall_ratio", 0.012, seconds_ago=10),
            sample("media", "recovery_ms", 2_400, seconds_ago=10),
            sample("interaction", "interaction_latency_ms", 240, seconds_ago=10),
            sample("control", "request_success", 1, seconds_ago=10),
            sample("replay", "request_success", 1, seconds_ago=10),
        ]
    )

    report = evaluate(samples)

    assert report.startup_success == 1
    assert report.first_frame_ms == 1_200
    assert report.stall_ratio == pytest.approx(0.008)
    assert report.interaction_latency_ms == 240
    assert report.recovery_ms == 2_400
    assert report.recommendation == "GREEN"


def test_old_samples_outside_window_do_not_pollute_calculation() -> None:
    samples = healthy_samples()
    samples.append(sample("media", "first_frame_ms", 99_999, seconds_ago=301))

    report = evaluate(samples)

    assert report.sample_count == 7
    assert report.first_frame_ms == 420
    assert report.recommendation == "GREEN"


@pytest.mark.parametrize(
    ("remove_component", "remove_metric"),
    [
        ("media", "startup_success"),
        ("media", "first_frame_ms"),
        ("media", "stall_ratio"),
        ("media", "recovery_ms"),
        ("interaction", "interaction_latency_ms"),
        ("control", "request_success"),
        ("replay", "request_success"),
    ],
)
def test_missing_required_metric_fails_closed(remove_component: str, remove_metric: str) -> None:
    samples = [
        item
        for item in healthy_samples()
        if (item.component, item.metric) != (remove_component, remove_metric)
    ]

    report = evaluate(samples)

    assert report.recommendation == "STOP"
    assert report.error_budget == 0
    assert report.human_review_required is True
    assert report.automatic_stop_issued is False
    assert any("missing metrics" in reason for reason in report.reasons)


def test_stale_metrics_fail_closed() -> None:
    samples = [replace(item, observed_at=NOW - timedelta(seconds=46)) for item in healthy_samples()]

    report = evaluate(samples)

    assert report.recommendation == "STOP"
    assert report.human_review_required is True
    assert any("stale metrics" in reason for reason in report.reasons)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tenant_id", "tenant.synthetic.other"),
        ("family_id", "family.synthetic.other"),
        ("session_ref", "live.synthetic.other"),
    ],
)
def test_cross_scope_metric_fails_closed(field: str, value: str) -> None:
    samples = healthy_samples()
    samples[0] = replace(samples[0], **{field: value})

    report = evaluate(samples)

    assert report.recommendation == "STOP"
    assert "cross-scope metric evidence" in report.reasons


@pytest.mark.parametrize(
    "unsafe_sample",
    [
        sample("media", "startup_success", 1, source="PRODUCTION"),
        sample("media", "startup_success", 1, fixture_only=False),
    ],
)
def test_non_synthetic_evidence_fails_closed(unsafe_sample: MetricSample) -> None:
    samples = healthy_samples()
    samples[0] = unsafe_sample

    report = evaluate(samples)

    assert report.recommendation == "STOP"
    assert "non-synthetic metric evidence" in report.reasons


def test_provider_failure_fault_injection_requires_human_stop_review() -> None:
    samples = healthy_samples()
    samples[0] = replace(samples[0], provider_ok=False)

    report = evaluate(samples)

    assert report.recommendation == "STOP"
    assert "provider failure: media" in report.reasons
    assert report.human_review_required is True
    assert report.automatic_stop_issued is False


def test_threshold_breach_is_degraded_while_budget_remains() -> None:
    samples = healthy_samples()
    samples[1] = replace(samples[1], value=1_700)

    report = evaluate(samples)

    assert report.recommendation == "DEGRADED"
    assert report.error_budget == 1
    assert "first-frame latency above target" in report.reasons
    assert report.human_review_required is False


def test_error_budget_exhaustion_recommends_stop_without_side_effect() -> None:
    samples = healthy_samples()
    samples[0] = replace(samples[0], value=0)

    report = evaluate(samples)

    assert report.startup_success == 0
    assert report.error_budget == 0
    assert report.recommendation == "STOP"
    assert "error budget exhausted" in report.reasons
    assert report.human_review_required is True
    assert report.automatic_stop_issued is False


def test_fault_recovery_becomes_green_in_the_next_clean_window() -> None:
    failed = healthy_samples()
    failed[0] = replace(failed[0], provider_ok=False)
    assert evaluate(failed).recommendation == "STOP"

    recovered_now = NOW + timedelta(minutes=6)
    recovered = [
        replace(item, observed_at=recovered_now - timedelta(seconds=5))
        for item in healthy_samples()
    ]
    report = evaluate(recovered, now=recovered_now)

    assert report.recommendation == "GREEN"
    assert report.error_budget == 1
    assert report.human_review_required is False


def test_invalid_values_and_future_evidence_fail_closed() -> None:
    samples = healthy_samples()
    samples[0] = replace(samples[0], value=1.1)
    samples[1] = replace(samples[1], observed_at=NOW + timedelta(seconds=1))

    report = evaluate(samples)

    assert report.recommendation == "STOP"
    assert any("out-of-range metric" in reason for reason in report.reasons)
    assert "future metric evidence" in report.reasons


def test_empty_input_and_naive_clock_fail_closed() -> None:
    empty = evaluate([])
    naive = evaluate(healthy_samples(), now=NOW.replace(tzinfo=None))

    assert empty.recommendation == "STOP"
    assert "missing metrics" in empty.reasons
    assert naive.recommendation == "STOP"
    assert "window end must be timezone-aware" in naive.reasons


def test_custom_window_and_targets_are_applied() -> None:
    targets = SloTargets(
        window=timedelta(minutes=1),
        freshness=timedelta(seconds=30),
        first_frame_ms=300,
    )

    report = evaluate(healthy_samples(), targets=targets)

    assert report.window_start == NOW - timedelta(minutes=1)
    assert report.recommendation == "DEGRADED"
    assert "first-frame latency above target" in report.reasons
