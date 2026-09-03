from collections import Counter

from backend.intelligence.experience.gold_set import (
    DEFAULT_GOLD_SET_COUNTS,
    DEFAULT_GOLD_SET_VERSION,
    build_default_gold_set,
    gold_set_fingerprint,
)


def test_default_gold_set_has_required_modalities_and_refusal_ratio() -> None:
    cases = build_default_gold_set()
    categories = Counter(
        next(iter(case.modalities)) if len(case.modalities) == 1 else "mixed" for case in cases
    )
    assert len(cases) == 200
    assert categories == Counter(DEFAULT_GOLD_SET_COUNTS)
    assert sum(case.expected_refusal for case in cases) == 40
    assert all(case.version == DEFAULT_GOLD_SET_VERSION for case in cases)
    assert all(case.fixture_kind == "synthetic" for case in cases)


def test_gold_set_is_reproducible_and_contains_only_opaque_media_refs() -> None:
    first = build_default_gold_set()
    second = build_default_gold_set()
    assert gold_set_fingerprint(first) == gold_set_fingerprint(second)
    assert len(gold_set_fingerprint(first)) == 64
    assert all(ref.startswith("fixture:") for case in first for ref in case.media_refs)


def test_gold_set_version_changes_fingerprint_without_changing_matrix() -> None:
    first = build_default_gold_set(version="gold.v1")
    second = build_default_gold_set(version="gold.v2")
    assert len(first) == len(second) == 200
    assert gold_set_fingerprint(first) != gold_set_fingerprint(second)
