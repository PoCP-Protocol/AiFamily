from __future__ import annotations

import ast
from pathlib import Path

from backend.apps.family_api.growth_plan_review_wiring import GrowthPlanDraftReviewRow

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "database" / "migrations" / "versions" / "0057_ai_growth_plan_draft_reviews.py"


def _revision_values() -> dict[str, object]:
    tree = ast.parse(MIGRATION.read_text(encoding="utf-8"))
    values: dict[str, object] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id in {"revision", "down_revision"}
            and node.value is not None
        ):
            values[node.target.id] = ast.literal_eval(node.value)
    return values


def test_growth_plan_review_migration_extends_current_chain_and_matches_orm() -> None:
    assert _revision_values() == {
        "revision": "0057_ai_growth_plan_draft_reviews",
        "down_revision": "0056_course_content",
    }
    expected = {
        "tenant_id",
        "draft_id",
        "request_id",
        "agent_run_id",
        "provenance_ref",
        "family_id",
        "region_id",
        "subject_person_id",
        "purpose",
        "consent_version",
        "data_class",
        "locale",
        "deletion_ref",
        "generation_correlation_id",
        "scope_payload",
        "intent_id",
        "onboarding_id",
        "priority_id",
        "input_refs",
        "stable_digest",
        "status",
        "may_mutate_business_state",
        "retention_policy",
        "created_at",
        "expires_at",
    }
    assert set(GrowthPlanDraftReviewRow.__table__.columns.keys()) == expected


def test_growth_plan_review_migration_enforces_draft_only_and_immutability() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert "ck_ai_growth_plan_review_draft_only" in source
    assert "ck_ai_growth_plan_review_cannot_mutate" in source
    assert "ck_ai_growth_plan_review_positive_ttl" in source
    assert "BEFORE UPDATE" in source
    assert "ai growth plan draft review rows are immutable" in source
