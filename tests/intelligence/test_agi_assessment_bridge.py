from __future__ import annotations

import pytest

from backend.intelligence.agi_assessment_bridge import build_vertical_draft_input
from backend.intelligence.agi_vertical_runtime import FamilyGrowthContext


def context() -> FamilyGrowthContext:
    return FamilyGrowthContext(
        "tenant-1",
        "family-1",
        ("child-1",),
        "family-growth-understanding",
        "consent-v1",
        "context:need-1:v3",
        {"family_need_id": "need-1", "statement": "孩子很难开始作业"},
    )


def test_maps_assessment_evidence_to_existing_draft_payload_without_fact_promotion():
    payload, refs = build_vertical_draft_input(
        context(),
        family_need_id="need-1",
        path_id="path-1",
        run_id="run-1",
        assessment_evidence={
            "assessment_session_id": "session-1",
            "assessment_response_id": "response-1",
            "assessment_evidence_id": "evidence-1",
            "tool_ref": "tool:focus",
            "focus_ref": "LEARNING_HABITS",
            "response_set": [{"item_ref": "q1", "response_value": "often"}],
        },
    )
    assert payload["family_need_id"] == "need-1"
    assert payload["assessment_evidence"]["source_refs"] == (
        "session-1",
        "response-1",
        "evidence-1",
        "tool:focus",
    )
    assert payload["assessment_evidence"]["boundary"] == "HYPOTHESIS_NOT_FACT_OR_DIAGNOSIS"
    assert "run-1" in refs
    assert "evidence-1" in refs


def test_rejects_assessment_without_source_refs():
    with pytest.raises(ValueError, match="ASSESSMENT_EVIDENCE_REFS_REQUIRED"):
        build_vertical_draft_input(
            context(),
            family_need_id="need-1",
            path_id="path-1",
            run_id="run-1",
            assessment_evidence={"focus_ref": "LEARNING_HABITS"},
        )
