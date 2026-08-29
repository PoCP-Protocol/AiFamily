"""R3 — No Legacy Import Without Manifest.

Every directory under backend/ that actually contains code must be
traceable to an entry in governance/MIGRATION_MANIFEST.yaml whose
`target` field contains that directory (exactly, or as an ancestor of
it). If a directory with .py files shows up under backend/ with no
manifest entry approving it, someone added code without going through
governance — that is exactly the "cp -R family-ai AiFamily" failure mode
R3 exists to prevent.

We deliberately check directories that *contain files* (not every
intermediate directory) so that a purely structural parent like
`backend/domains/` is never itself required to have a manifest entry —
only the leaf directories that actually hold code must be covered.

Wave 0 note: backend/ is expected to be empty or absent entirely. Both
cases are treated as trivially passing — there is nothing to check yet.
"""

from __future__ import annotations

from pathlib import Path

import yaml

MANIFEST_RELATIVE_PATH = "governance/MIGRATION_MANIFEST.yaml"
BACKEND_RELATIVE_PATH = "backend"


def _load_manifest_targets(repo_root: Path) -> set[str]:
    manifest_path = repo_root / MANIFEST_RELATIVE_PATH
    with manifest_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    targets: set[str] = set()
    for entry in data.get("entries") or []:
        target = entry.get("target")
        if target is None:
            continue
        if isinstance(target, str):
            targets.add(target)
        else:
            targets.update(target)
    return targets


def _dirs_containing_files(backend_dir: Path) -> set[Path]:
    if not backend_dir.exists():
        return set()
    return {p.parent for p in backend_dir.rglob("*") if p.is_file()}


def test_backend_code_dirs_are_all_manifested(repo_root: Path) -> None:
    backend_dir = repo_root / BACKEND_RELATIVE_PATH
    code_dirs = _dirs_containing_files(backend_dir)

    if not code_dirs:
        # Wave 0: backend/ does not exist or contains no files. Nothing to
        # enforce yet.
        return

    manifest_targets = _load_manifest_targets(repo_root)

    unmanifested = []
    for code_dir in code_dirs:
        rel_path = code_dir.relative_to(repo_root).as_posix()
        # A directory is "manifested" if some registered target is this exact
        # path, or is an ancestor of it (e.g. target backend/platform covers
        # a code dir backend/platform/identity/impl).
        covered = any(
            rel_path == target or rel_path.startswith(target + "/") for target in manifest_targets
        )
        if not covered:
            unmanifested.append(rel_path)

    assert not unmanifested, (
        "R3 violation: the following backend/ directories contain files but have no "
        f"corresponding (or ancestor) entry in {MANIFEST_RELATIVE_PATH}'s `target` "
        f"field: {sorted(unmanifested)}. Register the capability with disposition "
        "MIGRATE or REIMPLEMENT before adding code."
    )
