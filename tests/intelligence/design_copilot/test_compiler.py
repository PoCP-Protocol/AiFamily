from __future__ import annotations

from datetime import UTC, datetime
from types import MappingProxyType

import pytest

from backend.domains.product_intelligence.domain.entities import (
    EducationProductSpec,
    ProductDefinition,
)
from backend.intelligence.design_copilot.compiler import (
    CompilerCatalog,
    CompilerContext,
    ProductCompiler,
)


def _product() -> ProductDefinition:
    now = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
    return ProductDefinition(
        id="product:21:v1",
        version=1,
        created_at=now,
        updated_at=now,
        created_by="human:pm",
        tenant_scope="tenant-a",
        concept_id="concept:family-growth:v1",
        product_kind="MICRO_CAMP",
        duration_days=21,
        zone="ADVANTAGE",
        primary_contradiction="理解与行动之间存在断点",
        demand_ref="demand:family-growth:v1",
        market_insight_refs=["insight:family-growth:v1"],
        education_spec=EducationProductSpec(
            product_kind="MICRO_CAMP",
            duration_days=21,
            zone="ADVANTAGE",
            primary_contradiction="理解与行动之间存在断点",
            component_ids=["component:understand:v1", "component:action:v1"],
            skill_ids=["skill:compose:v1"],
            success_metric_ids=["metric:action-adoption"],
            guardrail_ids=["guardrail:consent"],
            stop_conditions=["stop:safety"],
            pause_policy="家长可随时暂停",
            human_gate_policy="敏感建议需人工复核",
        ),
    )


def _catalog() -> CompilerCatalog:
    product = "product:21:v1"
    return CompilerCatalog(
        components={
            "component:understand:v1": {"required_skill_ids": ["skill:compose:v1"]},
            "component:action:v1": {"required_skill_ids": ["skill:compose:v1"]},
        },
        skills={"skill:compose:v1": {"status": "ACTIVE"}},
        ai_use_cases={"skill:compose:v1": {"status": "ACTIVE"}},
        resources={
            "component:understand:v1": {"available": True, "capacity": 1},
            "component:action:v1": {"available": True, "capacity": 1},
            "skill:compose:v1": {"available": True, "capacity": 1},
        },
        costs={product: {"estimated_microusd": 100, "max_microusd": 500}},
        evaluations={product: {"refs": ["eval:product-package:v1"], "status": "ACTIVE"}},
        slas={product: {"p95_ms": 500}},
        context_boundaries={product: {"tenant_scope": "tenant-a", "family_scope": "family-only"}},
        safety_policies={product: {"policy_ref": "policy:minor-safe", "consent": "required"}},
        human_gates={product: {"required": True, "actor_type": "HUMAN"}},
        workflows={product: {"stages": ["DRAFT", "PILOT", "RELEASED"], "reachable": True}},
    )


def test_empty_catalog_fails_closed_and_aggregates_all_twelve_checks() -> None:
    report = ProductCompiler().compile(_product())
    assert len(report) == 12
    assert set(report) == set(ProductCompiler.CHECKS)
    assert report.passed is False
    assert any(not result.passed for result in report.values())
    assert report["check_schema"].passed is True
    assert report["check_component"].passed is False


def test_report_to_payload_is_stable_json_projection() -> None:
    report = ProductCompiler().compile(_product())
    payload = report.to_payload()

    assert payload["passed"] is False
    assert list(payload["checks"]) == list(ProductCompiler.CHECKS)
    first = payload["checks"]["check_schema"]
    assert first["check_name"] == "check_schema"
    assert isinstance(first["passed"], bool)
    assert isinstance(first["detail"], str)
    payload["checks"]["check_schema"]["detail"] = "caller mutation"
    assert report["check_schema"].detail != "caller mutation"


def test_complete_catalog_compiles_product_without_side_effects() -> None:
    catalog = _catalog()
    context = CompilerContext(catalog=catalog, max_cost_microusd=500, max_latency_ms=1000)
    compiler = ProductCompiler(context)
    report = compiler.compile(_product())
    assert report.passed is True
    assert len(report.checks) == 12
    assert all(result.passed for result in report.checks.values())
    assert isinstance(catalog.components, MappingProxyType)
    with pytest.raises(TypeError):
        catalog.components["new"] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        catalog.components["component:understand:v1"]["required_skill_ids"] = ()  # type: ignore[index]
    with pytest.raises(AttributeError):
        context.max_latency_ms = 1  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("workflows", "workflow_catalog_missing"),
        ("safety_policies", "safety_policy_missing"),
        ("evaluations", "evaluation_suite_missing"),
    ],
)
def test_missing_catalog_entry_fails_only_its_check(field: str, expected: str) -> None:
    catalog = _catalog()
    # Construct a replacement without mutating the frozen catalog.
    from dataclasses import fields

    kwargs = {item.name: getattr(catalog, item.name) for item in fields(CompilerCatalog)}
    kwargs[field] = {}
    report = ProductCompiler(CompilerCatalog(**kwargs)).compile(_product())
    check_name = {
        "workflows": "check_workflow",
        "safety_policies": "check_safety",
        "evaluations": "check_evaluation",
    }[field]
    assert report[check_name].passed is False
    assert expected in report[check_name].detail
    assert report.passed is False


def test_invalid_workflow_and_limits_are_deterministically_rejected() -> None:
    catalog = _catalog()
    from dataclasses import fields

    kwargs = {item.name: getattr(catalog, item.name) for item in fields(CompilerCatalog)}
    kwargs["workflows"] = {"product:21:v1": {"stages": ["DRAFT", "DRAFT"]}}
    kwargs["costs"] = {"product:21:v1": {"estimated_microusd": 600, "max_microusd": 500}}
    report = ProductCompiler(CompilerContext(catalog=CompilerCatalog(**kwargs))).compile(_product())
    assert report["check_workflow"].passed is False
    assert report["check_cost"].passed is False
