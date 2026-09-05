"""Content-fidelity test for migration 0047
(`FAMILY_SUPPORT_NEEDS` v3 — Batch 1 construct admission items) — no real
Postgres needed.

Batch 1 admitted EMOTION_REGULATION_SUPPORT / PARENT_CAPACITY /
SCHOOL_FAMILY_COLLABORATION into `_LEGAL_CONSTRUCT_REFS`
(governance/CONSTRUCT_ADMISSION_REGISTRY.yaml). This unlocked
EMOTION_REGULATION_Q02/Q03 and SCHOOL_FAMILY_FEEDBACK_LOOP — but NOT
EMOTION_REGULATION_Q01 or PARENT_CAPACITY_PRESSURE, both flagged
`safety_boundary: human_gate_if_crisis_signal` / `human_gate_if_parent_crisis`
in the registry with no code anywhere enforcing that gate yet. Admitting a
construct is not the same as clearing every item tagged with it — this test
exists specifically to catch the case where someone later "helpfully" adds
those two crisis-flagged items back in without first closing the
safety_boundary routing gap.
"""

from __future__ import annotations

from backend.domains.assessment.domain.value_objects import (
    AssessmentTool,
    AssessmentToolBoundary,
    AssessmentToolItem,
)

_FOUR_POINT_OPTIONS = ["often", "sometimes", "rarely", "not_sure"]

_V3_ITEM_SCHEMA = {
    "items": [
        {
            "item_ref": "FOCUS",
            "response_type": "SINGLE_CHOICE",
            "required": True,
            "options": [
                "LEARNING_HABITS",
                "EMOTION_REGULATION",
                "PARENT_CHILD_COMMUNICATION",
                "DEVICE_USE_CONTEXT",
                "SELF_REGULATION",
            ],
        },
        {
            "item_ref": "FAMILY_STRUCTURE",
            "response_type": "SINGLE_CHOICE",
            "required": False,
            "options": ["TWO_PARENT", "SINGLE_PARENT", "BLENDED", "PREFER_NOT_TO_SAY"],
        },
        {
            "item_ref": "CHILD_GENDER",
            "response_type": "SINGLE_CHOICE",
            "required": False,
            "options": ["BOY", "GIRL", "SELF_DESCRIBED", "PREFER_NOT_TO_SAY"],
        },
        {
            "item_ref": "LEARNING_HABITS_Q01",
            "response_type": "SINGLE_CHOICE",
            "required": False,
            "options": _FOUR_POINT_OPTIONS,
        },
        {
            "item_ref": "LEARNING_HABITS_Q03",
            "response_type": "SINGLE_CHOICE",
            "required": False,
            "options": _FOUR_POINT_OPTIONS,
        },
        {
            "item_ref": "PARENT_CHILD_COMMUNICATION_Q01",
            "response_type": "SINGLE_CHOICE",
            "required": False,
            "options": _FOUR_POINT_OPTIONS,
        },
        {
            "item_ref": "PARENT_CHILD_COMMUNICATION_Q02",
            "response_type": "SINGLE_CHOICE",
            "required": False,
            "options": _FOUR_POINT_OPTIONS,
        },
        {
            "item_ref": "PARENT_CHILD_COMMUNICATION_Q03",
            "response_type": "SINGLE_CHOICE",
            "required": False,
            "options": _FOUR_POINT_OPTIONS,
        },
        {
            "item_ref": "DEVICE_USE_CONTEXT_Q01",
            "response_type": "SINGLE_CHOICE",
            "required": False,
            "options": _FOUR_POINT_OPTIONS,
        },
        {
            "item_ref": "DEVICE_USE_CONTEXT_Q02",
            "response_type": "SINGLE_CHOICE",
            "required": False,
            "options": _FOUR_POINT_OPTIONS,
        },
        {
            "item_ref": "DEVICE_USE_CONTEXT_Q03",
            "response_type": "SINGLE_CHOICE",
            "required": False,
            "options": _FOUR_POINT_OPTIONS,
        },
        {
            "item_ref": "EMOTION_REGULATION_Q02",
            "response_type": "SINGLE_CHOICE",
            "required": False,
            "options": _FOUR_POINT_OPTIONS,
        },
        {
            "item_ref": "EMOTION_REGULATION_Q03",
            "response_type": "SINGLE_CHOICE",
            "required": False,
            "options": _FOUR_POINT_OPTIONS,
        },
        {
            "item_ref": "SCHOOL_FAMILY_FEEDBACK_LOOP",
            "response_type": "SINGLE_CHOICE",
            "required": False,
            "options": _FOUR_POINT_OPTIONS,
        },
    ]
}

_EXPECTED_NEW_ITEM_REFS = {
    "EMOTION_REGULATION_Q02",
    "EMOTION_REGULATION_Q03",
    "SCHOOL_FAMILY_FEEDBACK_LOOP",
}

# Crisis-flagged items whose PRIMARY construct is admitted but whose own
# safety_boundary tag (human_gate_if_crisis_signal / human_gate_if_parent_crisis)
# has no enforcing code yet — must never appear despite construct admission.
_CRISIS_FLAGGED_ITEM_REFS = {"EMOTION_REGULATION_Q01", "PARENT_CAPACITY_PRESSURE"}

# Items whose constructs remain HOLD in governance/CONSTRUCT_ADMISSION_REGISTRY.yaml.
_UNREVIEWED_CONSTRUCT_ITEM_REFS = {
    "SELF_REGULATION_Q01",
    "SELF_REGULATION_Q02",
    "SELF_REGULATION_Q03",
    "CHILD_ERROR_REVIEW_PATTERN",
    "SLEEP_ENERGY_LEARNING_IMPACT",
    "AI_LEARNING_USE_CLARITY",
    "MULTIMODAL_CREATION_OPPORTUNITY",
    "PARENT_CHILD_TALK_INTERRUPTION",
    "CHILD_WILLINGNESS_TO_TALK",
}


def _parse_as_tool_from_db_row_shape() -> AssessmentTool:
    """Mirrors `sqlalchemy_repository._map_tool_row()` field-for-field, minus
    the DB round-trip — same Pydantic construction path a real load would hit.
    """
    return AssessmentTool(
        tool_ref="FAMILY_SUPPORT_NEEDS",
        version_no=3,
        title="家庭支持需要与服务偏好确认(含深挖题·批次1扩容)",
        purpose="在v2基础上,针对情绪调节支持/家长自身容量/学校家庭协同三个新审核通过的方向追加观察题",
        schema_ref="family://assessment/FAMILY_SUPPORT_NEEDS/v3",
        items=[AssessmentToolItem(**item) for item in _V3_ITEM_SCHEMA["items"]],
        boundary=AssessmentToolBoundary(),
    )


class TestFamilySupportNeedsV3ItemBank:
    def test_v3_item_schema_parses_without_error(self):
        tool = _parse_as_tool_from_db_row_shape()
        assert tool.version_no == 3
        assert len(tool.items) == 14  # 11 (v2) + 3 new Batch-1 items

    def test_v2_items_are_preserved_unchanged(self):
        tool = _parse_as_tool_from_db_row_shape()
        for item_ref in [
            "FOCUS",
            "FAMILY_STRUCTURE",
            "CHILD_GENDER",
            "LEARNING_HABITS_Q01",
            "PARENT_CHILD_COMMUNICATION_Q01",
            "DEVICE_USE_CONTEXT_Q01",
        ]:
            assert tool.find_item(item_ref) is not None

    def test_new_batch1_items_present_with_four_point_frequency_scale(self):
        tool = _parse_as_tool_from_db_row_shape()
        for item_ref in _EXPECTED_NEW_ITEM_REFS:
            item = tool.find_item(item_ref)
            assert item is not None, f"{item_ref} missing from v3 item bank"
            assert item.response_type == "SINGLE_CHOICE"
            assert item.options == _FOUR_POINT_OPTIONS
            assert item.required is False

    def test_crisis_flagged_items_excluded_despite_construct_admission(self):
        """The key regression this test guards: EMOTION_REGULATION_SUPPORT and
        PARENT_CAPACITY are both ADMITTED constructs, but EMOTION_REGULATION_Q01
        and PARENT_CAPACITY_PRESSURE specifically carry a human_gate_* safety
        boundary the code doesn't enforce yet — admitting the construct must
        not be mistaken for clearing every item tagged with it."""
        tool = _parse_as_tool_from_db_row_shape()
        present_refs = {item.item_ref for item in tool.items}
        leaked = present_refs & _CRISIS_FLAGGED_ITEM_REFS
        assert not leaked, (
            f"crisis-flagged items leaked into v3 without a human-gate mechanism: {leaked}"
        )

    def test_unreviewed_construct_items_still_excluded(self):
        tool = _parse_as_tool_from_db_row_shape()
        present_refs = {item.item_ref for item in tool.items}
        leaked = present_refs & _UNREVIEWED_CONSTRUCT_ITEM_REFS
        assert not leaked, f"unreviewed-construct items leaked into v3: {leaked}"

    def test_boundary_still_forbids_score_and_diagnosis(self):
        tool = _parse_as_tool_from_db_row_shape()
        assert tool.boundary.not_a_score is True
        assert tool.boundary.not_a_diagnosis is True
