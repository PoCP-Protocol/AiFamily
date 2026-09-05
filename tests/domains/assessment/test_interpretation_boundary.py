"""Unit tests for `assert_interpretation_boundary` — port of
`assertInterpretationBoundary`'s test surface. Includes a direct
reproduction of the 2026-08-26 incident this guard exists to prevent
(model fabricating an unreviewed construct_ref).
"""

from __future__ import annotations

import pytest

from backend.domains.assessment.domain.errors import AssessmentValidationError
from backend.domains.assessment.domain.interpretation_boundary import assert_interpretation_boundary

LEGAL_REFS = {"PARENT_CHILD_COMMUNICATION", "HOMEWORK_PROCESS", "DEVICE_USE_CONTEXT"}


def _valid_draft() -> dict:
    return {
        "boundary_labels": ["hypothesis_not_fact", "recommendation_not_decision"],
        "construct_signals": [
            {"construct_ref": "PARENT_CHILD_COMMUNICATION", "boundary": "signal_not_diagnosis"}
        ],
        "hypotheses": [
            {
                "hypothesis_ref": "H1",
                "boundary": "hypothesis_not_fact",
                "construct_refs": ["PARENT_CHILD_COMMUNICATION"],
                "is_primary_contradiction": True,
                "contradiction_rank": 1,
            }
        ],
        "action_candidates": [
            {"action_ref": "SUPPORT_ACTION", "boundary": "recommendation_not_decision"}
        ],
        "prohibited_outputs": [],
    }


class TestInterpretationBoundary:
    def test_valid_draft_passes_through_unmodified(self):
        draft = _valid_draft()
        result = assert_interpretation_boundary(draft, LEGAL_REFS)
        assert result == draft

    def test_fabricated_construct_ref_is_rejected(self):
        """Direct reproduction of the 2026-08-26 incident: the model
        fabricated PARENT_CHILD_COMMUNICATION_QUALITY, which was never
        reviewed. This must raise, not pass through.
        """
        draft = _valid_draft()
        draft["construct_signals"][0]["construct_ref"] = "PARENT_CHILD_COMMUNICATION_QUALITY"
        with pytest.raises(AssessmentValidationError) as exc:
            assert_interpretation_boundary(draft, LEGAL_REFS)
        assert "construct_ref_not_in_reviewed_registry" in exc.value.code

    def test_fabricated_construct_ref_in_hypothesis_is_also_rejected(self):
        draft = _valid_draft()
        draft["hypotheses"][0]["construct_refs"] = ["COMMUNICATION_RESPECT_TURN_TAKING"]
        with pytest.raises(AssessmentValidationError) as exc:
            assert_interpretation_boundary(draft, LEGAL_REFS)
        assert "construct_ref_not_in_reviewed_registry" in exc.value.code

    def test_missing_hypothesis_not_fact_label_is_rejected(self):
        draft = _valid_draft()
        draft["boundary_labels"] = ["recommendation_not_decision"]
        with pytest.raises(AssessmentValidationError) as exc:
            assert_interpretation_boundary(draft, LEGAL_REFS)
        assert exc.value.code == "missing_hypothesis_not_fact_boundary"

    def test_missing_recommendation_not_decision_label_is_rejected(self):
        draft = _valid_draft()
        draft["boundary_labels"] = ["hypothesis_not_fact"]
        with pytest.raises(AssessmentValidationError) as exc:
            assert_interpretation_boundary(draft, LEGAL_REFS)
        assert exc.value.code == "missing_recommendation_not_decision_boundary"

    def test_construct_signal_with_wrong_boundary_literal_is_rejected(self):
        draft = _valid_draft()
        draft["construct_signals"][0]["boundary"] = "signal_confirmed"  # not a real literal
        with pytest.raises(AssessmentValidationError) as exc:
            assert_interpretation_boundary(draft, LEGAL_REFS)
        assert exc.value.code == "construct_signal_missing_boundary"

    def test_hypothesis_with_wrong_boundary_literal_is_rejected(self):
        draft = _valid_draft()
        draft["hypotheses"][0]["boundary"] = "confirmed_fact"
        with pytest.raises(AssessmentValidationError) as exc:
            assert_interpretation_boundary(draft, LEGAL_REFS)
        assert exc.value.code == "hypothesis_missing_boundary"

    def test_action_candidate_with_wrong_boundary_literal_is_rejected(self):
        draft = _valid_draft()
        draft["action_candidates"][0]["boundary"] = "final_decision"
        with pytest.raises(AssessmentValidationError) as exc:
            assert_interpretation_boundary(draft, LEGAL_REFS)
        assert exc.value.code == "action_candidate_missing_boundary"

    @pytest.mark.parametrize(
        "forbidden_key", ["total_score", "TotalScore", "ranking", "diagnosis", "family_diagnosis"]
    )
    def test_forbidden_field_names_are_rejected_anywhere_in_the_tree(self, forbidden_key):
        draft = _valid_draft()
        draft["construct_signals"][0][forbidden_key] = 42  # smuggled into a nested object
        with pytest.raises(AssessmentValidationError) as exc:
            assert_interpretation_boundary(draft, LEGAL_REFS)
        assert "forbidden_output_field" in exc.value.code

    def test_prohibited_outputs_key_itself_is_exempt_from_the_blacklist(self):
        """The field name 'prohibited_outputs' would otherwise match nothing
        in the blacklist regex, but this test documents that the exemption
        exists intentionally (mirrors the TS `!== 'prohibited_outputs'` check).
        """
        draft = _valid_draft()
        draft["prohibited_outputs"] = ["ranking"]  # a string VALUE, not a key — always fine
        assert_interpretation_boundary(draft, LEGAL_REFS)  # does not raise

    def test_up_to_three_primary_contradictions_are_allowed(self):
        draft = _valid_draft()
        base = draft["hypotheses"][0]
        draft["hypotheses"] = [
            {
                **base,
                "hypothesis_ref": f"H{i}",
                "contradiction_rank": i,
                "is_primary_contradiction": True,
            }
            for i in range(1, 4)
        ]
        assert_interpretation_boundary(draft, LEGAL_REFS)  # does not raise

    def test_more_than_three_primary_contradictions_is_rejected(self):
        draft = _valid_draft()
        base = draft["hypotheses"][0]
        draft["hypotheses"] = [
            {
                **base,
                "hypothesis_ref": f"H{i}",
                "contradiction_rank": i,
                "is_primary_contradiction": True,
            }
            for i in range(1, 5)
        ]
        with pytest.raises(AssessmentValidationError) as exc:
            assert_interpretation_boundary(draft, LEGAL_REFS)
        assert exc.value.code == "too_many_primary_contradictions:4"

    def test_zero_primary_contradictions_is_allowed(self):
        """is_primary_contradiction is optional-in-spirit (default false) —
        a draft where every hypothesis is secondary is structurally valid;
        this function has no opinion on WHETHER a primary contradiction was
        identified, only on the upper bound.
        """
        draft = _valid_draft()
        draft["hypotheses"][0]["is_primary_contradiction"] = False
        draft["hypotheses"][0]["contradiction_rank"] = None
        assert_interpretation_boundary(draft, LEGAL_REFS)  # does not raise

    def test_action_ref_has_no_whitelist_check(self):
        """Documents parity with the TS behavior: action_ref is NOT checked
        against any whitelist (recommended_action_map), unlike construct_ref.
        This is intentional parity, not a gap introduced by this port.
        """
        draft = _valid_draft()
        draft["action_candidates"][0]["action_ref"] = "SOME_COMPLETELY_MADE_UP_ACTION_REF"
        assert_interpretation_boundary(draft, LEGAL_REFS)  # does not raise
