"""Evaluation-only runner for the vertical AGI red-team scenarios."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def field_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, tuple[Any, Any]]:
    keys = set(before) | set(after)
    return {
        key: (before.get(key), after.get(key))
        for key in sorted(keys)
        if before.get(key) != after.get(key)
    }


def assert_scenario(scenario: dict[str, Any]) -> None:
    assert scenario["family_need_id"]
    assert scenario["run_id"]
    assert scenario["context_snapshot_ref"]
    assert scenario["knowledge"]["status"] == "PUBLISHED"
    assert scenario["knowledge"]["version"]
    assert scenario["draft"]["status"] in {
        "DRAFT",
        "PERSPECTIVE",
        "RECOMMENDATION",
        "ACTION_PROPOSAL",
    }
    if scenario["scenario_id"] == "same_need_feedback_delta":
        assert scenario["first_draft"]["family_need_id"] == scenario["draft"]["family_need_id"]
        assert field_diff(scenario["first_draft"], scenario["draft"])
        assert scenario["guardian_feedback_ref"] in scenario["draft"]["provenance"]["source_ref"]
    elif scenario["scenario_id"] == "fixed_knowledge_context_delta":
        assert (
            scenario["knowledge"]["digest"]
            == scenario["first_draft"]["provenance"]["knowledge_digest"]
        )
        assert field_diff(scenario["first_draft"], scenario["draft"])
    elif scenario["scenario_id"] == "decision_restart_persistence":
        assert scenario["decision"]["state"] in {"ACCEPT", "REJECT", "EDIT", "DEFER"}
        assert (
            scenario["decision"]["decision_ref"]
            == scenario["draft"]["provenance"]["decision_ref"]
        )
    elif scenario["scenario_id"] == "cross_family_scope_isolation":
        assert scenario["cross_scope"]["status"] in {403, 404}
        assert scenario["cross_scope"]["provider_invocations"] == 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args()
    data = json.loads(args.fixture.read_text(encoding="utf-8"))
    assert data.get("evaluation_only") is True
    for scenario in data["scenarios"]:
        assert_scenario(scenario)
    print(
        json.dumps(
            {
                "scenarios": len(data["scenarios"]),
                "result": "PASS",
                "evaluation_only": True,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
