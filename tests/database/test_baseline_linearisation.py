"""Guards `database/baseline/` against silent drift from the legacy SQL.

The Alembic baseline (`database/migrations/versions/0001_legacy_schema_baseline.py`)
replays these files verbatim instead of expressing 151 tables as `op.*` calls,
and that choice is only defensible if "verbatim" is actually checkable. These
tests are the check. They assert three separate things, because each can break
independently:

1. `LINEARISATION_MAP.md`'s mapping table is internally consistent with what is
   on disk (no file listed but missing, none present but unlisted, sequence
   numbers contiguous). Runs always — no legacy repository needed.
2. Every baseline file is byte-identical to the legacy file it claims to come
   from. Requires the legacy checkout; **skips** with a stated reason when it is
   not reachable rather than passing vacuously.
3. The relative order asserted by `LINEARISATION_MAP.md` §3 for the one
   empirically-verified hard dependency still holds in the filenames.

The legacy directory is supplied by the `AIFAMILY_LEGACY_MIGRATIONS_DIR`
environment variable. R12 forbids hardcoding source-repository paths in
executable code, and it would be wrong anyway: the legacy checkout is not part
of this repository and CI has no copy of it.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import re

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
BASELINE_DIR = _REPO_ROOT / "database" / "baseline"
LINEARISATION_MAP = _REPO_ROOT / "database" / "migrations" / "LINEARISATION_MAP.md"

LEGACY_DIR_ENV_VAR = "AIFAMILY_LEGACY_MIGRATIONS_DIR"

EXPECTED_FILE_COUNT = 62

#: The one ordering constraint proven by experiment rather than by reading:
#: applying `family_growth_page_objects` before `test_experience_workflows`
#: fails with `relation "test_experience_operations" does not exist`
#: (LINEARISATION_MAP.md §3.1). Encoded here so a future re-linearisation
#: cannot quietly reintroduce the failure.
REQUIRED_ORDERING = [
    ("test_experience_workflows", "family_growth_page_objects"),
]

_MAP_ROW = re.compile(
    r"^\|\s*`(?P<legacy>\d{4}_[a-z0-9_]+\.sql)`\s*\|\s*`(?P<baseline>\d{4}_[a-z0-9_]+\.sql)`\s*\|"
)


def _parse_mapping() -> list[tuple[str, str]]:
    text = LINEARISATION_MAP.read_text(encoding="utf-8")
    matches = (_MAP_ROW.match(line) for line in text.splitlines())
    rows = [(m.group("legacy"), m.group("baseline")) for m in matches if m]
    assert rows, (
        f"No mapping rows parsed from {LINEARISATION_MAP.name} — the table format changed"
    )
    return rows


def _legacy_dir() -> pathlib.Path | None:
    raw = os.environ.get(LEGACY_DIR_ENV_VAR)
    if not raw:
        return None
    path = pathlib.Path(raw)
    return path if path.is_dir() else None


def test_mapping_matches_files_on_disk() -> None:
    mapping = _parse_mapping()
    assert len(mapping) == EXPECTED_FILE_COUNT, (
        f"{LINEARISATION_MAP.name} lists {len(mapping)} rows, expected {EXPECTED_FILE_COUNT}"
    )

    mapped = {baseline for _, baseline in mapping}
    on_disk = {p.name for p in BASELINE_DIR.glob("*.sql")}

    assert mapped - on_disk == set(), (
        f"listed in the map but missing from baseline/: {sorted(mapped - on_disk)}"
    )
    assert on_disk - mapped == set(), (
        f"present in baseline/ but absent from the map: {sorted(on_disk - mapped)}"
    )


def test_baseline_sequence_numbers_are_contiguous_and_unique() -> None:
    numbers = sorted(int(p.name[:4]) for p in BASELINE_DIR.glob("*.sql"))
    assert numbers == list(range(1, EXPECTED_FILE_COUNT + 1)), (
        "Baseline sequence numbers must be 1..N with no gaps or duplicates — a gap means a file "
        f"was deleted without re-linearising. Got: {numbers}"
    )


def test_legacy_numbering_is_order_preserving() -> None:
    """The linearisation must not reorder anything, only disambiguate.

    Sorting the mapping by new sequence number must reproduce the legacy
    filename sort order, because that sort order *is* the legacy application
    order (`tools/migrate.mjs` used `readdirSync().sort()`).
    """
    mapping = _parse_mapping()
    by_new_number = [legacy for legacy, _ in sorted(mapping, key=lambda r: int(r[1][:4]))]
    assert by_new_number == sorted(legacy for legacy, _ in mapping), (
        "The new sequence reorders the legacy files. Linearisation may only disambiguate "
        "duplicate numbers, never change relative order — a reorder needs its own ADR."
    )


@pytest.mark.parametrize(("earlier", "later"), REQUIRED_ORDERING)
def test_verified_hard_dependency_ordering_holds(earlier: str, later: str) -> None:
    names = sorted(p.name for p in BASELINE_DIR.glob("*.sql"))
    positions = {
        stem: i for i, name in enumerate(names) for stem in (earlier, later) if stem in name
    }
    assert earlier in positions and later in positions, (
        f"could not locate {earlier!r}/{later!r} in baseline/"
    )
    assert positions[earlier] < positions[later], (
        f"{earlier} must be applied before {later} — see LINEARISATION_MAP.md section 3.1; "
        "the reverse order fails with 'relation \"test_experience_operations\" does not exist'."
    )


def test_baseline_files_are_byte_identical_to_legacy() -> None:
    legacy_dir = _legacy_dir()
    if legacy_dir is None:
        pytest.skip(
            f"{LEGACY_DIR_ENV_VAR} is unset or not a directory — cannot verify baseline "
            "SQL against the legacy checkout. Set it to the legacy repository's "
            "database/migrations directory to run this check."
        )

    mismatches: list[str] = []
    for legacy_name, baseline_name in _parse_mapping():
        legacy_file = legacy_dir / legacy_name
        baseline_file = BASELINE_DIR / baseline_name
        if not legacy_file.is_file():
            mismatches.append(f"{legacy_name}: missing from legacy directory")
            continue
        legacy_hash = hashlib.sha256(legacy_file.read_bytes()).hexdigest()
        baseline_hash = hashlib.sha256(baseline_file.read_bytes()).hexdigest()
        if legacy_hash != baseline_hash:
            mismatches.append(
                f"{baseline_name}: sha256 {baseline_hash[:12]} != legacy {legacy_hash[:12]}"
            )

    assert not mismatches, (
        "Baseline SQL has drifted from the legacy source. The baseline is a faithful snapshot; any "
        "schema change belongs in a new Alembic revision, never in these files:\n"
        + "\n".join(mismatches)
    )
