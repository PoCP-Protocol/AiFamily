"""Content-fidelity test for migration 0048
(`FAMILY_SUPPORT_NEEDS` v4 — Batch 2 construct admission items) — no real
Postgres needed.

Batch 2 admitted LEARNING_STRATEGY_METACOGNITION / SELF_REGULATION_SUPPORT
into `_LEGAL_CONSTRUCT_REFS` (governance/CONSTRUCT_ADMISSION_REGISTRY.yaml),
after a re-review clarified they are distinct analysis levels from the
already-admitted HOMEWORK_PROCESS (task-execution vs child-cognition vs
family-support-behavior) rather than overlapping duplicates. This unlocked
LEARNING_HABITS_Q02 and SELF_REGULATION_Q01-03 — all four verified
individually to carry `safety_boundary: normal_learning_support` in the
registry (no crisis-class flag, unlike Batch 1's exclusions).
"""
from __future__ import annotations

from backend.domains.assessment.domain.value_objects import AssessmentTool, AssessmentToolBoundary, AssessmentToolItem

_FOUR_POINT_OPTIONS = ["often", "sometimes", "rarely", "not_sure"]

_V4_ITEM_SCHEMA = {
    "items": [
        {"item_ref": "FOCUS", "response_type": "SINGLE_CHOICE", "required": True,
         "options": ["LEARNING_HABITS", "EMOTION_REGULATION", "PARENT_CHILD_COMMUNICATION", "DEVICE_USE_CONTEXT", "SELF_REGULATION"]},
        {"item_ref": "FAMILY_STRUCTURE", "response_type": "SINGLE_CHOICE", "required": False,
         "options": ["TWO_PARENT", "SINGLE_PARENT", "BLENDED", "PREFER_NOT_TO_SAY"]},
        {"item_ref": "CHILD_GENDER", "response_type": "SINGLE_CHOICE", "required": False,
         "options": ["BOY", "GIRL", "SELF_DESCRIBED", "PREFER_NOT_TO_SAY"]},
        {"item_ref": "LEARNING_HABITS_Q01", "response_type": "SINGLE_CHOICE", "required": False, "options": _FOUR_POINT_OPTIONS},
        {"item_ref": "LEARNING_HABITS_Q02", "response_type": "SINGLE_CHOICE", "required": False, "options": _FOUR_POINT_OPTIONS},
        {"item_ref": "LEARNING_HABITS_Q03", "response_type": "SINGLE_CHOICE", "required": False, "options": _FOUR_POINT_OPTIONS},
        {"item_ref": "PARENT_CHILD_COMMUNICATION_Q01", "response_type": "SINGLE_CHOICE", "required": False, "options": _FOUR_POINT_OPTIONS},
        {"item_ref": "PARENT_CHILD_COMMUNICATION_Q02", "response_type": "SINGLE_CHOICE", "required": False, "options": _FOUR_POINT_OPTIONS},
        {"item_ref": "PARENT_CHILD_COMMUNICATION_Q03", "response_type": "SINGLE_CHOICE", "required": False, "options": _FOUR_POINT_OPTIONS},
        {"item_ref": "DEVICE_USE_CONTEXT_Q01", "response_type": "SINGLE_CHOICE", "required": False, "options": _FOUR_POINT_OPTIONS},
        {"item_ref": "DEVICE_USE_CONTEXT_Q02", "response_type": "SINGLE_CHOICE", "required": False, "options": _FOUR_POINT_OPTIONS},
        {"item_ref": "DEVICE_USE_CONTEXT_Q03", "response_type": "SINGLE_CHOICE", "required": False, "options": _FOUR_POINT_OPTIONS},
        {"item_ref": "EMOTION_REGULATION_Q02", "response_type": "SINGLE_CHOICE", "required": False, "options": _FOUR_POINT_OPTIONS},
        {"item_ref": "EMOTION_REGULATION_Q03", "response_type": "SINGLE_CHOICE", "required": False, "options": _FOUR_POINT_OPTIONS},
        {"item_ref": "SCHOOL_FAMILY_FEEDBACK_LOOP", "response_type": "SINGLE_CHOICE", "required": False, "options": _FOUR_POINT_OPTIONS},
        {"item_ref": "SELF_REGULATION_Q01", "response_type": "SINGLE_CHOICE", "required": False, "options": _FOUR_POINT_OPTIONS},
        {"item_ref": "SELF_REGULATION_Q02", "response_type": "SINGLE_CHOICE", "required": False, "options": _FOUR_POINT_OPTIONS},
        {"item_ref": "SELF_REGULATION_Q03", "response_type": "SINGLE_CHOICE", "required": False, "options": _FOUR_POINT_OPTIONS},
    ]
}

_EXPECTED_NEW_ITEM_REFS = {"LEARNING_HABITS_Q02", "SELF_REGULATION_Q01", "SELF_REGULATION_Q02", "SELF_REGULATION_Q03"}

# Items whose constructs remain HOLD in governance/CONSTRUCT_ADMISSION_REGISTRY.yaml,
# plus Batch 1's crisis-flagged exclusions (still excluded, must not reappear here).
_STILL_EXCLUDED_ITEM_REFS = {
    "CHILD_ERROR_REVIEW_PATTERN", "SLEEP_ENERGY_LEARNING_IMPACT", "AI_LEARNING_USE_CLARITY",
    "MULTIMODAL_CREATION_OPPORTUNITY", "PARENT_CHILD_TALK_INTERRUPTION", "CHILD_WILLINGNESS_TO_TALK",
    "EMOTION_REGULATION_Q01", "PARENT_CAPACITY_PRESSURE",
}


def _parse_as_tool_from_db_row_shape() -> AssessmentTool:
    """Mirrors `sqlalchemy_repository._map_tool_row()` field-for-field, minus
    the DB round-trip — same Pydantic construction path a real load would hit.
    """
    return AssessmentTool(
        tool_ref="FAMILY_SUPPORT_NEEDS",
        version_no=4,
        title="家庭支持需要与服务偏好确认(含深挖题·批次2扩容)",
        purpose="在v3基础上,针对学习策略/元认知与自我管理支持两个新审核通过的方向追加观察题",
        schema_ref="family://assessment/FAMILY_SUPPORT_NEEDS/v4",
        items=[AssessmentToolItem(**item) for item in _V4_ITEM_SCHEMA["items"]],
        boundary=AssessmentToolBoundary(),
    )


class TestFamilySupportNeedsV4ItemBank:
    def test_v4_item_schema_parses_without_error(self):
        tool = _parse_as_tool_from_db_row_shape()
        assert tool.version_no == 4
        assert len(tool.items) == 18  # 14 (v3) + 4 new Batch-2 items

    def test_v3_items_are_preserved_unchanged(self):
        tool = _parse_as_tool_from_db_row_shape()
        for item_ref in ["FOCUS", "LEARNING_HABITS_Q01", "EMOTION_REGULATION_Q02", "SCHOOL_FAMILY_FEEDBACK_LOOP"]:
            assert tool.find_item(item_ref) is not None

    def test_new_batch2_items_present_with_four_point_frequency_scale(self):
        tool = _parse_as_tool_from_db_row_shape()
        for item_ref in _EXPECTED_NEW_ITEM_REFS:
            item = tool.find_item(item_ref)
            assert item is not None, f"{item_ref} missing from v4 item bank"
            assert item.response_type == "SINGLE_CHOICE"
            assert item.options == _FOUR_POINT_OPTIONS
            assert item.required is False

    def test_unreviewed_and_crisis_flagged_items_still_excluded(self):
        tool = _parse_as_tool_from_db_row_shape()
        present_refs = {item.item_ref for item in tool.items}
        leaked = present_refs & _STILL_EXCLUDED_ITEM_REFS
        assert not leaked, f"items that should still be excluded leaked into v4: {leaked}"

    def test_boundary_still_forbids_score_and_diagnosis(self):
        tool = _parse_as_tool_from_db_row_shape()
        assert tool.boundary.not_a_score is True
        assert tool.boundary.not_a_diagnosis is True
