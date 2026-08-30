from __future__ import annotations

import pytest

from backend.intelligence.experience.model_benchmark import (
    DECLARED_MODEL_CANDIDATES,
    AnonymousGoldCase,
    BenchmarkScoreWeights,
    ComplianceGate,
    ModelBenchmarkError,
    ModelBenchmarkHarness,
    ModelCandidate,
    ModelCaseResult,
)


def _case(case_id: str = "case-1") -> AnonymousGoldCase:
    return AnonymousGoldCase(
        case_id=case_id,
        version="gold.v1",
        modalities=("text", "image"),
        expected_schema={"type": "object", "required": ["answer"]},
        safety_labels=("safe",),
    )


def _candidate(*, candidate_id: str = "candidate-qwen") -> ModelCandidate:
    return ModelCandidate(
        candidate_id=candidate_id,
        provider_id="local-eval",
        model="qwen3-vl-flash",
        model_version="2026-08",
        status="INTERNAL_APPROVED",
        compliance_gate=ComplianceGate(
            security_assessment_ref="assessment-1",
            processing_agreement_ref="agreement-1",
            sub_delegates=False,
            approved_environments=("benchmark",),
            anonymous_data_allowed=True,
        ),
    )


def _result(candidate_id: str, case_id: str, *, latency: int = 100) -> ModelCaseResult:
    return ModelCaseResult(
        candidate_id=candidate_id,
        case_id=case_id,
        schema_passed=True,
        safety_passed=True,
        refusal_correct=True,
        latency_ms=latency,
        cost_microusd=12,
    )


def test_harness_compares_precomputed_results_and_cost_latency() -> None:
    candidate = _candidate()
    report = ModelBenchmarkHarness().evaluate(
        candidates=(candidate,),
        cases=(_case(), _case("case-2")),
        results={
            candidate.candidate_id: (
                _result(candidate.candidate_id, "case-1", latency=80),
                _result(candidate.candidate_id, "case-2", latency=200),
            )
        },
    )

    summary = report.by_candidate()[candidate.candidate_id]
    assert report.case_version == "gold.v1"
    assert summary.observed_cases == 2
    assert summary.schema_pass_rate == 1.0
    assert summary.safety_pass_rate == 1.0
    assert summary.refusal_accuracy_rate == 1.0
    assert summary.latency_ms_p50 == 80
    assert summary.latency_ms_p95 == 200
    assert summary.cost_microusd_total == 24
    assert summary.cost_microusd_average == 12.0
    assert summary.benchmark_gate.status == "ELIGIBLE"
    assert summary.quality_score == 1.0
    assert summary.safety_score == 1.0
    assert summary.cost_score == 1.0
    assert summary.latency_score == 1.0
    assert summary.composite_score == 1.0
    assert report.score_weights.as_mapping() == {
        "quality": 0.35,
        "safety": 0.35,
        "cost": 0.15,
        "latency": 0.15,
    }
    assert report.education_outcome_status == "NOT_MEASURED"
    assert not hasattr(summary, "click_through_rate")


def test_compliance_gate_is_explicit_and_blocks_declared_candidates() -> None:
    report = ModelBenchmarkHarness().evaluate(
        candidates=DECLARED_MODEL_CANDIDATES,
        cases=(_case(),),
        results={
            candidate.candidate_id: (_result(candidate.candidate_id, "case-1"),)
            for candidate in DECLARED_MODEL_CANDIDATES
        },
    )

    summaries = report.by_candidate()
    assert set(summaries) == {
        "qwen3-vl-flash",
        "qwen3.5-omni-flash",
        "gemini-3.7-flash",
    }
    for summary in summaries.values():
        assert summary.benchmark_gate.status == "BLOCKED"
        assert "compliance:status:REGISTERED" in summary.failure_reasons
        assert "compliance:security_assessment_missing" in summary.failure_reasons


def test_missing_case_result_is_visible_and_not_treated_as_pass() -> None:
    candidate = _candidate()
    summary = (
        ModelBenchmarkHarness()
        .evaluate(
            candidates=(candidate,),
            cases=(_case(), _case("case-2")),
            results={candidate.candidate_id: (_result(candidate.candidate_id, "case-1"),)},
        )
        .summaries[0]
    )

    assert summary.total_cases == 2
    assert summary.observed_cases == 1
    assert summary.schema_pass_rate == 0.5
    assert summary.failure_reasons["missing_case_result"] == 1


def test_gold_case_rejects_raw_media_and_result_rejects_negative_cost() -> None:
    with pytest.raises(ModelBenchmarkError, match="RAW_MEDIA_FORBIDDEN"):
        AnonymousGoldCase(
            case_id="raw",
            version="gold.v1",
            modalities=("image",),
            expected_schema={"raw_media": "bytes"},
        )
    with pytest.raises(ModelBenchmarkError, match="COST_MUST_BE_NON_NEGATIVE"):
        ModelCaseResult(
            candidate_id="candidate-qwen",
            case_id="case-1",
            schema_passed=True,
            safety_passed=True,
            refusal_correct=True,
            latency_ms=1,
            cost_microusd=-1,
        )


def test_benchmark_rejects_mixed_gold_versions() -> None:
    with pytest.raises(ModelBenchmarkError, match="VERSIONS_MUST_MATCH"):
        ModelBenchmarkHarness().evaluate(
            candidates=(_candidate(),),
            cases=(
                _case("case-1"),
                AnonymousGoldCase(
                    case_id="case-2",
                    version="gold.v2",
                    modalities=("text",),
                    expected_schema={"type": "object"},
                ),
            ),
            results={},
        )


def test_scores_are_auditable_and_normalized_across_eligible_candidates() -> None:
    first = _candidate(candidate_id="candidate-a")
    second = _candidate(candidate_id="candidate-b")
    report = ModelBenchmarkHarness().evaluate(
        candidates=(first, second),
        cases=(_case(), _case("case-2")),
        results={
            first.candidate_id: (
                _result(first.candidate_id, "case-1", latency=100),
                _result(first.candidate_id, "case-2", latency=100),
            ),
            second.candidate_id: (
                ModelCaseResult(
                    candidate_id=second.candidate_id,
                    case_id="case-1",
                    schema_passed=False,
                    safety_passed=True,
                    refusal_correct=True,
                    latency_ms=200,
                    cost_microusd=24,
                ),
                ModelCaseResult(
                    candidate_id=second.candidate_id,
                    case_id="case-2",
                    schema_passed=True,
                    safety_passed=False,
                    refusal_correct=False,
                    latency_ms=200,
                    cost_microusd=24,
                ),
            ),
        },
        score_weights=BenchmarkScoreWeights(quality=0.5, safety=0.3, cost=0.1, latency=0.1),
    )

    scores = report.by_candidate()
    assert scores["candidate-a"].composite_score == 1.0
    assert scores["candidate-b"].quality_score == 0.5
    assert scores["candidate-b"].safety_score == 0.5
    assert scores["candidate-b"].cost_score == 0.5
    assert scores["candidate-b"].latency_score == 0.5
    assert scores["candidate-b"].composite_score == 0.5


def test_score_weights_must_be_auditable_sum_to_one() -> None:
    with pytest.raises(ModelBenchmarkError, match="SUM_TO_ONE"):
        BenchmarkScoreWeights(quality=0.5, safety=0.5, cost=0.5, latency=0.5)
