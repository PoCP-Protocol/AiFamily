from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "docs/07_data/DATA_OBJECT_TABLE_RELATIONSHIP_CATALOG.md"
MASTER_BUSINESS = ROOT / "docs/07_data/MASTER_AND_BUSINESS_DATA_DECOMPOSITION.md"
SCENARIO_DATA = ROOT / "docs/07_data/BUSINESS_SCENARIO_DATA_ARCHITECTURE.md"


def test_object_table_relationship_catalog_has_required_layers() -> None:
    text = CATALOG.read_text(encoding="utf-8")

    for heading in (
        "## 2. 数据对象 → 数据表目录",
        "## 3. 数据关系目录",
        "## 4. 跨域关系与物理约束",
        "## 6. 表级验收清单",
    ):
        assert heading in text

    for token in (
        "主键",
        "关键外键/唯一关系",
        "基数",
        "on_delete",
        "BASELINE",
        "WIP_ORM",
        "TARGET_REQUIRED",
    ):
        assert token in text


def test_catalog_covers_core_master_and_business_tables() -> None:
    text = CATALOG.read_text(encoding="utf-8")
    required_tables = (
        "families",
        "persons",
        "consents",
        "family_assessment_tools",
        "family_assessment_sessions",
        "family_journey_plans",
        "growth_actions",
        "service_cases",
        "service_tasks",
        "family_product_offerings",
        "family_order_intents",
        "family_entitlements",
        "family_membership_plans",
        "family_loyalty_points_ledger",
        "platform_audit_events",
        "outbox_events",
        "memory_candidates",
        "child_memory_items",
        "guardian_memory_items",
        "family_relationship_memory_items",
        "memory_retrievals",
        "memory_deletion_proofs",
    )
    for table in required_tables:
        assert f"`{table}`" in text


def test_master_business_decomposition_is_referenced_by_scenario_data_truth() -> None:
    scenario_text = SCENARIO_DATA.read_text(encoding="utf-8")
    master_business_text = MASTER_BUSINESS.read_text(encoding="utf-8")

    assert "DATA_OBJECT_TABLE_RELATIONSHIP_CATALOG.md" in scenario_text
    for token in ("主数据 Master", "业务数据 Business", "主数据与策略版本", "B 业务数据"):
        assert token in master_business_text


def test_relationship_catalog_keeps_high_risk_boundaries_explicit() -> None:
    text = CATALOG.read_text(encoding="utf-8")

    for token in (
        "AI ModelDraft → Family/Outcome/GrowthState",
        "`balance`/`score`/`ranking`",
        "| PointsAccount | PointsLedgerEntry |",
        "ServiceCase | ServiceTask",
        "AllocationRun | ContributionAllocation",
        "MemoryCandidate | MemoryConsent",
        "Memory | MediaTranscript/Embedding/Cache",
    ):
        assert token in text
