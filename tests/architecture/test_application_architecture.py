from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPLICATION = ROOT / "docs/06_platform/APPLICATION_ARCHITECTURE.md"
BUSINESS = ROOT / "docs/02_business/BUSINESS_ARCHITECTURE.md"
DATA = ROOT / "docs/07_data/BUSINESS_SCENARIO_DATA_ARCHITECTURE.md"
OBJECT_DATA = ROOT / "docs/07_data/DATA_OBJECT_TABLE_RELATIONSHIP_CATALOG.md"


def test_application_architecture_defines_hierarchical_layers() -> None:
    text = APPLICATION.read_text(encoding="utf-8")
    for level in ("A0", "A1", "A2", "A3", "A4", "A5", "A6"):
        assert level in text
    for section in (
        "## 3. A0 应用系统与 A1 渠道/进程",
        "## 4. A2 应用模块与责任边界",
        "## 5. A3 用例/应用服务与 39 个流程绑定",
        "## 6. A4 工作流与编排模式",
        "## 7. A5 接口与 34 UI 对齐",
        "## 8. A6 运行组件与代码组织",
    ):
        assert section in text


def test_application_architecture_covers_all_scenarios_and_ui() -> None:
    text = APPLICATION.read_text(encoding="utf-8")
    for prefix, count in (("S", 24), ("O", 14), ("UI-", 34)):
        for number in range(1, count + 1):
            identifier = f"{prefix}{number:02d}" if prefix != "UI-" else f"UI-{number:02d}"
            assert identifier in text, identifier
    assert "UI-02-result" in text


def test_application_architecture_references_business_and_data_truth() -> None:
    text = APPLICATION.read_text(encoding="utf-8")
    for reference in (
        "BUSINESS_ARCHITECTURE.md",
        "BUSINESS_SCENARIO_CLOSURE_CATALOG.md",
        "DATA_OBJECT_TABLE_RELATIONSHIP_CATALOG.md",
        "MASTER_AND_BUSINESS_DATA_DECOMPOSITION.md",
        "tenant_id",
        "consent",
        "idempotency",
        "Outbox",
    ):
        assert reference in text

    assert "APPLICATION_ARCHITECTURE.md" in BUSINESS.read_text(encoding="utf-8")
    assert "APPLICATION_ARCHITECTURE.md" in DATA.read_text(encoding="utf-8")
    assert "Query Port" in OBJECT_DATA.read_text(encoding="utf-8")


def test_application_architecture_preserves_environment_parity_and_boundaries() -> None:
    text = APPLICATION.read_text(encoding="utf-8")
    for phrase in (
        "三环境功能等价",
        "Projection → Fact",
        "AI Draft → Canonical Fact",
        "跨域直写",
        "S16 只归属 P04/VS-03",
    ):
        assert phrase in text
