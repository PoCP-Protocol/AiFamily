from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ..application import commands
from ..application.context import ActorContext
from ..domain.entities import (
    EducationProductSpec,
    ProductComponent,
    ProductConcept,
    ProductDefinition,
)
from ..domain.errors import ProductIntelligenceValidationError
from ..infrastructure.fake_repository import FakeProductIntelligenceRepository


def _common() -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "id": "component-1",
        "created_at": now,
        "updated_at": now,
        "created_by": "human:product-owner",
        "tenant_scope": "tenant-a",
    }


def _spec(*, kind: str = "MICRO_CAMP", duration: int = 21) -> EducationProductSpec:
    return EducationProductSpec(
        product_kind=kind,
        duration_days=duration,
        zone="ADVANTAGE",
        primary_contradiction="家庭理解与行动之间存在断点",
        component_ids=["understand-v1", "action-v1"],
        skill_ids=["compose_growth_product"],
        success_metric_ids=["action_adoption"],
        guardrail_ids=["no_child_commercial_targeting"],
        stop_conditions=["safety_guardrail_breached"],
        pause_policy="家长可随时暂停并恢复",
        human_gate_policy="敏感建议先由人工复核",
    )


def test_education_spec_models_21_day_product() -> None:
    spec = _spec()
    assert spec.duration_days == 21
    assert spec.zone == "ADVANTAGE"


def test_education_spec_rejects_wrong_duration() -> None:
    with pytest.raises(ProductIntelligenceValidationError, match="micro_camp_duration"):
        _spec(duration=90)


def test_product_definition_rejects_zone_mismatch() -> None:
    common = _common()
    common["id"] = "definition-1"
    with pytest.raises(ProductIntelligenceValidationError, match="zone_mismatch"):
        ProductDefinition(
            **common,
            concept_id="concept-1",
            component_ids=["understand-v1", "action-v1"],
            product_kind="MICRO_CAMP",
            duration_days=21,
            zone="HOMOGENEOUS",
            demand_ref="family-need-1",
            market_insight_refs=["market-insight-1"],
            education_spec=_spec(),
        )


def test_component_library_preserves_three_zone_and_contract_refs() -> None:
    component = ProductComponent(
        **_common(),
        component_type="ACTION",
        title="今日行动",
        zone="ADVANTAGE",
        purpose="把理解转成可暂停的小行动",
        input_refs=["growth_hypothesis"],
        output_refs=["action_candidate"],
        required_skill_ids=["explain_growth_hypothesis"],
        evidence_refs=["evidence-action-adoption"],
        metric_ids=["action_adoption"],
        owner_ref="journey",
    )
    assert component.zone == "ADVANTAGE"
    assert component.required_skill_ids == ["explain_growth_hypothesis"]


def test_education_product_requires_demand_and_market_insight_refs() -> None:
    common = _common()
    common["id"] = "definition-2"
    with pytest.raises(ProductIntelligenceValidationError, match="demand_ref_required"):
        ProductDefinition(
            **common,
            concept_id="concept-1",
            component_ids=["understand-v1", "action-v1"],
            product_kind="MICRO_CAMP",
            duration_days=21,
            zone="ADVANTAGE",
            market_insight_refs=["market-insight-1"],
            education_spec=_spec(),
        )


@pytest.mark.asyncio
async def test_product_factory_creates_draft_from_demand_and_market_evidence() -> None:
    repo = FakeProductIntelligenceRepository()
    now = datetime.now(UTC)
    await repo.save_product_concept(
        ProductConcept(
            id="concept-1",
            created_at=now,
            updated_at=now,
            created_by="human:product-owner",
            tenant_scope="tenant-a",
            strategy_id="strategy-1",
            title="家庭行动支持",
        )
    )
    definition = await commands.create_education_product_definition(
        repo,
        ActorContext(
            actor_id="ai:product-factory",
            actor_type="AI",
            tenant_scope="tenant-a",
        ),
        concept_id="concept-1",
        product_kind="MICRO_CAMP",
        duration_days=21,
        zone="ADVANTAGE",
        primary_contradiction="理解与行动之间存在断点",
        demand_ref="family-need-1",
        market_insight_refs=["market-insight-1"],
        component_ids=["understand-v1", "action-v1"],
        skill_ids=["compose_growth_product"],
        success_metric_ids=["action_adoption"],
        guardrail_ids=["no_child_commercial_targeting"],
        stop_conditions=["safety_guardrail_breached"],
        pause_policy="家长可以随时暂停",
        human_gate_policy="敏感建议需人工复核",
        model_ref="gateway:test",
        prompt_use_case_version="product.compose.v1",
        confidence=0.8,
    )
    assert definition.status == "DRAFT"
    assert definition.demand_ref == "family-need-1"
    assert definition.generated_by == "ai:product-factory"
