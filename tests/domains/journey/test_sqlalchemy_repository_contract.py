from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_repository_targets_existing_canonical_baseline_tables() -> None:
    source = (
        REPO_ROOT / "backend/domains/journey/infrastructure/sqlalchemy_repository.py"
    ).read_text(encoding="utf-8")
    assert "family_journey_plans" in source
    assert "family_journey_plan_phases" in source
    assert "growth_priorities" in source
    assert "growth_journeys" in source
    assert "growth_actions" in source
    assert "journey_plan_id=:plan_id" in source
    assert "status='COMPLETED'" in source
    assert "create table" not in source.lower()


def test_repository_preserves_family_and_onboarding_scope() -> None:
    source = (
        REPO_ROOT / "backend/domains/journey/infrastructure/sqlalchemy_repository.py"
    ).read_text(encoding="utf-8")
    assert source.count("family_id=:family_id") >= 6
    assert source.count("onboarding_id=:onboarding_id") >= 4
    assert "PRIORITY_IS_HUMAN_CONFIRMED_PRACTICE_FOCUS" in source
    assert "PLAN_IS_FAMILY_CONFIRMED_CADENCE_NOT_DIAGNOSIS_OR_OUTCOME" in source
