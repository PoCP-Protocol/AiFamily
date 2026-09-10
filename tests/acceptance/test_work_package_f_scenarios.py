from __future__ import annotations

from tests.acceptance.work_package_f_scenarios import APPROVED_REF, SCENARIOS, scenario_ids


def test_work_package_f_scenario_inventory_is_unique_and_hard_gated() -> None:
    ids = scenario_ids()

    assert APPROVED_REF == "72eec31d178e14a32aa6a05b4189c8c515119975"
    assert len(ids) == len(set(ids)) == 8
    assert all(s.hard_gate and s.required_proof and s.forbidden_substitutes for s in SCENARIOS)


def test_work_package_f_inventory_contains_required_red_team_dimensions() -> None:
    titles = {scenario.title for scenario in SCENARIOS}

    assert "Default composition root and real HTTP" in titles
    assert "Fresh PostgreSQL persistence" in titles
    assert "Cross-process restart readback" in titles
    assert "Browser golden path" in titles
    assert "Two-family differential evidence" in titles
    assert "Guardian four-state matrix" in titles
    assert "Published Knowledge and ModelGateway provenance" in titles
    assert "Replay, deletion, and cross-scope negatives" in titles
