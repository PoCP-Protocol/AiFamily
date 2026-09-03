from __future__ import annotations

import pytest

from backend.intelligence.evaluation.release_gate import (
    AiReleaseGate,
    ReleaseGateError,
    ReleaseGateThresholds,
)
from backend.intelligence.experience.model_benchmark import (
    AnonymousGoldCase,
    ComplianceGate,
    ModelBenchmarkHarness,
    ModelCandidate,
    ModelCaseResult,
)
from backend.intelligence.model_gateway.provider_registry import ProviderRecord, ProviderRegistry


def _candidate(*, status: str = "INTERNAL_APPROVED") -> ModelCandidate:
    return ModelCandidate(
        candidate_id="candidate-a",
        provider_id="local-eval",
        model="local-model",
        model_version="v1",
        status=status,  # type: ignore[arg-type]
        compliance_gate=ComplianceGate(
            security_assessment_ref="internal",
            processing_agreement_ref="internal",
            sub_delegates=False,
            approved_environments=("benchmark", "test"),
            anonymous_data_allowed=True,
        ),
    )


def _report(*, safe: bool = True, latency: int = 100, cost: int = 10):
    case = AnonymousGoldCase(
        case_id="case-1",
        version="gold.v1",
        modalities=("text", "image"),
        expected_schema={"type": "object", "required": ["answer"]},
    )
    result = ModelCaseResult(
        candidate_id="candidate-a",
        case_id="case-1",
        schema_passed=True,
        safety_passed=safe,
        refusal_correct=True,
        latency_ms=latency,
        cost_microusd=cost,
    )
    return ModelBenchmarkHarness().evaluate(
        candidates=(_candidate(),),
        cases=(case,),
        results={"candidate-a": (result,)},
    )


def _registry(*, status: str = "INTERNAL_APPROVED") -> ProviderRegistry:
    return ProviderRegistry(
        [
            ProviderRecord(
                provider_id="local-eval",
                vendor="internal",
                model="local-model",
                model_version="v1",
                status=status,  # type: ignore[arg-type]
                approved_environments=("test",),
                sub_delegates=False,
                security_assessment_ref="internal",
                processing_agreement_ref="internal",
                deletion_on_termination_committed=True,
            )
        ]
    )


def test_release_gate_admits_only_when_provider_and_evidence_pass() -> None:
    decision = AiReleaseGate().evaluate(
        report=_report(),
        provider_registry=_registry(),
        environment="test",
    )

    assert decision.admitted
    assert decision.status == "ADMITTED"
    assert decision.failures == ()
    assert decision.report_ref.startswith("benchmark:model:gold.v1:")


def test_release_gate_fails_closed_for_unapproved_provider_even_with_perfect_metrics() -> None:
    decision = AiReleaseGate().evaluate(
        report=_report(),
        provider_registry=_registry(status="TECHNICALLY_VALIDATED"),
        environment="test",
    )

    assert not decision.admitted
    assert "provider_admission:POLICY_REJECTED" in decision.failures


def test_release_gate_blocks_safety_latency_and_cost_threshold_breaches() -> None:
    report = _report(safe=False, latency=2_001, cost=501)
    decision = AiReleaseGate().evaluate(
        report=report,
        provider_registry=_registry(),
        environment="test",
    )

    assert decision.status == "BLOCKED"
    assert {"safety_below_min", "latency_p95_above_max", "cost_average_above_max"}.issubset(
        decision.failures
    )


def test_release_gate_requires_candidate_for_multi_candidate_report() -> None:
    first = _candidate()
    second = ModelCandidate(
        candidate_id="candidate-b",
        provider_id="local-eval",
        model="local-model",
        model_version="v1",
        status="INTERNAL_APPROVED",
        compliance_gate=first.compliance_gate,
    )
    case = AnonymousGoldCase(
        case_id="case-1",
        version="gold.v1",
        modalities=("text",),
        expected_schema={"type": "object"},
    )
    report = ModelBenchmarkHarness().evaluate(
        candidates=(first, second),
        cases=(case,),
        results={
            "candidate-a": (ModelCaseResult("candidate-a", "case-1", True, True, True, 1, 1),),
            "candidate-b": (ModelCaseResult("candidate-b", "case-1", True, True, True, 1, 1),),
        },
    )
    with pytest.raises(ReleaseGateError, match="CANDIDATE_ID_REQUIRED"):
        AiReleaseGate().evaluate(report=report, provider_registry=_registry(), environment="test")


def test_threshold_configuration_is_validated() -> None:
    with pytest.raises(ReleaseGateError, match="THRESHOLD_RATES"):
        ReleaseGateThresholds(min_quality_score=1.1)
