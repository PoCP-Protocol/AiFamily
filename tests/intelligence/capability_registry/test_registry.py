from __future__ import annotations

import pytest

from backend.intelligence.capability_registry import CapabilityOffer, CapabilityRegistry


def offer(ref: str = "practice:bedtime", *, scope: str = "family_growth") -> CapabilityOffer:
    return CapabilityOffer(
        capability_ref=ref,
        version="1.0.0",
        title="家庭实践",
        description="可由家长选择的家庭练习",
        purpose="growth_path_design",
        scope=scope,
        required_capability_keys=("family_practice",),
        need_types=("routine",),
        owner="growth-team",
    )


def test_unpublished_capability_never_enters_path_candidates() -> None:
    registry = CapabilityRegistry((offer(),))
    assert registry.retrieve_published(purpose="growth_path_design", scope="family_growth") == ()
    registry.transition("practice:bedtime", "1.0.0", "REVIEWED")
    registry.transition("practice:bedtime", "1.0.0", "PUBLISHED")
    assert (
        len(registry.retrieve_published(purpose="growth_path_design", scope="family_growth"))
        == 1
    )


def test_retrieval_is_fail_closed_for_purpose_scope_and_required_keys() -> None:
    registry = CapabilityRegistry((offer(),))
    registry.transition("practice:bedtime", "1.0.0", "REVIEWED")
    registry.transition("practice:bedtime", "1.0.0", "PUBLISHED")
    assert registry.retrieve_published(purpose="other", scope="family_growth") == ()
    assert registry.retrieve_published(purpose="growth_path_design", scope="other") == ()
    assert registry.retrieve_published(
        purpose="growth_path_design", scope="family_growth", required_keys=("expert",)
    ) == ()
    assert registry.retrieve_published(
        purpose="growth_path_design", scope="family_growth", need_type="sleep"
    ) == ()


def test_invalid_lifecycle_transition_is_rejected() -> None:
    registry = CapabilityRegistry((offer(),))
    with pytest.raises(ValueError, match="INVALID_CAPABILITY_TRANSITION"):
        registry.transition("practice:bedtime", "1.0.0", "PUBLISHED")
