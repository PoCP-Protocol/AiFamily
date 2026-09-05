from backend.intelligence.experience.gold_set import build_default_gold_set
from backend.intelligence.experience.multimodal_eval import MultimodalAdapterResult
from backend.intelligence.experience.slice_runner import MultimodalSliceRunner
from backend.intelligence.model_gateway.contracts import AiProvenance


def test_slice_runner_produces_deterministic_modality_locale_and_age_slices() -> None:
    cases = build_default_gold_set()

    def adapter(case):
        return MultimodalAdapterResult(
            provider_id="provider-a",
            model="model-a",
            model_version="v1",
            output={"summary": "ok", "next_step": "reflect"},
            refused=case.expected_refusal,
            refusal_reason="policy" if case.expected_refusal else None,
            safety_labels=case.safety_labels,
            safety_passed=True,
            provenance=AiProvenance(
                provider_id="provider-a",
                model="model-a",
                model_version="v1",
                prompt_version="prompt.v1",
                schema_version=case.version,
                context_snapshot_ref="ctx:synthetic",
                latency_ms=10,
                data_class="SYNTHETIC",
                use_case="offline-eval",
            ),
            latency_ms=10,
            cost_microusd=1,
        )

    first = MultimodalSliceRunner().run(cases, {"provider-a": adapter})
    second = MultimodalSliceRunner().run(cases, {"provider-a": adapter})
    assert [(item.dimension, item.value, len(item.case_ids)) for item in first] == [
        ("modality", "audio", 60),
        ("modality", "image", 60),
        ("modality", "text", 80),
        ("modality", "video", 40),
        ("locale", "en-US", 100),
        ("locale", "zh-CN", 100),
        ("age_band", "ADOLESCENT", 50),
        ("age_band", "EARLY_CHILDHOOD", 50),
        ("age_band", "GUARDIAN", 50),
        ("age_band", "SCHOOL_AGE", 50),
    ]
    assert [item.case_ids for item in first] == [item.case_ids for item in second]
    assert all(item.report.total_cases == len(item.case_ids) for item in first)
