"""FAMILY_SUPPORT_NEEDS v3+v4: register the construct-admission-reviewed
18-item bank as the new active assessment tool version.

`family_assessment_tools` already carries v1 (3-option `FOCUS`, legacy
baseline 0043) and v2 (`database/baseline/0047_ui02_family_assessment_ai_capability_memory.sql`,
5-option `FOCUS` + deep questions across five dimensions). Both are historical
baseline snapshots this repository does not edit byte-for-byte (see
`tests/database/test_baseline_linearisation.py`).

v2, however, carries `EMOTION_REGULATION_Q01` and (in a since-abandoned v3
draft) `PARENT_CAPACITY_PRESSURE` — both flagged `safety_boundary:
human_gate_if_crisis_signal` / `human_gate_if_parent_crisis` in the
construct-admission review that produced
`tests/domains/assessment/test_family_support_needs_v3_item_bank.py` and
`test_family_support_needs_v4_item_bank.py` (their docstrings are the audit
trail for this exclusion — no `governance/CONSTRUCT_ADMISSION_REGISTRY.yaml`
file exists yet to hold it structurally, which is a separate, still-open
governance gap this migration does not attempt to close). Those two items
route to a Human Gate that no code enforces yet; serving them to a family
with no human in the loop is the exact risk the review exists to prevent.

This migration inserts v3 (14 items: v1's three plus 11 already-admitted
deep questions, still excluding both crisis-flagged items) and v4 (18 items:
v3 plus `LEARNING_HABITS_Q02` and `SELF_REGULATION_Q01-03`, admitted in a
second construct-admission batch) as new, additional rows — v1/v2 are left
untouched, and `load_active_tool`'s `order by version_no desc limit 1` means
v4 becomes what every *new* session actually uses without deleting or
rewriting history. `FakeAssessmentRepository.default_tool()` (the in-memory
test double `backend/apps/family_api/dev_wiring.py` serves in dev) is updated
to match this same v4 item set in the same change that adds this migration,
so dev/test and real Postgres serve the same tool content — this is the fix
for the mobile UI-02 screen (`frontend/mobile/app/ui/UI-02.tsx`, whose real
design already answers `FOCUS` with one of the five dimension ids and
answers deep questions with `often`/`sometimes`/`rarely`/`not_sure`) failing
every real submission with `assessment_choice_not_in_tool_version` /
`assessment_item_contract_mismatch` against the old 3-option v1-shaped stub.

Revision ID: 0067_family_support_needs_v4_item_bank
Revises: 0066_fgcn_provider_qualification_fields
Create Date: 2026-09-07
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "0067_family_support_needs_v4_item_bank"
down_revision: str | None = "0066_fgcn_provider_qualification_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FOUR_POINT_OPTIONS = ["often", "sometimes", "rarely", "not_sure"]

_FOCUS_OPTIONS = [
    "LEARNING_HABITS",
    "EMOTION_REGULATION",
    "PARENT_CHILD_COMMUNICATION",
    "DEVICE_USE_CONTEXT",
    "SELF_REGULATION",
]

_BASE_ITEMS = [
    {
        "item_ref": "FOCUS",
        "response_type": "SINGLE_CHOICE",
        "required": True,
        "options": _FOCUS_OPTIONS,
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
]


def _q(item_ref: str) -> dict:
    return {
        "item_ref": item_ref,
        "response_type": "SINGLE_CHOICE",
        "required": False,
        "options": _FOUR_POINT_OPTIONS,
    }


# v3: base items + already-admitted Batch 1 deep questions, excluding both
# crisis-flagged items (EMOTION_REGULATION_Q01, PARENT_CAPACITY_PRESSURE).
_V3_ITEMS = [
    *_BASE_ITEMS,
    _q("LEARNING_HABITS_Q01"),
    _q("LEARNING_HABITS_Q03"),
    _q("PARENT_CHILD_COMMUNICATION_Q01"),
    _q("PARENT_CHILD_COMMUNICATION_Q02"),
    _q("PARENT_CHILD_COMMUNICATION_Q03"),
    _q("DEVICE_USE_CONTEXT_Q01"),
    _q("DEVICE_USE_CONTEXT_Q02"),
    _q("DEVICE_USE_CONTEXT_Q03"),
    _q("EMOTION_REGULATION_Q02"),
    _q("EMOTION_REGULATION_Q03"),
    _q("SCHOOL_FAMILY_FEEDBACK_LOOP"),
]

# v4: v3 plus Batch 2's four newly admitted items.
_V4_ITEMS = [
    *_V3_ITEMS,
    _q("LEARNING_HABITS_Q02"),
    _q("SELF_REGULATION_Q01"),
    _q("SELF_REGULATION_Q02"),
    _q("SELF_REGULATION_Q03"),
]

_BOUNDARY = {
    "truth_class": "FAMILY_PERSPECTIVE",
    "not_a_score": True,
    "not_a_diagnosis": True,
    "no_eligibility_effect": True,
    "withdrawable": True,
    "training_use": False,
}

_INSERT_SQL = text(
    """
    insert into family_assessment_tools(
      tool_ref, version_no, title, purpose, status, admission_status,
      evidence_level, schema_ref, item_schema, boundary, effective_from
    ) values (
      :tool_ref, :version_no, :title, :purpose, 'ACTIVE', 'ADMITTED',
      'E1', :schema_ref, :item_schema, :boundary, now()
    ) on conflict (tool_ref, version_no) do nothing
    """
)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        _INSERT_SQL,
        {
            "tool_ref": "FAMILY_SUPPORT_NEEDS",
            "version_no": 3,
            "title": "家庭支持需要与服务偏好确认(含深挖题·批次1扩容)",
            "purpose": "在v2基础上，针对已通过构念审核的情绪调节/学校协作方向追加观察题，"
            "危机类信号题(EMOTION_REGULATION_Q01)在人工闸门落地前继续排除",
            "schema_ref": "family://assessment/FAMILY_SUPPORT_NEEDS/v3",
            "item_schema": json.dumps({"items": _V3_ITEMS}),
            "boundary": json.dumps(_BOUNDARY),
        },
    )
    bind.execute(
        _INSERT_SQL,
        {
            "tool_ref": "FAMILY_SUPPORT_NEEDS",
            "version_no": 4,
            "title": "家庭支持需要与服务偏好确认(含深挖题·批次2扩容)",
            "purpose": "在v3基础上，针对学习策略/元认知与自我管理支持两个新审核通过的方向"
            "追加观察题",
            "schema_ref": "family://assessment/FAMILY_SUPPORT_NEEDS/v4",
            "item_schema": json.dumps({"items": _V4_ITEMS}),
            "boundary": json.dumps(_BOUNDARY),
        },
    )


def downgrade() -> None:
    op.execute(
        "delete from family_assessment_tools "
        "where tool_ref = 'FAMILY_SUPPORT_NEEDS' and version_no in (3, 4)"
    )
