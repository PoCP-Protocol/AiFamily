"""Port of `assertInterpretationBoundary` / `assertNoForbiddenOutputFields`
(`packages/family-model/src/index.ts`). Fail-closed structural validation of
any AI-generated interpretation draft — applies identically whether the
draft came from `DeterministicInterpretationAdapter` or a real model call
(`ClaudeInterpretationAdapter`). Per migration plan section 10, this
guarantee must be preserved, not weakened, in the Python port.

Four checks, all must pass or this raises:
1. Field-name blacklist: no key anywhere in the output may match
   total_score/ranking/diagnosis (case-insensitive), recursively.
2. Structural boundary literals: every construct_signal/hypothesis/
   action_candidate must carry its fixed boundary literal
   (signal_not_diagnosis / hypothesis_not_fact / recommendation_not_decision).
3. Construct-ref whitelist: every construct_ref referenced anywhere must be
   in the reviewed registry — this is what stopped the 2026-08-26 incident
   where a model fabricated PARENT_CHILD_COMMUNICATION_QUALITY and
   COMMUNICATION_RESPECT_TURN_TAKING (neither ever passed human review).
4. Primary-contradiction cardinality: at most 3 hypotheses in the draft may
   carry `is_primary_contradiction=True`. Per
   architecture/FAMILY_COMMERCIAL_VALUE_STRATEGY_V2.md section 8.3/8.4, the
   point of this field is to force a small, decidable set of "what to break
   through right now" — not another ranked list of everything. WHICH
   hypothesis is primary is a judgment call left to the adapter / model;
   this function only enforces the count is small enough that "primary"
   still means something.
"""
from __future__ import annotations

import re
from typing import Any

from .errors import AssessmentValidationError

_FORBIDDEN_FIELD_PATTERN = re.compile(r"(?:total_?score|ranking|diagnosis)", re.IGNORECASE)


def assert_no_forbidden_output_fields(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, sub_value in value.items():
            if key != "prohibited_outputs" and _FORBIDDEN_FIELD_PATTERN.search(str(key)):
                raise AssessmentValidationError(f"forbidden_output_field:{path}.{key}")
            assert_no_forbidden_output_fields(sub_value, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert_no_forbidden_output_fields(item, f"{path}[{index}]")


def assert_interpretation_boundary(draft: dict, legal_construct_refs: set[str]) -> dict:
    assert_no_forbidden_output_fields(draft)

    boundary_labels = draft.get("boundary_labels", [])
    if "hypothesis_not_fact" not in boundary_labels:
        raise AssessmentValidationError("missing_hypothesis_not_fact_boundary")
    if "recommendation_not_decision" not in boundary_labels:
        raise AssessmentValidationError("missing_recommendation_not_decision_boundary")

    for signal in draft.get("construct_signals", []):
        if signal.get("boundary") != "signal_not_diagnosis":
            raise AssessmentValidationError("construct_signal_missing_boundary")
        if signal.get("construct_ref") not in legal_construct_refs:
            raise AssessmentValidationError(f"construct_ref_not_in_reviewed_registry:{signal.get('construct_ref')}")

    primary_contradiction_count = 0
    for hypothesis in draft.get("hypotheses", []):
        if hypothesis.get("boundary") != "hypothesis_not_fact":
            raise AssessmentValidationError("hypothesis_missing_boundary")
        for construct_ref in hypothesis.get("construct_refs", []):
            if construct_ref not in legal_construct_refs:
                raise AssessmentValidationError(f"construct_ref_not_in_reviewed_registry:{construct_ref}")
        if hypothesis.get("is_primary_contradiction"):
            primary_contradiction_count += 1

    # "1 to 3 key contradictions" (FAMILY_COMMERCIAL_VALUE_STRATEGY_V2.md §8.3/8.4)
    # is a structural cardinality invariant of the SAME kind the boundary literal
    # checks above already enforce fail-closed — not a business-judgment call this
    # function has any opinion on (which hypothesis is primary is left entirely to
    # the caller / model). Enforcing "at most 3" here, at the shared choke point
    # both adapters pass through, is cheaper and harder to bypass than expecting
    # every future caller to re-derive and check this count itself.
    if primary_contradiction_count > 3:
        raise AssessmentValidationError(f"too_many_primary_contradictions:{primary_contradiction_count}")

    for action_candidate in draft.get("action_candidates", []):
        if action_candidate.get("boundary") != "recommendation_not_decision":
            raise AssessmentValidationError("action_candidate_missing_boundary")
        # action_ref itself has no whitelist check — port of the TS behavior
        # (recommended_action_map is not checked there either), not an
        # oversight introduced in this port.

    return draft
