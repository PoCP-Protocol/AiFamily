"""Capability Registry integrity — the check that keeps the registry honest.

`governance/CAPABILITY_REGISTRY.yaml` is the file that connects documentation to
code: one row per capability, from domain/actor/command/api down to code paths
and tests. Its whole value is that it describes facts.

The source repository's failure mode is the reason these tests exist:
`governance/FPAI_PROVIDER_REGISTRY.yaml` declared three providers while its own
generated artifact carried two, and the generator's `--check` mode exited 1 on
the baseline commit — because no CI ever ran it. A registry nobody verifies is
worse than no registry, because it is read as truth.

So: every path this registry claims must exist on disk, and every status word
must be legal.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REGISTRY_PATH = "governance/CAPABILITY_REGISTRY.yaml"

# A capability may only claim PRODUCTION once it actually serves production
# traffic. Nothing in AiFamily does yet; this list exists so that the day
# something claims it, the claim is a deliberate act.
LEGAL_STATUSES = {
    "PLANNED",
    "IMPLEMENTED_UNTESTED",
    "IMPLEMENTED_TESTED",
    "PRODUCTION",
}

LEGAL_ACTOR_TYPES = {"guardian", "child", "operator", "teacher", "system", "ai"}


@pytest.fixture
def registry(repo_root: Path) -> dict:
    path = repo_root / REGISTRY_PATH
    assert path.is_file(), f"{REGISTRY_PATH} does not exist"
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    assert isinstance(data, dict), f"{REGISTRY_PATH} must parse to a mapping"
    return data


def test_registry_declares_its_enums(registry: dict) -> None:
    enums = registry.get("enums")
    assert isinstance(enums, dict), "registry must declare an `enums` block"
    assert set(enums.get("status", [])) == LEGAL_STATUSES, (
        "registry's declared status enum drifted from the one the tests enforce — "
        "change both together or neither"
    )
    assert set(enums.get("actor_type", [])) == LEGAL_ACTOR_TYPES
    assert enums.get("business_capability"), (
        "registry must declare an `enums.business_capability` list — it is the "
        "vocabulary the upstream traceability link is checked against"
    )


def test_every_capability_has_upstream_attribution(registry: dict) -> None:
    """The upstream half of the DOCUMENT_GOVERNANCE §6 chain.

    The chain runs Strategy → Business Capability → ... → Test. This registry
    already carries Domain-downwards; `business_capability` is the field that
    keeps the link above Domain from snapping. It is an explicit declaration
    rather than something derived from `domain`, because deriving it from the
    code location would be circular — it could never fail, and a check that
    cannot fail certifies nothing.

    `PLATFORM_INTERNAL` is a legal answer: platform primitives genuinely do not
    serve one business capability, and forcing an invented attribution would be
    worse than recording that fact.
    """
    legal = set(registry.get("enums", {}).get("business_capability") or [])
    problems: list[str] = []
    for entry in registry.get("capabilities", []):
        name = entry.get("capability", "<unnamed>")
        attribution = entry.get("business_capability")
        if not attribution:
            problems.append(f"{name}: missing `business_capability`")
        elif attribution not in legal:
            problems.append(f"{name}: {attribution!r} not in enums.business_capability")
    assert not problems, (
        "capabilities whose upstream traceability link is broken (see "
        "tools/architecture/check_traceability.py):\n" + "\n".join(problems)
    )


def test_capability_names_are_unique(registry: dict) -> None:
    names = [entry["capability"] for entry in registry.get("capabilities", [])]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    assert not duplicates, f"duplicate capability names: {duplicates}"


def test_every_capability_has_required_fields(registry: dict) -> None:
    required = {
        "capability",
        "business_capability",
        "domain",
        "purpose",
        "actor",
        "code",
        "status",
    }
    missing: list[str] = []
    for entry in registry.get("capabilities", []):
        absent = required - entry.keys()
        if absent:
            missing.append(f"{entry.get('capability', '<unnamed>')}: missing {sorted(absent)}")
    assert not missing, "capabilities with missing required fields:\n" + "\n".join(missing)


def test_every_status_is_legal(registry: dict) -> None:
    illegal: list[str] = []
    for entry in registry.get("capabilities", []):
        status = entry.get("status")
        if status not in LEGAL_STATUSES:
            illegal.append(f"{entry['capability']}: {status!r}")
    assert not illegal, (
        f"illegal status values (legal: {sorted(LEGAL_STATUSES)}):\n" + "\n".join(illegal)
    )


def test_every_actor_is_legal(registry: dict) -> None:
    illegal: list[str] = []
    for entry in registry.get("capabilities", []):
        for actor in entry.get("actor", []):
            if actor not in LEGAL_ACTOR_TYPES:
                illegal.append(f"{entry['capability']}: {actor!r}")
    assert not illegal, (
        f"illegal actor values (legal: {sorted(LEGAL_ACTOR_TYPES)}):\n" + "\n".join(illegal)
    )


def test_declared_code_paths_exist(registry: dict, repo_root: Path) -> None:
    """Closes the gap the registry itself flags under `enforcement.missing`.

    Without this, the registry can point at a deleted module and CI stays green
    — which is precisely how the source repository's registries rotted.
    """
    dead: list[str] = []
    for entry in registry.get("capabilities", []):
        code = entry.get("code") or {}
        for layer, rel_path in code.items():
            if not rel_path:
                continue
            if not (repo_root / rel_path).exists():
                dead.append(f"{entry['capability']}.code.{layer} -> {rel_path}")
    assert not dead, "registry points at paths that do not exist:\n" + "\n".join(dead)


def test_declared_test_paths_exist(registry: dict, repo_root: Path) -> None:
    dead: list[str] = []
    for entry in registry.get("capabilities", []):
        for rel_path in entry.get("tests") or []:
            if not (repo_root / rel_path).exists():
                dead.append(f"{entry['capability']}.tests -> {rel_path}")
    assert not dead, "registry claims tests that do not exist:\n" + "\n".join(dead)


def test_tested_status_requires_declared_tests(registry: dict) -> None:
    """R4 — no capability may claim to be tested without naming its tests."""
    unsupported: list[str] = []
    for entry in registry.get("capabilities", []):
        if entry.get("status") in {"IMPLEMENTED_TESTED", "PRODUCTION"} and not entry.get("tests"):
            unsupported.append(entry["capability"])
    assert not unsupported, (
        "R4 violation: these capabilities claim IMPLEMENTED_TESTED/PRODUCTION "
        f"but declare no tests: {unsupported}"
    )


def test_not_yet_capabilities_paths_exist(registry: dict, repo_root: Path) -> None:
    """The `not_yet_capabilities` block is an honesty ledger, not a wishlist.

    Each entry says "code lives here but it does not constitute a capability".
    If the path is gone, the entry is stale and should be removed.
    """
    dead: list[str] = []
    for entry in registry.get("not_yet_capabilities") or []:
        rel_path = entry.get("path")
        if rel_path and not (repo_root / rel_path).exists():
            dead.append(rel_path)
    assert not dead, "not_yet_capabilities points at paths that do not exist:\n" + "\n".join(dead)
