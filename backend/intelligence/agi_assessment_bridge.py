"""Map existing FamilyNeed/Assessment evidence into the Experience draft DTO.

The bridge is intentionally a pure adapter: it does not call a provider, write
assessment facts, or create a second ledger.  Its output can be supplied to the
existing multimodal draft route and durable run ledger.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.intelligence.agi_vertical_runtime import FamilyGrowthContext


def build_vertical_draft_input(
    context: FamilyGrowthContext,
    *,
    family_need_id: str,
    path_id: str,
    run_id: str,
    assessment_evidence: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Return ``(payload, input_refs)`` for the existing Experience route.

    Assessment references remain evidence/source references.  They are not
    promoted to facts or diagnoses.  Correlation keys are repeated in the
    payload so the durable run replay can prove one need/path/run chain.
    """

    if context.family_id != context.values.get("family_id", context.family_id):
        raise ValueError("CONTEXT_FAMILY_SCOPE_MISMATCH")
    if not all((family_need_id, path_id, run_id, context.context_snapshot_ref)):
        raise ValueError("VERTICAL_CORRELATION_REQUIRED")

    payload: dict[str, Any] = {
        "family_need_id": family_need_id,
        "path_id": path_id,
        "run_id": run_id,
        "family_context": dict(context.values),
        "output_semantics": "UNDERSTANDING_DRAFT_NOT_DIAGNOSIS",
        "requires_human_confirmation": True,
    }
    refs = [family_need_id, path_id, run_id, context.context_snapshot_ref]
    if assessment_evidence is not None:
        evidence_refs = tuple(
            str(assessment_evidence[key])
            for key in (
                "assessment_session_id",
                "assessment_response_id",
                "assessment_evidence_id",
                "tool_ref",
            )
            if assessment_evidence.get(key)
        )
        if not evidence_refs:
            raise ValueError("ASSESSMENT_EVIDENCE_REFS_REQUIRED")
        payload["assessment_evidence"] = {
            "source_refs": evidence_refs,
            "focus_ref": assessment_evidence.get("focus_ref"),
            "response_set": assessment_evidence.get("response_set", []),
            "boundary": "HYPOTHESIS_NOT_FACT_OR_DIAGNOSIS",
        }
        refs.extend(evidence_refs)
    return payload, tuple(dict.fromkeys(refs))


__all__ = ["build_vertical_draft_input"]
