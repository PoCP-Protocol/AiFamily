"""R13 — Historical Documents Must Not Act As Current Truth.

docs/00_system/ holds the system source of truth: SYSTEM_MANIFEST plus the
CURRENT_* baseline documents. Everything that documents a superseded decision
must live under docs/99_archive/ and must clearly mark itself as superseded, so
nobody mistakes it for a live baseline the way the source repository's three
self-declared "current baseline" documents did.

Layout note: this replaced the earlier docs/00_foundation + docs/archive pair
when the Documentation Architecture V1.0 (16-layer docs/ tree) was adopted.
The rule is unchanged; only the directory names moved.
"""

from __future__ import annotations

from pathlib import Path

SYSTEM_DIR = "docs/00_system"
ARCHIVE_DIR = "docs/99_archive"

# Research and reference material is explicitly non-canonical. It must say so,
# otherwise an agent can mistake a research note for an accepted design.
RESEARCH_DIR = "docs/13_research"
NON_CANONICAL_MARKERS = ["RESEARCH_ONLY", "NOT_CANONICAL", "STATUS: RESEARCH"]

SUPERSEDED_MARKERS = ["SUPERSEDED", "ARCHIVED", "DEPRECATED", "已被取代", "DO_NOT_USE"]


def test_current_system_docs_exist_and_are_nonempty(repo_root: Path) -> None:
    system_dir = repo_root / SYSTEM_DIR
    assert system_dir.is_dir(), f"{SYSTEM_DIR} does not exist"

    current_docs = sorted(system_dir.glob("CURRENT_*.md"))
    assert current_docs, f"{SYSTEM_DIR} has no CURRENT_*.md files — no current truth is declared"

    empty = [p.name for p in current_docs if p.stat().st_size == 0]
    assert not empty, f"R13 violation: the following CURRENT_*.md files are empty: {empty}"


def test_system_manifest_exists(repo_root: Path) -> None:
    """SYSTEM_MANIFEST.md is the single entry point every human and agent reads first.

    Without it there is no declared answer to "which documents are canonical",
    which is the precondition for every other R13 guarantee.
    """
    manifest = repo_root / SYSTEM_DIR / "SYSTEM_MANIFEST.md"
    assert manifest.is_file(), f"{SYSTEM_DIR}/SYSTEM_MANIFEST.md is missing"
    assert manifest.stat().st_size > 0, "SYSTEM_MANIFEST.md is empty"


def test_archive_docs_are_marked_as_superseded(repo_root: Path) -> None:
    archive_dir = repo_root / ARCHIVE_DIR
    if not archive_dir.exists():
        return  # nothing archived yet — nothing to check

    archived_files = [
        p for p in archive_dir.rglob("*") if p.is_file() and p.suffix in {".md", ".txt"}
    ]
    if not archived_files:
        return  # directory exists but is empty — nothing to check

    unmarked: list[str] = []
    for doc in archived_files:
        head = doc.read_text(encoding="utf-8", errors="ignore")[:2000]
        if not any(marker in head for marker in SUPERSEDED_MARKERS):
            unmarked.append(doc.relative_to(repo_root).as_posix())

    assert not unmarked, (
        "R13 violation: the following docs/99_archive/ files do not mark themselves "
        f"as superseded (expected one of {SUPERSEDED_MARKERS} near the top): {unmarked}"
    )


def test_research_docs_declare_themselves_non_canonical(repo_root: Path) -> None:
    """Research must never be readable as accepted design.

    The source repository's failure mode was the reverse: research notes and
    proposals sat beside frozen baselines with no status marker, so both humans
    and agents treated "we looked into this" as "we decided this".
    """
    research_dir = repo_root / RESEARCH_DIR
    if not research_dir.exists():
        return

    research_files = [p for p in research_dir.rglob("*.md") if p.is_file()]
    if not research_files:
        return

    unmarked: list[str] = []
    for doc in research_files:
        head = doc.read_text(encoding="utf-8", errors="ignore")[:2000]
        if not any(marker in head for marker in NON_CANONICAL_MARKERS):
            unmarked.append(doc.relative_to(repo_root).as_posix())

    assert not unmarked, (
        "R13 violation: the following docs/13_research/ files do not declare themselves "
        f"non-canonical (expected one of {NON_CANONICAL_MARKERS} near the top): {unmarked}"
    )
