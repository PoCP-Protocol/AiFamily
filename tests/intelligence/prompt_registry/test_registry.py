from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.prompt_registry import (
    PromptAlreadyRegistered,
    PromptBindingError,
    PromptBundle,
    PromptNotFound,
    PromptRegistry,
)


def _prompt(*, status: str = "PUBLISHED", effective_at: datetime | None = None) -> PromptBundle:
    return PromptBundle(
        prompt_ref="assessment.interpretation",
        version="v1",
        use_case="assessment_interpretation",
        agent_id="parent_advisor",
        template="Explain the evidence without diagnosing.",
        system_policy_ref="safety.parenting.v1",
        knowledge_refs=("knowledge.assessment.v1",),
        input_contract_ref="assessment.input.v1",
        output_schema_ref="growth_perspective_v1",
        safety_policy_version="safety.v1",
        locale="zh-CN",
        author="growth-team",
        reviewer="reviewer" if status == "PUBLISHED" else None,
        status=status,  # type: ignore[arg-type]
        effective_at=effective_at if effective_at is not None else datetime.now(UTC),
        change_reason="reviewed" if status in {"REVIEW", "RETIRED"} else "",
    )


def test_prompt_resolution_is_bound_to_use_case_agent_and_effective_window() -> None:
    now = datetime.now(UTC)
    registry = PromptRegistry(bundles=(_prompt(effective_at=now - timedelta(minutes=1)),))
    assert registry.resolve(
        use_case="assessment_interpretation", agent_id="parent_advisor"
    ).prompt_text.startswith("Explain")
    assert registry.find(use_case="assessment_interpretation", agent_id="other") is None
    assert registry.find(
        use_case="assessment_interpretation",
        agent_id="parent_advisor",
        at=now - timedelta(days=1),
    ) is None


def test_prompt_lookup_fails_closed_and_duplicate_versions_are_rejected() -> None:
    registry = PromptRegistry(bundles=(_prompt(),))
    with pytest.raises(PromptNotFound, match="PROMPT_NOT_FOUND"):
        registry.resolve(use_case="other", agent_id="parent_advisor")
    with pytest.raises(PromptAlreadyRegistered):
        registry.register(_prompt())
    with pytest.raises(PromptBindingError):
        registry.resolve(use_case="", agent_id="parent_advisor")


def test_prompt_lifecycle_creates_new_version_and_keeps_original_immutable() -> None:
    registry = PromptRegistry(bundles=(_prompt(status="REVIEW"),))
    published = registry.transition(
        "assessment.interpretation",
        "v1",
        "PUBLISHED",
        reviewer="reviewer",
        effective_at=datetime.now(UTC),
        change_reason="approved",
    )
    assert published.version != "v1"
    assert published.status == "PUBLISHED"
    assert registry.get("assessment.interpretation", "v1").status == "REVIEW"  # type: ignore[union-attr]

