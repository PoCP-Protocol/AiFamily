"""R2 — Single Domain Truth.

governance/DOMAIN_REGISTRY.yaml is the only authority for "where does the
canonical implementation of capability X live". This test enforces the
mechanical part of R2: no capability may be registered under two
different canonical paths, and no capability entry may be duplicated
outright.

Wave 0 note: if the registry does not exist yet, we skip with a clear
reason instead of failing — R2 has nothing to enforce until the registry
exists, and a hard failure here would block bootstrapping the repo.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REGISTRY_RELATIVE_PATH = "governance/DOMAIN_REGISTRY.yaml"


def _load_registry(repo_root: Path) -> dict:
    registry_path = repo_root / REGISTRY_RELATIVE_PATH
    with registry_path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_domain_registry_present_or_skip(repo_root: Path) -> None:
    registry_path = repo_root / REGISTRY_RELATIVE_PATH
    if not registry_path.exists():
        pytest.skip(
            f"{REGISTRY_RELATIVE_PATH} does not exist yet — R2 has no registry "
            "to enforce. This test will start enforcing as soon as the file "
            "is created."
        )
    assert registry_path.stat().st_size > 0, f"{REGISTRY_RELATIVE_PATH} exists but is empty"


def test_each_capability_appears_exactly_once(repo_root: Path) -> None:
    registry_path = repo_root / REGISTRY_RELATIVE_PATH
    if not registry_path.exists():
        pytest.skip(f"{REGISTRY_RELATIVE_PATH} does not exist yet — nothing to check")

    data = _load_registry(repo_root)
    entries = data.get("entries") or []
    assert entries, f"{REGISTRY_RELATIVE_PATH} has no entries — nothing registered under R2"

    capability_names = [entry["capability"] for entry in entries]
    duplicates = {name for name in capability_names if capability_names.count(name) > 1}
    assert not duplicates, (
        "R2 violation: the following capabilities are registered more than once in "
        f"{REGISTRY_RELATIVE_PATH}: {sorted(duplicates)}. "
        "A business capability must have exactly one canonical implementation entry."
    )


def test_no_capability_has_multiple_canonical_paths(repo_root: Path) -> None:
    """A single capability entry must declare a single canonical_path.

    This is distinct from two *different* capabilities intentionally
    sharing a directory (e.g. platform_actor_tenant_context and
    auth_identity both landing under backend/platform/identity per the
    migration manifest) — that is a manifest-level decision, not an R2
    violation. What R2 forbids is the same capability name being pointed
    at two different "true" locations, which would mean nobody knows
    which one is authoritative.
    """
    registry_path = repo_root / REGISTRY_RELATIVE_PATH
    if not registry_path.exists():
        pytest.skip(f"{REGISTRY_RELATIVE_PATH} does not exist yet — nothing to check")

    data = _load_registry(repo_root)
    entries = data.get("entries") or []

    paths_by_capability: dict[str, set[str]] = {}
    for entry in entries:
        capability = entry["capability"]
        canonical_path = entry.get("canonical_path")
        assert canonical_path, f"capability '{capability}' has no canonical_path"
        assert isinstance(canonical_path, str), (
            f"capability '{capability}' has a non-scalar canonical_path "
            f"({canonical_path!r}) — R2 requires exactly one path per entry, "
            "not a list."
        )
        paths_by_capability.setdefault(capability, set()).add(canonical_path)

    offenders = {cap: paths for cap, paths in paths_by_capability.items() if len(paths) > 1}
    assert not offenders, (
        "R2 violation: the following capabilities have more than one canonical_path "
        f"registered across separate entries: {offenders}"
    )
