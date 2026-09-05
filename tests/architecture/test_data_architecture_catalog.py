"""Guard that data architecture stays aligned with the business/operations catalog."""

from __future__ import annotations

import re
from pathlib import Path

CATALOG = Path("docs/07_data/BUSINESS_SCENARIO_DATA_ARCHITECTURE.md")


def _section(text: str, heading: str, next_heading: str) -> str:
    return text.split(heading, 1)[1].split(next_heading, 1)[0]


def test_data_map_covers_all_business_and_operations_scenarios(repo_root: Path) -> None:
    text = (repo_root / CATALOG).read_text(encoding="utf-8")

    business = _section(text, "## 4. 24 个业务场景的数据架构映射", "## 5.")
    operations = _section(text, "## 5. 14 个平台运营场景的数据架构映射", "## 6.")

    business_ids = set(re.findall(r"^\| (S(?:0[1-9]|1[0-9]|2[0-4])) ", business, re.MULTILINE))
    operation_ids = set(re.findall(r"^\| (O(?:0[1-9]|1[0-4])) ", operations, re.MULTILINE))
    assert business_ids == {f"S{index:02d}" for index in range(1, 25)}
    assert operation_ids == {f"O{index:02d}" for index in range(1, 15)}


def test_data_map_covers_all_baseline_ui_projections(repo_root: Path) -> None:
    text = (repo_root / CATALOG).read_text(encoding="utf-8")
    ui_section = _section(text, "## 8. UI 读模型匹配（34 个基线屏幕）", "## 9.")
    missing = [f"UI-{index:02d}" for index in range(1, 35) if f"UI-{index:02d}" not in ui_section]
    assert not missing, f"data architecture UI projection map is missing: {missing}"


def test_event_envelope_contains_boundary_and_provenance_fields(repo_root: Path) -> None:
    text = (repo_root / CATALOG).read_text(encoding="utf-8")
    envelope = _section(text, "### 6.1 事件信封", "### 6.2")
    required = {
        "event_id",
        "aggregate_type/id",
        "tenant_id/family_id",
        "actor_id/actor_type",
        "purpose",
        "consent_version",
        "idempotency_key",
        "provenance",
        "environment",
    }
    missing = [field for field in required if field not in envelope]
    assert not missing, f"event envelope is missing: {missing}"


def test_data_design_accounts_for_existing_wip_surfaces(repo_root: Path) -> None:
    text = (repo_root / CATALOG).read_text(encoding="utf-8")
    wip_section = _section(text, "## 3A. 现有 WIP 数据面纳入总设计", "## 4.")
    required_surfaces = {
        "family_assessment_sessions",
        "family_journey_plans",
        "family_service_providers",
        "family_order_intents",
        "family_membership_plans",
        "family_loyalty_points_ledger",
        "product_intelligence_growth_hypotheses",
        "platform_audit_events",
        "family_activity_catalog",
        "alembic upgrade head",
    }
    missing = [surface for surface in required_surfaces if surface not in wip_section]
    assert not missing, f"WIP data surface is not covered by the total design: {missing}"
