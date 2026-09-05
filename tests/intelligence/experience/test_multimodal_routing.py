from __future__ import annotations

from dataclasses import replace

import pytest

from backend.intelligence.experience.multimodal_routing import (
    DEFAULT_MULTIMODAL_CANDIDATES,
    DOUBAO_MULTIMODAL_CANDIDATE,
    QWEN_MULTIMODAL_CANDIDATE,
    MultimodalRouteError,
    MultimodalRouter,
    MultimodalRouteRequest,
)


def _approved(profile):
    return replace(
        profile,
        status="INTERNAL_APPROVED",
        approved_environments=("test",),
        approved_data_classes=frozenset({"SYNTHETIC", "OPERATIONAL_TEXT"}),
        sub_delegates=False,
    )


def _request(**kwargs):
    values = {
        "use_case": "family-image-summary",
        "data_class": "SYNTHETIC",
        "modalities": ("TEXT", "IMAGE"),
        "environment": "test",
        "estimated_input_tokens": 1000,
    }
    values.update(kwargs)
    return MultimodalRouteRequest(**values)


def test_candidate_profiles_declare_qwen_and_doubao_without_being_callable() -> None:
    assert {profile.vendor for profile in DEFAULT_MULTIMODAL_CANDIDATES} == {"qwen", "doubao"}
    assert QWEN_MULTIMODAL_CANDIDATE.status == "TECHNICALLY_VALIDATED"
    assert DOUBAO_MULTIMODAL_CANDIDATE.status == "TECHNICALLY_VALIDATED"
    assert {"IMAGE", "AUDIO", "VIDEO"}.issubset(QWEN_MULTIMODAL_CANDIDATE.modalities)


def test_router_selects_by_cost_and_returns_explainable_provenance() -> None:
    router = MultimodalRouter(
        (_approved(QWEN_MULTIMODAL_CANDIDATE), _approved(DOUBAO_MULTIMODAL_CANDIDATE))
    )
    decision = router.route(_request(strategy="cost"))

    assert decision.selected.vendor == "doubao"
    assert decision.fallback_provider_ids == ("qwen-multimodal-candidate",)
    assert decision.provenance_input.data_class == "SYNTHETIC"
    assert decision.provenance_input.modalities == ("TEXT", "IMAGE")
    assert decision.provenance_input.estimated_cost_microusd == 60


def test_router_fails_closed_for_unapproved_profiles_and_minor_data() -> None:
    router = MultimodalRouter(DEFAULT_MULTIMODAL_CANDIDATES)
    with pytest.raises(MultimodalRouteError) as candidate_error:
        router.route(_request())
    assert candidate_error.value.reason == "NO_CAPABLE_PROVIDER"

    approved = replace(
        _approved(QWEN_MULTIMODAL_CANDIDATE),
        approved_data_classes=frozenset({"MINOR_PERSONAL_DATA"}),
        sub_delegates=None,
    )
    with pytest.raises(MultimodalRouteError) as minor_error:
        MultimodalRouter((approved,)).route(_request(data_class="MINOR_PERSONAL_DATA"))
    assert minor_error.value.reason == "NO_CAPABLE_PROVIDER"


def test_router_applies_latency_and_cost_budgets_before_sorting() -> None:
    router = MultimodalRouter(
        (_approved(QWEN_MULTIMODAL_CANDIDATE), _approved(DOUBAO_MULTIMODAL_CANDIDATE))
    )
    decision = router.route(_request(strategy="latency", max_latency_ms=800))
    assert decision.selected.vendor == "doubao"

    with pytest.raises(MultimodalRouteError):
        router.route(_request(max_cost_microusd=10))


def test_router_counts_media_items_instead_of_modality_categories() -> None:
    profile = replace(_approved(QWEN_MULTIMODAL_CANDIDATE), max_media_items=2)
    router = MultimodalRouter((profile,))

    with pytest.raises(MultimodalRouteError, match="no explicitly approved provider"):
        router.route(_request(media_item_count=3))
