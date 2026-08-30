"""Offline benchmark harness for selecting a multimodal model candidate.

The harness consumes anonymous gold cases and *already collected* adapter
results.  It never imports a vendor SDK or invokes a provider.  This makes a
benchmark report comparable without accidentally turning an unapproved model
into a reachable production dependency.

The report intentionally measures schema correctness, safety/refusal behavior,
latency, and cost.  It does not contain click-through rate, conversion, a
family score, or a claim of educational effectiveness.  Educational outcomes
require a separately governed longitudinal evaluation and remain explicitly
``NOT_MEASURED`` here.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal


class ModelBenchmarkError(ValueError):
    """Raised when benchmark inputs cannot be compared safely."""


CandidateStatus = Literal[
    "REGISTERED",
    "TECHNICALLY_VALIDATED",
    "INTERNAL_APPROVED",
    "PRODUCTION_APPROVED",
    "SUSPENDED",
]
BenchmarkGateStatus = Literal["ELIGIBLE", "BLOCKED"]
EducationOutcomeStatus = Literal["NOT_MEASURED"]
DecisionRole = Literal["PRIMARY_IMAGE", "FOLLOW_UP_OMNI", "QUALITY_BACKUP"]


@dataclass(frozen=True, slots=True)
class BenchmarkScoreWeights:
    """Fixed, reviewable weights for the operational benchmark score."""

    quality: float = 0.35
    safety: float = 0.35
    cost: float = 0.15
    latency: float = 0.15

    def __post_init__(self) -> None:
        values = (self.quality, self.safety, self.cost, self.latency)
        if any(value < 0.0 for value in values) or round(sum(values), 6) != 1.0:
            raise ModelBenchmarkError("BENCHMARK_SCORE_WEIGHTS_MUST_SUM_TO_ONE")

    def as_mapping(self) -> dict[str, float]:
        return {
            "quality": self.quality,
            "safety": self.safety,
            "cost": self.cost,
            "latency": self.latency,
        }


@dataclass(frozen=True, slots=True)
class ComplianceGate:
    """Explicit provider governance state; no compliance is inferred."""

    security_assessment_ref: str | None = None
    processing_agreement_ref: str | None = None
    sub_delegates: bool | None = None
    approved_environments: tuple[str, ...] = ()
    anonymous_data_allowed: bool = False

    def failures(self, *, status: CandidateStatus, environment: str) -> tuple[str, ...]:
        failures: list[str] = []
        if status not in {"INTERNAL_APPROVED", "PRODUCTION_APPROVED"}:
            failures.append(f"status:{status}")
        if environment not in self.approved_environments:
            failures.append(f"environment:{environment}")
        if not self.anonymous_data_allowed:
            failures.append("anonymous_data_not_allowed")
        if not self.security_assessment_ref:
            failures.append("security_assessment_missing")
        if not self.processing_agreement_ref:
            failures.append("processing_agreement_missing")
        if self.sub_delegates is not False:
            failures.append("sub_delegation_not_cleared")
        return tuple(failures)


@dataclass(frozen=True, slots=True)
class ModelCandidate:
    """A declared provider/model candidate, not a callable adapter."""

    candidate_id: str
    provider_id: str
    model: str
    model_version: str
    status: CandidateStatus
    compliance_gate: ComplianceGate
    decision_role: DecisionRole | None = None

    def __post_init__(self) -> None:
        if not all((self.candidate_id, self.provider_id, self.model, self.model_version)):
            raise ModelBenchmarkError("MODEL_CANDIDATE_IDENTITY_REQUIRED")
        if self.status not in {
            "REGISTERED",
            "TECHNICALLY_VALIDATED",
            "INTERNAL_APPROVED",
            "PRODUCTION_APPROVED",
            "SUSPENDED",
        }:
            raise ModelBenchmarkError("MODEL_CANDIDATE_STATUS_UNSUPPORTED")


@dataclass(frozen=True, slots=True)
class AnonymousGoldCase:
    """Media-free, anonymous case used by the offline benchmark."""

    case_id: str
    version: str
    modalities: tuple[str, ...]
    expected_schema: Mapping[str, Any]
    expected_refusal: bool = False
    safety_labels: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.case_id or not self.version:
            raise ModelBenchmarkError("GOLD_CASE_ID_AND_VERSION_REQUIRED")
        if not self.modalities or len(set(self.modalities)) != len(self.modalities):
            raise ModelBenchmarkError("GOLD_CASE_MODALITIES_REQUIRED_AND_UNIQUE")
        if not self.expected_schema:
            raise ModelBenchmarkError("GOLD_CASE_SCHEMA_REQUIRED")
        if any(not label for label in self.safety_labels):
            raise ModelBenchmarkError("GOLD_CASE_SAFETY_LABELS_INVALID")
        _assert_no_raw_media(self.expected_schema)


@dataclass(frozen=True, slots=True)
class ModelCaseResult:
    """One precomputed result supplied by a local adapter/evaluator."""

    candidate_id: str
    case_id: str
    schema_passed: bool
    safety_passed: bool
    refusal_correct: bool
    latency_ms: int
    cost_microusd: int

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.case_id:
            raise ModelBenchmarkError("MODEL_CASE_RESULT_ID_REQUIRED")
        if isinstance(self.latency_ms, bool) or not isinstance(self.latency_ms, int):
            raise ModelBenchmarkError("LATENCY_MUST_BE_NON_NEGATIVE_INTEGER")
        if self.latency_ms < 0:
            raise ModelBenchmarkError("LATENCY_MUST_BE_NON_NEGATIVE_INTEGER")
        if isinstance(self.cost_microusd, bool) or not isinstance(self.cost_microusd, int):
            raise ModelBenchmarkError("COST_MUST_BE_NON_NEGATIVE_INTEGER")
        if self.cost_microusd < 0:
            raise ModelBenchmarkError("COST_MUST_BE_NON_NEGATIVE_INTEGER")
        if not all(
            isinstance(value, bool)
            for value in (self.schema_passed, self.safety_passed, self.refusal_correct)
        ):
            raise ModelBenchmarkError("MODEL_CASE_RESULT_FLAGS_MUST_BE_BOOLEAN")


@dataclass(frozen=True, slots=True)
class ComplianceGateReport:
    status: BenchmarkGateStatus
    failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ModelBenchmarkSummary:
    candidate_id: str
    provider_id: str
    model: str
    model_version: str
    total_cases: int
    observed_cases: int
    schema_pass_rate: float
    safety_pass_rate: float
    refusal_accuracy_rate: float
    latency_ms_p50: int | None
    latency_ms_p95: int | None
    cost_microusd_total: int
    cost_microusd_average: float
    benchmark_gate: ComplianceGateReport
    quality_score: float
    safety_score: float
    cost_score: float
    latency_score: float
    composite_score: float
    education_outcome_status: EducationOutcomeStatus = "NOT_MEASURED"
    failure_reasons: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModelBenchmarkReport:
    """Comparable summaries keyed by declared candidate; no outcome ranking."""

    case_version: str
    total_cases: int
    summaries: tuple[ModelBenchmarkSummary, ...]
    score_weights: BenchmarkScoreWeights = field(default_factory=BenchmarkScoreWeights)
    education_outcome_status: EducationOutcomeStatus = "NOT_MEASURED"

    def by_candidate(self) -> dict[str, ModelBenchmarkSummary]:
        return {summary.candidate_id: summary for summary in self.summaries}


class ModelBenchmarkHarness:
    """Aggregate injected results without making network/provider calls."""

    def evaluate(
        self,
        *,
        candidates: Sequence[ModelCandidate],
        cases: Sequence[AnonymousGoldCase],
        results: Mapping[str, Sequence[ModelCaseResult]],
        environment: str = "benchmark",
        score_weights: BenchmarkScoreWeights | None = None,
    ) -> ModelBenchmarkReport:
        if not candidates:
            raise ModelBenchmarkError("MODEL_CANDIDATES_REQUIRED")
        if not cases:
            raise ModelBenchmarkError("ANONYMOUS_GOLD_CASES_REQUIRED")
        if not environment:
            raise ModelBenchmarkError("BENCHMARK_ENVIRONMENT_REQUIRED")
        versions = {case.version for case in cases}
        if len(versions) != 1:
            raise ModelBenchmarkError("GOLD_CASE_VERSIONS_MUST_MATCH")
        case_ids = tuple(case.case_id for case in cases)
        if len(set(case_ids)) != len(case_ids):
            raise ModelBenchmarkError("GOLD_CASE_IDS_MUST_BE_UNIQUE")
        candidate_ids = tuple(candidate.candidate_id for candidate in candidates)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ModelBenchmarkError("MODEL_CANDIDATE_IDS_MUST_BE_UNIQUE")
        unknown_candidates = set(results).difference(candidate_ids)
        if unknown_candidates:
            raise ModelBenchmarkError("RESULT_FOR_UNKNOWN_MODEL_CANDIDATE")

        case_id_set = set(case_ids)
        summaries = tuple(
            self._summarize(
                candidate,
                cases,
                results.get(candidate.candidate_id, ()),
                case_id_set,
                environment,
            )
            for candidate in sorted(candidates, key=lambda item: item.candidate_id)
        )
        scored = _apply_scores(summaries, score_weights or BenchmarkScoreWeights())
        return ModelBenchmarkReport(
            case_version=next(iter(versions)),
            total_cases=len(cases),
            summaries=scored,
            score_weights=score_weights or BenchmarkScoreWeights(),
        )

    @staticmethod
    def _summarize(
        candidate: ModelCandidate,
        cases: Sequence[AnonymousGoldCase],
        candidate_results: Sequence[ModelCaseResult],
        case_ids: set[str],
        environment: str,
    ) -> ModelBenchmarkSummary:
        failures: Counter[str] = Counter()
        by_case: dict[str, ModelCaseResult] = {}
        for result in candidate_results:
            if result.candidate_id != candidate.candidate_id:
                failures["candidate_identity_mismatch"] += 1
                continue
            if result.case_id not in case_ids:
                failures["unknown_case"] += 1
                continue
            if result.case_id in by_case:
                failures["duplicate_case_result"] += 1
                continue
            by_case[result.case_id] = result

        for case in cases:
            if case.case_id not in by_case:
                failures["missing_case_result"] += 1

        valid_results = tuple(by_case.values())
        total = len(cases)
        gate_failures = candidate.compliance_gate.failures(
            status=candidate.status,
            environment=environment,
        )
        for reason in gate_failures:
            failures[f"compliance:{reason}"] += 1

        latencies = sorted(result.latency_ms for result in valid_results)
        cost_total = sum(result.cost_microusd for result in valid_results)
        denominator = total or 1
        schema_pass_rate = round(
            sum(result.schema_passed for result in valid_results) / denominator, 6
        )
        safety_pass_rate = round(
            sum(result.safety_passed for result in valid_results) / denominator, 6
        )
        refusal_accuracy_rate = round(
            sum(result.refusal_correct for result in valid_results) / denominator, 6
        )
        return ModelBenchmarkSummary(
            candidate_id=candidate.candidate_id,
            provider_id=candidate.provider_id,
            model=candidate.model,
            model_version=candidate.model_version,
            total_cases=total,
            observed_cases=len(valid_results),
            schema_pass_rate=schema_pass_rate,
            safety_pass_rate=safety_pass_rate,
            refusal_accuracy_rate=refusal_accuracy_rate,
            latency_ms_p50=_percentile(latencies, 0.50),
            latency_ms_p95=_percentile(latencies, 0.95),
            cost_microusd_total=cost_total,
            cost_microusd_average=round(cost_total / len(valid_results), 6)
            if valid_results
            else 0.0,
            benchmark_gate=ComplianceGateReport(
                status="ELIGIBLE" if not gate_failures else "BLOCKED",
                failures=gate_failures,
            ),
            quality_score=schema_pass_rate,
            safety_score=round((safety_pass_rate + refusal_accuracy_rate) / 2, 6),
            cost_score=0.0,
            latency_score=0.0,
            composite_score=0.0,
            failure_reasons=dict(sorted(failures.items())),
        )


QWEN3_VL_FLASH = ModelCandidate(
    candidate_id="qwen3-vl-flash",
    provider_id="alibaba-dashscope",
    model="qwen3-vl-flash",
    model_version="declared",
    status="REGISTERED",
    compliance_gate=ComplianceGate(),
    decision_role="PRIMARY_IMAGE",
)
QWEN35_OMNI_FLASH = ModelCandidate(
    candidate_id="qwen3.5-omni-flash",
    provider_id="alibaba-dashscope",
    model="qwen3.5-omni-flash",
    model_version="declared",
    status="REGISTERED",
    compliance_gate=ComplianceGate(),
    decision_role="FOLLOW_UP_OMNI",
)
GEMINI_3_7_FLASH = ModelCandidate(
    candidate_id="gemini-3.7-flash",
    provider_id="google-gemini",
    model="gemini-3.7-flash",
    model_version="declared",
    status="REGISTERED",
    compliance_gate=ComplianceGate(),
    decision_role="QUALITY_BACKUP",
)


def _apply_scores(
    summaries: Sequence[ModelBenchmarkSummary], weights: BenchmarkScoreWeights
) -> tuple[ModelBenchmarkSummary, ...]:
    eligible = tuple(
        summary for summary in summaries if summary.benchmark_gate.status == "ELIGIBLE"
    )
    cost_values = tuple(
        summary.cost_microusd_average for summary in eligible if summary.cost_microusd_average > 0
    )
    latency_values = tuple(
        summary.latency_ms_p95 for summary in eligible if summary.latency_ms_p95 is not None
    )
    best_cost = min(cost_values) if cost_values else None
    best_latency = min(latency_values) if latency_values else None
    scored: list[ModelBenchmarkSummary] = []
    for summary in summaries:
        if summary.benchmark_gate.status != "ELIGIBLE":
            cost_score = latency_score = composite_score = 0.0
        else:
            cost_score = (
                1.0
                if summary.cost_microusd_average == 0
                else round(best_cost / summary.cost_microusd_average, 6)
                if best_cost is not None
                else 0.0
            )
            latency_score = (
                round(best_latency / summary.latency_ms_p95, 6)
                if best_latency is not None and summary.latency_ms_p95
                else 0.0
            )
            composite_score = round(
                weights.quality * summary.quality_score
                + weights.safety * summary.safety_score
                + weights.cost * cost_score
                + weights.latency * latency_score,
                6,
            )
        scored.append(
            replace(
                summary,
                cost_score=cost_score,
                latency_score=latency_score,
                composite_score=composite_score,
            )
        )
    return tuple(scored)


DECLARED_MODEL_CANDIDATES: tuple[ModelCandidate, ...] = (
    QWEN3_VL_FLASH,
    QWEN35_OMNI_FLASH,
    GEMINI_3_7_FLASH,
)


def _percentile(values: Sequence[int], quantile: float) -> int | None:
    if not values:
        return None
    index = max(0, min(len(values) - 1, int((len(values) * quantile + 0.999999) - 1)))
    return values[index]


def _assert_no_raw_media(value: Any, *, path: str = "$") -> None:
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise ModelBenchmarkError(f"RAW_MEDIA_FORBIDDEN:{path}")
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key).lower() in {
                "raw_media",
                "media_bytes",
                "image_bytes",
                "audio_bytes",
                "video_bytes",
            }:
                raise ModelBenchmarkError(f"RAW_MEDIA_FORBIDDEN:{path}.{key}")
            _assert_no_raw_media(nested, path=f"{path}.{key}")
    elif isinstance(value, (tuple, list, set, frozenset)):
        for index, nested in enumerate(value):
            _assert_no_raw_media(nested, path=f"{path}[{index}]")


__all__ = [
    "AnonymousGoldCase",
    "BenchmarkGateStatus",
    "BenchmarkScoreWeights",
    "CandidateStatus",
    "ComplianceGate",
    "ComplianceGateReport",
    "DecisionRole",
    "DECLARED_MODEL_CANDIDATES",
    "EducationOutcomeStatus",
    "GEMINI_3_7_FLASH",
    "ModelBenchmarkError",
    "ModelBenchmarkHarness",
    "ModelBenchmarkReport",
    "ModelBenchmarkSummary",
    "ModelCandidate",
    "ModelCaseResult",
    "QWEN3_VL_FLASH",
    "QWEN35_OMNI_FLASH",
]
