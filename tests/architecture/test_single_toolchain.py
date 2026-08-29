"""R11 — Single Dependency Toolchain.

Python dependencies are managed exclusively with uv + pyproject.toml.
No pip/poetry/pipenv/requirements.txt may coexist. uv.lock is the only
allowed lockfile. This test enforces the mechanical, file-presence part
of R11 at the repository root.
"""

from __future__ import annotations

from pathlib import Path

FORBIDDEN_ROOT_GLOBS = [
    "requirements*.txt",
    "Pipfile",
    "Pipfile.lock",
    "poetry.lock",
    "setup.py",
    "setup.cfg",
]


def test_pyproject_toml_exists(repo_root: Path) -> None:
    assert (repo_root / "pyproject.toml").is_file(), (
        "R11 violation: repository root has no pyproject.toml — it must be the "
        "single source of Python dependency declarations."
    )


def test_no_competing_dependency_manifests_at_root(repo_root: Path) -> None:
    offenders: list[str] = []
    for pattern in FORBIDDEN_ROOT_GLOBS:
        offenders.extend(p.name for p in repo_root.glob(pattern))

    assert not offenders, (
        "R11 violation: found competing Python dependency manifest(s) at the "
        f"repository root: {sorted(offenders)}. Only pyproject.toml "
        "(+ optionally uv.lock) is allowed."
    )
