"""Guard the business/operations scenario inventory from regressing to a short happy path."""

from __future__ import annotations

import re
from pathlib import Path

CATALOG = Path("docs/02_business/BUSINESS_SCENARIO_CLOSURE_CATALOG.md")


def test_catalog_covers_all_business_and_platform_operations(repo_root: Path) -> None:
    text = (repo_root / CATALOG).read_text(encoding="utf-8")

    business_rows = re.findall(r"^\| S(?:0[1-9]|1[0-9]|2[0-4]) \|", text, flags=re.MULTILINE)
    assert len(business_rows) == 24, "business scenario inventory must contain S01-S24 exactly"

    operations_rows = re.findall(r"^\| O(?:0[1-9]|1[0-4]) \|", text, flags=re.MULTILINE)
    assert len(operations_rows) == 14, "platform operations inventory must contain O01-O14 exactly"


def test_catalog_maps_every_baseline_ui(repo_root: Path) -> None:
    text = (repo_root / CATALOG).read_text(encoding="utf-8")
    coverage = text.split("## 4. 34 个 UI 覆盖矩阵", 1)[1].split("## 5. 场景节点契约", 1)[0]

    missing = [f"UI-{index:02d}" for index in range(1, 35) if f"UI-{index:02d}" not in coverage]
    assert not missing, f"34 UI coverage matrix is missing: {missing}"


def test_each_platform_operation_has_node_contract(repo_root: Path) -> None:
    text = (repo_root / CATALOG).read_text(encoding="utf-8")
    missing = []
    for index in range(1, 15):
        operation = f"O{index:02d}"
        operation_block = ""
        if f"### {operation} " in text:
            operation_block = text.split(f"### {operation} ", 1)[1].split("### ", 1)[0]
        has_header = "| 节点 | 输入 | 活动 | 输出 | 业务规则 |" in operation_block
        has_nodes = all(f"{operation}-N0{node}" in text for node in range(1, 5))
        if f"### {operation} " not in text or not has_header or not has_nodes:
            missing.append(operation)
    assert not missing, (
        "platform operations without node-level input/activity/output/rule table: "
        f"{missing}"
    )
