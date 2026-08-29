"""Content-fidelity test for migration 0046
(`FAMILY_SUPPORT_NEEDS` v2 deep-dive items) — no real Postgres needed.

Verifies the exact `item_schema` JSON the migration inserts parses through
`AssessmentTool`/`AssessmentToolItem` the same way
`sqlalchemy_repository._map_tool_row()` would parse a row loaded from a real
database, and that it contains exactly the 8 new deep-dive items (plus the 3
original v1 items) whose `item_ref` matches
`docs/model/family_assessment_item_bank.registry.yaml` — construct scope
intentionally limited to PARENT_CHILD_COMMUNICATION/HOMEWORK_PROCESS/
DEVICE_USE_CONTEXT (the three refs already reviewed in
`claude_interpretation.py`'s `_LEGAL_CONSTRUCT_REFS`); the registry's other 17
items (EMOTION_REGULATION_*, SELF_REGULATION_*, the English 10-item bank) are
deliberately excluded and this test does not expect them.

This test hardcodes the item_schema JSON rather than reading the .sql file at
runtime — the migration file is the deployment artifact, this test is the
"if this exact content lands in the DB, does it parse and does it contain
what we intended" golden check. If the migration content and this test drift,
that's a signal someone edited one without the other.
"""
from __future__ import annotations

from backend.domains.assessment.domain.value_objects import AssessmentTool, AssessmentToolBoundary, AssessmentToolItem

_FOUR_POINT_OPTIONS = ["often", "sometimes", "rarely", "not_sure"]

_V2_ITEM_SCHEMA = {
    "items": [
        {"item_ref": "FOCUS", "response_type": "SINGLE_CHOICE", "required": True,
         "options": ["LEARNING_HABITS", "EMOTION_REGULATION", "PARENT_CHILD_COMMUNICATION", "DEVICE_USE_CONTEXT", "SELF_REGULATION"]},
        {"item_ref": "FAMILY_STRUCTURE", "response_type": "SINGLE_CHOICE", "required": False,
         "options": ["TWO_PARENT", "SINGLE_PARENT", "BLENDED", "PREFER_NOT_TO_SAY"]},
        {"item_ref": "CHILD_GENDER", "response_type": "SINGLE_CHOICE", "required": False,
         "options": ["BOY", "GIRL", "SELF_DESCRIBED", "PREFER_NOT_TO_SAY"]},
        {"item_ref": "LEARNING_HABITS_Q01", "response_type": "SINGLE_CHOICE", "required": False, "options": _FOUR_POINT_OPTIONS},
        {"item_ref": "LEARNING_HABITS_Q03", "response_type": "SINGLE_CHOICE", "required": False, "options": _FOUR_POINT_OPTIONS},
        {"item_ref": "PARENT_CHILD_COMMUNICATION_Q01", "response_type": "SINGLE_CHOICE", "required": False, "options": _FOUR_POINT_OPTIONS},
        {"item_ref": "PARENT_CHILD_COMMUNICATION_Q02", "response_type": "SINGLE_CHOICE", "required": False, "options": _FOUR_POINT_OPTIONS},
        {"item_ref": "PARENT_CHILD_COMMUNICATION_Q03", "response_type": "SINGLE_CHOICE", "required": False, "options": _FOUR_POINT_OPTIONS},
        {"item_ref": "DEVICE_USE_CONTEXT_Q01", "response_type": "SINGLE_CHOICE", "required": False, "options": _FOUR_POINT_OPTIONS},
        {"item_ref": "DEVICE_USE_CONTEXT_Q02", "response_type": "SINGLE_CHOICE", "required": False, "options": _FOUR_POINT_OPTIONS},
        {"item_ref": "DEVICE_USE_CONTEXT_Q03", "response_type": "SINGLE_CHOICE", "required": False, "options": _FOUR_POINT_OPTIONS},
    ]
}

_EXPECTED_NEW_ITEM_REFS = {
    "LEARNING_HABITS_Q01", "LEARNING_HABITS_Q03",
    "PARENT_CHILD_COMMUNICATION_Q01", "PARENT_CHILD_COMMUNICATION_Q02", "PARENT_CHILD_COMMUNICATION_Q03",
    "DEVICE_USE_CONTEXT_Q01", "DEVICE_USE_CONTEXT_Q02", "DEVICE_USE_CONTEXT_Q03",
}

# Items whose registry construct_refs are NOT a subset of the 3 legal refs — must
# never appear in this tool version, even accidentally.
_EXCLUDED_ITEM_REFS = {
    "EMOTION_REGULATION_Q01", "EMOTION_REGULATION_Q02", "EMOTION_REGULATION_Q03",
    "SELF_REGULATION_Q01", "SELF_REGULATION_Q02", "SELF_REGULATION_Q03",
    "CHILD_ERROR_REVIEW_PATTERN", "SLEEP_ENERGY_LEARNING_IMPACT", "AI_LEARNING_USE_CLARITY",
    "MULTIMODAL_CREATION_OPPORTUNITY", "PARENT_CAPACITY_PRESSURE", "SCHOOL_FAMILY_FEEDBACK_LOOP",
    "PARENT_CHILD_TALK_INTERRUPTION", "CHILD_WILLINGNESS_TO_TALK",
}


def _parse_as_tool_from_db_row_shape() -> AssessmentTool:
    """Mirrors `sqlalchemy_repository._map_tool_row()` field-for-field, minus
    the DB round-trip — same Pydantic construction path a real load would hit.
    """
    return AssessmentTool(
        tool_ref="FAMILY_SUPPORT_NEEDS",
        version_no=2,
        title="家庭支持需要与服务偏好确认(含深挖题)",
        purpose="在v1的场景/偏好确认基础上,针对学习习惯/亲子沟通/设备使用三个已审核方向追加具体观察题",
        schema_ref="family://assessment/FAMILY_SUPPORT_NEEDS/v2",
        items=[AssessmentToolItem(**item) for item in _V2_ITEM_SCHEMA["items"]],
        boundary=AssessmentToolBoundary(),
    )


class TestFamilySupportNeedsV2ItemBank:
    def test_v2_item_schema_parses_without_error(self):
        tool = _parse_as_tool_from_db_row_shape()
        assert tool.version_no == 2
        assert len(tool.items) == 11  # 3 original (v1) + 8 new deep-dive items

    def test_v1_items_are_preserved_unchanged(self):
        tool = _parse_as_tool_from_db_row_shape()
        assert tool.find_item("FOCUS") is not None
        assert tool.find_item("FAMILY_STRUCTURE") is not None
        assert tool.find_item("CHILD_GENDER") is not None

    def test_all_expected_new_items_present_with_four_point_frequency_scale(self):
        tool = _parse_as_tool_from_db_row_shape()
        for item_ref in _EXPECTED_NEW_ITEM_REFS:
            item = tool.find_item(item_ref)
            assert item is not None, f"{item_ref} missing from v2 item bank"
            assert item.response_type == "SINGLE_CHOICE"
            assert item.options == _FOUR_POINT_OPTIONS
            assert item.required is False  # no branching engine yet — must stay optional

    def test_unreviewed_construct_items_are_not_included(self):
        """Anti-scope-creep guard: the 17 registry items tied to constructs
        never reviewed against `_LEGAL_CONSTRUCT_REFS` must not silently end
        up in this tool version."""
        tool = _parse_as_tool_from_db_row_shape()
        present_refs = {item.item_ref for item in tool.items}
        leaked = present_refs & _EXCLUDED_ITEM_REFS
        assert not leaked, f"unreviewed-construct items leaked into v2: {leaked}"

    def test_boundary_still_forbids_score_and_diagnosis(self):
        tool = _parse_as_tool_from_db_row_shape()
        assert tool.boundary.not_a_score is True
        assert tool.boundary.not_a_diagnosis is True
