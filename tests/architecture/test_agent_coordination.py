from pathlib import Path

from tools.governance.check_agent_coordination import _load, _path_overlap

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_coordination_register_is_adr_bound_and_has_required_protocol() -> None:
    data = _load(REPO_ROOT)
    assert data["authority"]["adr"] == (
        "governance/ADR/ADR-0158-agi-native-family-growth-platform.md"
    )
    assert "READY_FOR_REVIEW" in data["protocol"]["statuses"]
    assert "exact_ref" in data["protocol"]["integration_requirements"]


def test_observed_thread_ids_are_unique() -> None:
    data = _load(REPO_ROOT)
    ids = [entry["task_id"] for entry in data["observed_threads"]]
    assert len(ids) == len(set(ids))


def test_path_overlap_is_ancestor_aware() -> None:
    assert _path_overlap(["backend/domains/family"], ["backend/domains/family/api.py"])
    assert not _path_overlap(["backend/domains/family"], ["backend/domains/service"])
