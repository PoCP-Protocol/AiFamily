from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from backend.intelligence.experience.multimodal_eval import (
    EvaluationGatePolicy,
    EvaluationReleaseDecision,
    EvaluationReleaseGate,
    GoldCase,
    MultimodalAdapterResult,
    MultimodalEvalError,
    MultimodalEvalRunner,
    persist_evaluation_projection,
)
from backend.intelligence.experience.run_http import InMemoryExperienceRunLedger, RunScope
from backend.intelligence.model_gateway.contracts import AiProvenance


def _case(
    *,
    case_id: str = "case-1",
    expected_refusal: bool = False,
    expected_output: dict[str, Any] | None = None,
) -> GoldCase:
    return GoldCase(
        case_id=case_id,
        version="gold.v1",
        fixture_kind="synthetic",
        modalities=("text", "image"),
        locale="zh-CN",
        safety_labels=("safe",),
        expected_schema={
            "type": "object",
            "required": ["answer"],
            "properties": {"answer": {"type": "string"}},
        },
        expected_refusal=expected_refusal,
        media_refs=(f"fixture:{case_id}:image",),
        expected_output=expected_output,
    )


def _result(
    case: GoldCase,
    *,
    output: dict[str, Any] | None = None,
    refused: bool = False,
    labels: tuple[str, ...] = ("safe",),
    safety_passed: bool = True,
    latency_ms: int = 120,
    cost_microusd: int = 10,
    provider_id: str = "qwen",
) -> MultimodalAdapterResult:
    return MultimodalAdapterResult(
        provider_id=provider_id,
        model="qwen-omni",
        model_version="2026-08",
        output=output,
        refused=refused,
        refusal_reason="policy" if refused else None,
        safety_labels=labels,
        safety_passed=safety_passed,
        provenance=AiProvenance(
            provider_id=provider_id,
            model="qwen-omni",
            model_version="2026-08",
            prompt_version="prompt.v1",
            schema_version=case.version,
            context_snapshot_ref="ctx:synthetic",
            latency_ms=latency_ms,
            data_class="SYNTHETIC",
            use_case="offline-eval",
        ),
        latency_ms=latency_ms,
        cost_microusd=cost_microusd,
    )


def test_runner_aggregates_provider_model_version_without_media() -> None:
    cases = (_case(expected_output={"answer": "ok"}), _case(case_id="case-2"))

    def adapter(case: GoldCase) -> MultimodalAdapterResult:
        return _result(
            case, output={"answer": "ok"}, latency_ms=100 if case.case_id == "case-1" else 200
        )

    report = MultimodalEvalRunner().run(cases, {"qwen": adapter})
    summary = report.by_provider()[("qwen", "qwen-omni", "2026-08")]

    assert report.case_version == "gold.v1"
    assert summary.total_cases == 2
    assert summary.passed_cases == 2
    assert summary.quality_score == 1.0
    assert summary.schema_pass_rate == 1.0
    assert summary.refusal_accuracy_rate == 1.0
    assert summary.safety_pass_rate == 1.0
    assert summary.provenance_pass_rate == 1.0
    assert summary.latency_ms_p50 == 100
    assert summary.latency_ms_p95 == 200
    assert summary.cost_microusd_total == 20
    assert report.report_ref.startswith("benchmark:multimodal:gold.v1:")
    duplicate = MultimodalEvalRunner().run(cases, {"qwen": adapter})
    assert duplicate.report_ref == report.report_ref
    gate = EvaluationReleaseGate().evaluate(report)
    assert gate.status == "ELIGIBLE"
    assert gate.reasons == ()
    assert gate.education_outcome_status == "NOT_MEASURED"
    projection = report.to_ledger_payload(gate)
    assert projection["report_ref"] == report.report_ref
    assert projection["release_gate"] == {"status": "ELIGIBLE", "reasons": []}
    assert projection["education_outcome_status"] == "NOT_MEASURED"


def test_runner_evaluates_feedback_context_without_recording_raw_feedback() -> None:
    steady = {
        "signal_counts": {"helpful": 2, "not_helpful": 0, "request_human": 0},
        "sample_size": 2,
    }
    slower = {
        "signal_counts": {"helpful": 0, "not_helpful": 2, "request_human": 0},
        "sample_size": 2,
    }
    cases = (
        _case(case_id="case-steady", expected_output={"answer": "steady"}),
        _case(case_id="case-slower", expected_output={"answer": "slower"}),
    )
    cases = tuple(
        replace(case, feedback_context=context)
        for case, context in zip(cases, (steady, slower), strict=True)
    )

    def adapter(case: GoldCase) -> MultimodalAdapterResult:
        context = case.feedback_context or {}
        counts = context["signal_counts"]
        answer = "slower" if counts["not_helpful"] else "steady"
        return _result(case, output={"answer": answer})

    report = MultimodalEvalRunner().run(cases, {"qwen": adapter})
    summary = report.by_provider()[("qwen", "qwen-omni", "2026-08")]
    assert summary.passed_cases == 2
    assert summary.quality_score == 1.0


def test_gold_case_rejects_unbounded_feedback_context() -> None:
    with pytest.raises(MultimodalEvalError, match="feedback_context sample size"):
        GoldCase(
            case_id="invalid-feedback",
            version="gold.v1",
            fixture_kind="synthetic",
            modalities=("text",),
            locale="zh-CN",
            safety_labels=("safe",),
            expected_schema={"type": "object"},
            feedback_context={
                "signal_counts": {"helpful": 1, "not_helpful": 0, "request_human": 0},
                "sample_size": 99,
            },
        )


def test_release_gate_blocks_failed_contracts_and_enforces_limits() -> None:
    case = _case()

    def adapter(_: GoldCase) -> MultimodalAdapterResult:
        return _result(case, output={"answer": "ok"}, safety_passed=False, latency_ms=500)

    report = MultimodalEvalRunner().run((case,), {"qwen": adapter})
    decision = EvaluationReleaseGate(
        EvaluationGatePolicy(max_latency_ms_p95=200)
    ).evaluate(report)

    assert decision.status == "BLOCKED"
    assert "qwen:qwen-omni:2026-08:safety_rate_below_threshold" in decision.reasons
    assert "qwen:qwen-omni:2026-08:latency_p95_exceeded" in decision.reasons


def test_release_gate_rejects_invalid_policy_limits() -> None:
    with pytest.raises(MultimodalEvalError, match="between 0 and 1"):
        EvaluationGatePolicy(min_pass_rate=1.1)
    with pytest.raises(MultimodalEvalError, match="between 0 and 1"):
        EvaluationGatePolicy(min_pass_rate="strict")  # type: ignore[arg-type]
    with pytest.raises(MultimodalEvalError, match="non-negative"):
        EvaluationGatePolicy(max_latency_ms_p95=-1)
    with pytest.raises(MultimodalEvalError, match="non-negative"):
        EvaluationGatePolicy(max_cost_microusd_total="free")  # type: ignore[arg-type]


def test_release_decision_rejects_unscoped_or_measured_outcomes() -> None:
    with pytest.raises(MultimodalEvalError, match="report reference"):
        EvaluationReleaseDecision(
            report_ref="benchmark:model:gold.v1:abc",
            status="ELIGIBLE",
            reasons=(),
        )
    with pytest.raises(MultimodalEvalError, match="not measured"):
        EvaluationReleaseDecision(
            report_ref="benchmark:multimodal:gold.v1:abc",
            status="ELIGIBLE",
            reasons=(),
            education_outcome_status="MEASURED",  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_report_projection_coordinator_writes_gate_and_ref_to_run_ledger() -> None:
    case = _case()
    report = MultimodalEvalRunner().run(
        (case,), {"qwen": lambda item: _result(item, output={"answer": "ok"})}
    )
    scope = RunScope(
        tenant_id="tenant-eval",
        family_id="family-eval",
        subject_ids=("guardian-eval",),
    )
    ledger = InMemoryExperienceRunLedger()
    ledger.create_draft(
        scope=scope,
        run_id="run-eval",
        request_ref="request-eval",
        draft_payload={"status": "DRAFT", "headline": "评估关联"},
        idempotency_key="create-eval",
    )

    receipt = await persist_evaluation_projection(
        ledger,
        scope=scope,
        run_id="run-eval",
        report=report,
        idempotency_key="evaluation-eval",
    )

    assert receipt.status == "recorded"
    snapshot = ledger.replay(scope=scope, run_id="run-eval")
    projection = snapshot.entries[-1].payload
    assert projection["report_ref"] == report.report_ref
    assert projection["release_gate"]["status"] == "ELIGIBLE"
    assert projection["education_outcome_status"] == "NOT_MEASURED"


def test_runner_fails_closed_for_schema_safety_and_provenance() -> None:
    case = _case()

    def adapter(_: GoldCase) -> MultimodalAdapterResult:
        result = _result(
            case,
            output={"wrong": 1},
            labels=("unsafe",),
            safety_passed=False,
        )
        return MultimodalAdapterResult(
            provider_id=result.provider_id,
            model=result.model,
            model_version=result.model_version,
            output=result.output,
            refused=result.refused,
            safety_labels=result.safety_labels,
            safety_passed=result.safety_passed,
            provenance=None,
            latency_ms=result.latency_ms,
            cost_microusd=result.cost_microusd,
        )

    summary = MultimodalEvalRunner().run((case,), {"qwen": adapter}).summaries[0]
    assert summary.passed_cases == 0
    assert summary.schema_pass_rate == 0.0
    assert summary.safety_pass_rate == 0.0
    assert summary.provenance_pass_rate == 0.0
    assert summary.failure_reasons == {
        "provenance_invalid": 1,
        "safety_failed": 1,
        "safety_labels_mismatch": 1,
        "schema_invalid": 1,
    }


def test_expected_refusal_is_a_valid_safe_case_and_raw_media_is_rejected() -> None:
    case = _case(expected_refusal=True)

    def refusing(_: GoldCase) -> MultimodalAdapterResult:
        return _result(case, refused=True, output=None)

    summary = MultimodalEvalRunner().run((case,), {"qwen": refusing}).summaries[0]
    assert summary.passed_cases == 1
    assert summary.schema_pass_rate == 0.0
    assert summary.refusal_accuracy_rate == 1.0
    assert summary.quality_score == 1.0

    with pytest.raises(MultimodalEvalError, match="raw media"):
        GoldCase(
            case_id="bad",
            version="gold.v1",
            fixture_kind="synthetic",
            modalities=("image",),
            locale="zh-CN",
            safety_labels=("safe",),
            expected_schema={"type": "object", "properties": {"media_bytes": {}}},
        )


def test_mixed_gold_versions_are_rejected() -> None:
    first = _case()
    second = GoldCase(
        case_id="case-2",
        version="gold.v2",
        fixture_kind="anonymous",
        modalities=("text",),
        locale="en-US",
        safety_labels=("safe",),
        expected_schema={"type": "object"},
    )
    with pytest.raises(MultimodalEvalError, match="share one version"):
        MultimodalEvalRunner().run((first, second), {"qwen": lambda _: _result(first)})
