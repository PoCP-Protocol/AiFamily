from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.intelligence.model_gateway.contracts import AiProvenance, ModelDraft
from backend.intelligence.safety import SafetyContext, SafetyRuntime


def _draft(output: dict[str, object], *, mutable: bool = False) -> ModelDraft:
    draft = ModelDraft(
        output=output,
        provenance=AiProvenance(
            provider_id="fake",
            model="fake-model",
            model_version="v1",
            prompt_version="p1",
            schema_version="s1",
            context_snapshot_ref="snapshot-1",
            latency_ms=1,
            data_class="SYNTHETIC",
            use_case="family_growth_support",
            generated_at=datetime.now(UTC),
        ),
    )
    if not mutable:
        return draft
    return ModelDraft(
        output=draft.output,
        status="DRAFT",
        may_mutate_business_state=True,  # type: ignore[call-arg]
        provenance=draft.provenance,
    )


def test_low_risk_input_is_allowed_without_human_gate() -> None:
    decision = SafetyRuntime().evaluate_input(
        SafetyContext(use_case="family_assistant_conversation"), {"prompt": "你好"}
    )
    assert decision.status == "ALLOW"
    assert decision.requires_human_gate is False


def test_high_impact_input_requires_human_gate() -> None:
    decision = SafetyRuntime().evaluate_input(
        SafetyContext(use_case="growth_plan_draft"), {"goal": "亲子共读"}
    )
    assert decision.status == "REVIEW"
    assert decision.requires_human_gate is True


def test_prohibited_score_field_is_blocked_before_model() -> None:
    decision = SafetyRuntime().evaluate_input(
        SafetyContext(use_case="family_assistant_conversation"),
        {"family_score": 99},
    )
    assert decision.status == "BLOCK"
    assert any(reason.startswith("forbidden_field:") for reason in decision.reasons)


def test_minor_output_is_reviewed_even_for_low_impact_use_case() -> None:
    decision = SafetyRuntime().evaluate_output(
        SafetyContext(use_case="family_assistant_conversation", subject_is_minor=True),
        _draft({"message": "试试十分钟共读"}),
    )
    assert decision.status == "REVIEW"
    assert decision.risk_level == "MEDIUM"


def test_mutating_or_prohibited_output_is_blocked() -> None:
    runtime = SafetyRuntime()
    assert runtime.evaluate_output(
        SafetyContext(use_case="family_assistant_conversation"),
        _draft({"message": "ok", "ranking": ["family-a"]}),
    ).status == "BLOCK"
    with pytest.raises(TypeError):
        _draft({"message": "unsafe"}, mutable=True)
