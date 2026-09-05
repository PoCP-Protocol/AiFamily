"""Guard the business architecture's process hierarchy and traceability."""

from __future__ import annotations

import re
from pathlib import Path

ARCHITECTURE = Path("docs/02_business/BUSINESS_ARCHITECTURE.md")


def test_business_architecture_declares_l0_to_l5_process_layers(repo_root: Path) -> None:
    text = (repo_root / ARCHITECTURE).read_text(encoding="utf-8")
    section = text.split("## 7. 分级流程架构", 1)[1].split("## 8. 与现有基础文档的关系", 1)[0]

    for level in ("L0", "L1", "L2", "L3", "L4", "L5"):
        assert level in section, f"process architecture is missing {level}"

    assert {f"VS-{index:02d}" for index in range(1, 6)} <= set(re.findall(r"VS-\d{2}", section))
    assert {f"P{index:02d}" for index in range(1, 7)} <= set(re.findall(r"P\d{2}", section))


def test_process_architecture_covers_all_scenarios_and_operations(repo_root: Path) -> None:
    text = (repo_root / ARCHITECTURE).read_text(encoding="utf-8")
    section = text.split("## 7. 分级流程架构", 1)[1].split("## 8. 与现有基础文档的关系", 1)[0]

    expected_scenarios = {f"S{index:02d}" for index in range(1, 25)}
    expected_operations = {f"O{index:02d}" for index in range(1, 15)}
    assert expected_scenarios <= set(re.findall(r"S\d{2}", section))
    assert expected_operations <= set(re.findall(r"O\d{2}", section))
    assert "BUSINESS_SCENARIO_CLOSURE_CATALOG.md" in section
    assert "BUSINESS_SCENARIO_DATA_ARCHITECTURE.md" in section
