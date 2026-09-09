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
