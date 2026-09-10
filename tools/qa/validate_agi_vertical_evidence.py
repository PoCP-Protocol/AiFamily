"""Validate a captured AGI vertical evaluation evidence manifest.

This validates evidence completeness only. It never executes business code and
never upgrades a scenario to PASS when its required artifact is absent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_SCENARIOS = {
    "V-01",
    "V-02",
    "V-03",
    "V-04",
    "V-05",
    "V-06",
    "V-07",
    "V-08",
    "V-09",
    "V-10",
}
FORBIDDEN_EVIDENCE = {"fake", "in_memory", "sqlite", "skipped", "fixture_only", "same_process_only"}
REQUIRED_ARTIFACT_KINDS = {"git_ref", "http", "postgres_sql", "browser", "process_restart"}
REQUIRED_ARTIFACT_FIELDS = {"kind", "ref", "command"}


def validate(manifest: dict) -> list[str]:
    errors: list[str] = []
    if not manifest.get("approved_ref"):
        errors.append("approved_ref is required")
    if manifest.get("status") == "PASS" and manifest.get("approved_ref") != manifest.get("git_ref"):
        errors.append("approved_ref must equal git_ref")
    if manifest.get("status") == "PASS" and manifest.get("database_kind") != "fresh_postgresql":
        errors.append("PASS requires fresh_postgresql")
    artifacts = manifest.get("artifacts", [])
    kinds = {item.get("kind") for item in artifacts if isinstance(item, dict)}
    artifact_refs = {
        item.get("ref")
        for item in artifacts
        if isinstance(item, dict) and isinstance(item.get("ref"), str)
    }
    errors.extend(f"missing artifact kind: {kind}" for kind in REQUIRED_ARTIFACT_KINDS - kinds)
    for item in artifacts:
        if not isinstance(item, dict):
            errors.append("artifact must be an object")
            continue
        errors.extend(
            f"artifact {item.get('kind', '<unknown>')} missing field: {field}"
            for field in REQUIRED_ARTIFACT_FIELDS
            if not isinstance(item.get(field), str) or not item[field].strip()
        )
        text = json.dumps(item, ensure_ascii=False).lower()
        errors.extend(
            f"forbidden substitute in artifact: {flag}"
            for flag in FORBIDDEN_EVIDENCE
            if flag in text
        )
    scenarios = {item.get("scenario_id"): item for item in manifest.get("scenarios", [])}
    errors.extend(
        f"missing scenario: {scenario_id}"
        for scenario_id in REQUIRED_SCENARIOS - scenarios.keys()
    )
    if manifest.get("status") == "PASS":
        errors.extend(
            f"scenario not PASS: {scenario_id}"
            for scenario_id, scenario in scenarios.items()
            if scenario.get("status") != "PASS"
        )
        for scenario_id in REQUIRED_SCENARIOS:
            scenario = scenarios.get(scenario_id)
            if scenario is None:
                continue
            refs = scenario.get("artifact_refs")
            if not isinstance(refs, list) or not refs or any(
                not isinstance(ref, str) or not ref.strip() for ref in refs
            ):
                errors.append(f"scenario missing artifact_refs: {scenario_id}")
            else:
                errors.extend(
                    f"scenario references unknown artifact: {scenario_id}:{ref}"
                    for ref in refs
                    if ref not in artifact_refs
                )
    return sorted(set(errors))


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: uv run python tools/qa/validate_agi_vertical_evidence.py evidence.json")
        return 2
    manifest = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    errors = validate(manifest)
    if errors:
        print("FAIL: evidence manifest is incomplete")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PASS: evidence manifest is structurally complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
