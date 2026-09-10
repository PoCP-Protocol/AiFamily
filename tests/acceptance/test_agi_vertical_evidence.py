from __future__ import annotations

from tools.qa.validate_agi_vertical_evidence import validate


def test_empty_manifest_cannot_pass() -> None:
    errors = validate({"status": "PASS"})

    assert "approved_ref is required" in errors
    assert any(error.startswith("missing scenario:") for error in errors)


def test_structural_manifest_requires_real_artifact_kinds() -> None:
    manifest = {
        "status": "BLOCKED",
        "approved_ref": "abc",
        "git_ref": "abc",
        "database_kind": "fresh_postgresql",
        "artifacts": [{"kind": "git_ref"}],
        "scenarios": [],
    }

    errors = validate(manifest)

    assert "missing artifact kind: http" in errors
    assert "missing artifact kind: postgres_sql" in errors
    assert "missing artifact kind: browser" in errors
    assert "missing artifact kind: process_restart" in errors


def test_pass_manifest_requires_traceable_artifacts_and_scenario_refs() -> None:
    manifest = {
        "status": "PASS",
        "approved_ref": "abc",
        "git_ref": "abc",
        "database_kind": "fresh_postgresql",
        "artifacts": [
            {"kind": kind, "ref": f"artifact:{kind}", "command": "pytest"}
            for kind in {
                "git_ref",
                "http",
                "postgres_sql",
                "browser",
                "process_restart",
            }
        ],
        "scenarios": [
            {"scenario_id": scenario_id, "status": "PASS"}
            for scenario_id in sorted(
                {f"V-{index:02d}" for index in range(1, 11)}
            )
        ],
    }

    errors = validate(manifest)

    assert "scenario missing artifact_refs: V-01" in errors
    assert "scenario missing artifact_refs: V-10" in errors


def test_pass_manifest_rejects_unknown_artifact_reference() -> None:
    artifact_kinds = {
        "git_ref",
        "http",
        "postgres_sql",
        "browser",
        "process_restart",
    }
    manifest = {
        "status": "PASS",
        "approved_ref": "abc",
        "git_ref": "abc",
        "database_kind": "fresh_postgresql",
        "artifacts": [
            {"kind": kind, "ref": f"artifact:{kind}", "command": "pytest"}
            for kind in artifact_kinds
        ],
        "scenarios": [
            {
                "scenario_id": f"V-{index:02d}",
                "status": "PASS",
                "artifact_refs": ["artifact:http"],
            }
            for index in range(1, 11)
        ],
    }
    manifest["scenarios"][0]["artifact_refs"] = ["artifact:not-present"]

    errors = validate(manifest)

    assert "scenario references unknown artifact: V-01:artifact:not-present" in errors
