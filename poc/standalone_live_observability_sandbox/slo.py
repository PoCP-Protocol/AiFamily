"""Synthetic-only SLO evaluation for the standalone live sandbox.

The evaluator is deliberately side-effect free.  In particular, ``STOP`` is an
operations recommendation that requires a human decision; it never calls a
control-plane or media stop endpoint.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import ceil, isfinite
from typing import Literal

Component = Literal["media", "interaction", "control", "replay"]
Recommendation = Literal["GREEN", "DEGRADED", "STOP"]

SYNTHETIC_SOURCES = frozenset({"synthetic", "SANDBOX_SYNTHETIC"})
REQUIRED_METRICS: dict[Component, frozenset[str]] = {
    "media": frozenset({"startup_success", "first_frame_ms", "stall_ratio", "recovery_ms"}),
    "interaction": frozenset({"interaction_latency_ms"}),
    "control": frozenset({"request_success"}),
    "replay": frozenset({"request_success"}),
}
SUCCESS_METRICS = frozenset(
    {
        ("media", "startup_success"),
        ("control", "request_success"),
        ("replay", "request_success"),
    }
)


@dataclass(frozen=True, slots=True)
class MetricSample:
    """One scoped metric observation from a synthetic live session."""

    component: Component
    metric: str
    value: float
    observed_at: datetime
    tenant_id: str
    family_id: str
    session_ref: str
    source: str = "SANDBOX_SYNTHETIC"
    fixture_only: bool = True
    provider_ok: bool = True


@dataclass(frozen=True, slots=True)
class SloTargets:
    """Sandbox thresholds; these are not production release targets."""

    window: timedelta = timedelta(minutes=5)
    freshness: timedelta = timedelta(seconds=45)
    startup_success: float = 0.99
    first_frame_ms: float = 1_500.0
    stall_ratio: float = 0.02
    interaction_latency_ms: float = 300.0
    recovery_ms: float = 3_000.0
    request_success: float = 0.99
    degraded_budget_remaining: float = 0.25


@dataclass(frozen=True, slots=True)
class SloReport:
    """Calculated live SLO evidence and a non-executing operator suggestion."""

    window_start: datetime
    window_end: datetime
    sample_count: int
    startup_success: float | None
    first_frame_ms: float | None
    stall_ratio: float | None
    interaction_latency_ms: float | None
    recovery_ms: float | None
    error_budget: float
    recommendation: Recommendation
    reasons: tuple[str, ...]
    human_review_required: bool
    automatic_stop_issued: bool = False


def evaluate_slo(
    samples: Sequence[MetricSample],
    *,
    tenant_id: str,
    family_id: str,
    session_ref: str,
    now: datetime,
    targets: SloTargets | None = None,
) -> SloReport:
    """Evaluate one live session window, failing closed on unsafe evidence."""

    policy = targets or SloTargets()
    window_start = now - policy.window
    unsafe_reasons = _validate_inputs(
        samples,
        tenant_id=tenant_id,
        family_id=family_id,
        session_ref=session_ref,
        now=now,
        targets=policy,
    )
    if unsafe_reasons:
        return _stopped_report(window_start, now, samples, unsafe_reasons)

    window_samples = [sample for sample in samples if window_start <= sample.observed_at <= now]
    missing = _missing_metrics(window_samples)
    if missing:
        return _stopped_report(
            window_start,
            now,
            window_samples,
            ("missing metrics: " + ", ".join(missing),),
        )

    stale = _stale_metrics(window_samples, now=now, freshness=policy.freshness)
    if stale:
        return _stopped_report(
            window_start,
            now,
            window_samples,
            ("stale metrics: " + ", ".join(stale),),
        )

    startup_success = _mean(_values(window_samples, "media", "startup_success"))
    first_frame_ms = _percentile(_values(window_samples, "media", "first_frame_ms"), 0.95)
    stall_ratio = _mean(_values(window_samples, "media", "stall_ratio"))
    interaction_latency_ms = _percentile(
        _values(window_samples, "interaction", "interaction_latency_ms"), 0.95
    )
    recovery_ms = _percentile(_values(window_samples, "media", "recovery_ms"), 0.95)
    control_success = _mean(_values(window_samples, "control", "request_success"))
    replay_success = _mean(_values(window_samples, "replay", "request_success"))
    error_budget = _error_budget(window_samples, policy)

    violations = []
    if startup_success < policy.startup_success:
        violations.append("startup success below target")
    if first_frame_ms > policy.first_frame_ms:
        violations.append("first-frame latency above target")
    if stall_ratio > policy.stall_ratio:
        violations.append("stall ratio above target")
    if interaction_latency_ms > policy.interaction_latency_ms:
        violations.append("interaction latency above target")
    if recovery_ms > policy.recovery_ms:
        violations.append("recovery latency above target")
    if control_success < policy.request_success:
        violations.append("control success below target")
    if replay_success < policy.request_success:
        violations.append("replay success below target")

    if error_budget <= 0:
        recommendation: Recommendation = "STOP"
        violations.append("error budget exhausted")
    elif violations or error_budget <= policy.degraded_budget_remaining:
        recommendation = "DEGRADED"
    else:
        recommendation = "GREEN"

    return SloReport(
        window_start=window_start,
        window_end=now,
        sample_count=len(window_samples),
        startup_success=startup_success,
        first_frame_ms=first_frame_ms,
        stall_ratio=stall_ratio,
        interaction_latency_ms=interaction_latency_ms,
        recovery_ms=recovery_ms,
        error_budget=error_budget,
        recommendation=recommendation,
        reasons=tuple(dict.fromkeys(violations)),
        human_review_required=recommendation == "STOP",
    )


def _validate_inputs(
    samples: Sequence[MetricSample],
    *,
    tenant_id: str,
    family_id: str,
    session_ref: str,
    now: datetime,
    targets: SloTargets,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if not samples:
        reasons.append("missing metrics")
    if now.tzinfo is None:
        reasons.append("window end must be timezone-aware")
    if targets.window <= timedelta(0) or targets.freshness <= timedelta(0):
        reasons.append("invalid evaluation window")

    for sample in samples:
        if sample.observed_at.tzinfo is None:
            reasons.append("metric timestamp must be timezone-aware")
        if (
            sample.tenant_id != tenant_id
            or sample.family_id != family_id
            or sample.session_ref != session_ref
        ):
            reasons.append("cross-scope metric evidence")
        if sample.source not in SYNTHETIC_SOURCES or sample.fixture_only is not True:
            reasons.append("non-synthetic metric evidence")
        if not sample.provider_ok:
            reasons.append(f"provider failure: {sample.component}")
        if not isfinite(sample.value):
            reasons.append(f"invalid metric value: {sample.component}.{sample.metric}")
        if (
            sample.observed_at.tzinfo is not None
            and now.tzinfo is not None
            and sample.observed_at > now
        ):
            reasons.append("future metric evidence")
        if not _value_in_range(sample):
            reasons.append(f"out-of-range metric: {sample.component}.{sample.metric}")
    return tuple(dict.fromkeys(reasons))


def _value_in_range(sample: MetricSample) -> bool:
    if sample.metric in {"startup_success", "request_success", "stall_ratio"}:
        return 0 <= sample.value <= 1
    return sample.value >= 0


def _missing_metrics(samples: Sequence[MetricSample]) -> list[str]:
    present = {(sample.component, sample.metric) for sample in samples}
    return sorted(
        f"{component}.{metric}"
        for component, metrics in REQUIRED_METRICS.items()
        for metric in metrics
        if (component, metric) not in present
    )


def _stale_metrics(
    samples: Sequence[MetricSample], *, now: datetime, freshness: timedelta
) -> list[str]:
    latest: dict[tuple[Component, str], datetime] = {}
    for sample in samples:
        key = (sample.component, sample.metric)
        latest[key] = max(latest.get(key, sample.observed_at), sample.observed_at)
    return sorted(
        f"{component}.{metric}"
        for (component, metric), observed_at in latest.items()
        if now - observed_at > freshness
    )


def _values(samples: Sequence[MetricSample], component: Component, metric: str) -> list[float]:
    return [
        sample.value
        for sample in samples
        if sample.component == component and sample.metric == metric
    ]


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    rank = max(1, ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def _error_budget(samples: Sequence[MetricSample], targets: SloTargets) -> float:
    success_samples = [
        sample for sample in samples if (sample.component, sample.metric) in SUCCESS_METRICS
    ]
    failures = sum(1 for sample in success_samples if sample.value < 1)
    allowed_failure_ratio = 1 - min(targets.startup_success, targets.request_success)
    allowed_failures = len(success_samples) * allowed_failure_ratio
    if allowed_failures <= 0:
        return 1.0 if failures == 0 else 0.0
    return max(0.0, min(1.0, (allowed_failures - failures) / allowed_failures))


def _stopped_report(
    window_start: datetime,
    now: datetime,
    samples: Sequence[MetricSample],
    reasons: tuple[str, ...],
) -> SloReport:
    return SloReport(
        window_start=window_start,
        window_end=now,
        sample_count=len(samples),
        startup_success=None,
        first_frame_ms=None,
        stall_ratio=None,
        interaction_latency_ms=None,
        recovery_ms=None,
        error_budget=0.0,
        recommendation="STOP",
        reasons=reasons,
        human_review_required=True,
    )
