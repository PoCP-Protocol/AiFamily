from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "docs/11_delivery/APPLICATION_IMPLEMENTATION_LEDGER.md"


def test_application_implementation_ledger_exists_and_is_explicit() -> None:
    text = LEDGER.read_text(encoding="utf-8")
    for phrase in (
        "A3-A6 应用实现台账",
        "Handler",
        "权威对象/表",
        "事件/审计",
        "测试证据",
        "三环境功能等价闸门",
    ):
        assert phrase in text


def test_ledger_covers_all_business_and_operations_flows() -> None:
    text = LEDGER.read_text(encoding="utf-8")
    for prefix, count in (("S", 24), ("O", 14)):
        for number in range(1, count + 1):
            assert f"{prefix}{number:02d}" in text


def test_ledger_covers_all_mobile_ui_ids_without_inventing_result_scenario() -> None:
    text = LEDGER.read_text(encoding="utf-8")
    for number in range(1, 35):
        assert f"UI-{number:02d}" in text
    assert "UI-02-result" in text
    assert "不另造场景" in text


def test_s04_to_s07_have_node_level_evidence_and_gaps() -> None:
    text = LEDGER.read_text(encoding="utf-8")
    for node in (
        "S04-N01",
        "S04-N02",
        "S04-N03",
        "S04-N04",
        "S04-N05",
        "S05-N01",
        "S05-N02",
        "S05-N03",
        "S05-N04",
        "S06-N01",
        "S06-N02",
        "S06-N03",
        "S06-N04",
        "S06-N05",
        "S07-N01",
        "S07-N02",
        "S07-N03",
        "S07-N04",
        "S07-N05",
    ):
        assert node in text
    assert "S04 测评执行、提交与证据冻结 | IMPLEMENTED" in text
    assert "S05 假设解读、家庭确认与成长入营 | PARTIAL" in text
    assert "S06 90 天计划生成、确认与阶段复盘 | PARTIAL" in text
    assert "S07 21 天行动、今日任务与过程回读 | NOT_IMPLEMENTED" in text


def test_ledger_records_environment_parity_as_a_gate() -> None:
    text = LEDGER.read_text(encoding="utf-8")
    for phrase in (
        "dev 会安装 assessment/service/commercial fake wiring",
        "生产默认依赖仍有 fail-closed stub",
        "只替换数据工厂和外部适配器",
        "不能以“测试环境可点击”作为生产就绪证明",
    ):
        assert phrase in text
