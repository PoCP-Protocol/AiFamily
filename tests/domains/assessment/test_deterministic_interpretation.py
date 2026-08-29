"""Unit tests for `DeterministicInterpretationAdapter` — no external call.
Focus of this file: the hypothesis item shape must stay a structural mirror
of `ClaudeInterpretationAdapter`'s output (see both adapters' module
docstrings — "same shape... application layer doesn't need to know which
adapter is behind the port"), including the `is_primary_contradiction` /
`contradiction_rank` fields added for the primary-contradiction method
(architecture/FAMILY_COMMERCIAL_VALUE_STRATEGY_V2.md section 8.3/8.4).
"""

from __future__ import annotations

import pytest

from backend.domains.assessment.domain.entities import GrowthHypothesisEvidence
from backend.domains.assessment.domain.interpretation_boundary import assert_interpretation_boundary
from backend.domains.assessment.infrastructure.deterministic_interpretation import (
    DeterministicInterpretationAdapter,
)

_LEGAL_CONSTRUCT_REFS = {
    "PARENT_CHILD_COMMUNICATION",
    "HOMEWORK_PROCESS",
    "DEVICE_USE_CONTEXT",
}


def _evidence(focus_ref: str = "COMMUNICATION") -> GrowthHypothesisEvidence:
    return GrowthHypothesisEvidence(
        assessment_session_id="sess-1",
        subject_person_id="child-1",
        subject_display_name="小明",
        submitted_at=None,
        tool_ref="FAMILY_SUPPORT_NEEDS",
        tool_version=1,
        assessment_response_id="resp-1",
        focus_ref=focus_ref,
        assessment_evidence_id="ev-1",
        need_type_ref="PARENT_CHILD_COMMUNICATION_CONFLICT",
        need_type_version=1,
        title="亲子沟通支持",
        description="先从倾听开始",
        required_capability_keys=["CAP_PARENT_COACHING"],
        response_set=[
            {"item_ref": "FOCUS", "response_type": "SINGLE_CHOICE", "response_value": focus_ref}
        ],
    )


class TestDeterministicInterpretationAdapter:
    async def test_single_hypothesis_is_marked_primary_contradiction_rank_one(self):
        adapter = DeterministicInterpretationAdapter()

        result = await adapter.interpret("family-1", _evidence(), "DEEP_AI_INTERPRETATION")

        draft = result["interpretation"]["draft"]
        assert len(draft["hypotheses"]) == 1
        hypothesis = draft["hypotheses"][0]
        assert hypothesis["is_primary_contradiction"] is True
        assert hypothesis["contradiction_rank"] == 1

    async def test_hypothesis_item_shape_matches_claude_adapter_required_fields(self):
        """The fallback and live adapters must agree on the hypothesis item
        keys — this is the "two adapters, one shape" invariant both modules'
        docstrings describe. Enumerated here explicitly so a future change
        to either adapter's hypothesis shape without updating the other
        fails this test, not silently at the application layer.
        """
        adapter = DeterministicInterpretationAdapter()

        result = await adapter.interpret("family-1", _evidence())

        hypothesis = result["interpretation"]["draft"]["hypotheses"][0]
        assert set(hypothesis.keys()) == {
            "hypothesis_ref",
            "boundary",
            "construct_refs",
            "is_primary_contradiction",
            "contradiction_rank",
        }

    async def test_deterministic_draft_passes_interpretation_boundary_validation(self):
        """The deterministic draft, including its new primary-contradiction
        fields, must pass the exact same fail-closed gate the live adapter's
        output is re-validated against (see ClaudeInterpretationAdapter's
        module docstring: "the SAME check DeterministicInterpretationAdapter's
        output would need to pass if it were re-validated").
        """
        adapter = DeterministicInterpretationAdapter()

        result = await adapter.interpret("family-1", _evidence())

        draft = result["interpretation"]["draft"]
        assert_interpretation_boundary(draft, _LEGAL_CONSTRUCT_REFS)  # does not raise

    @pytest.mark.parametrize(
        "focus_ref", ["COMMUNICATION", "HOMEWORK", "SCREEN_TIME", "UNKNOWN_FOCUS"]
    )
    async def test_deterministic_draft_passes_boundary_regardless_of_focus(self, focus_ref):
        adapter = DeterministicInterpretationAdapter()

        result = await adapter.interpret("family-1", _evidence(focus_ref))

        draft = result["interpretation"]["draft"]
        assert_interpretation_boundary(draft, _LEGAL_CONSTRUCT_REFS)  # does not raise
