"""Unknown Engine (AIFAMILY-WM-004C).

Two halves, deliberately separated the same way `belief_engine.py` is:

1. **Deterministic**: `compute_information_value()` and `rank_unknowns()`
   need no model at all — given an `UnknownState` and its impact/
   answerability/urgency bands, the priority score is a fixed formula.
   This is most of what this engine does day to day.
2. **Generative, gated**: `generate_unknown()` lets a model *propose* a
   candidate Unknown from the current hypotheses/conflicts, but per
   ADR-0172 every proposal is re-validated deterministically before
   becoming a real `UnknownState` — scope, subject membership, referenced
   hypothesis existence, and duplicate-question detection all run in this
   module, not in the model.

`UnknownState` itself is unchanged from WM-001 (`world_state.py`) — Unknown
was already a first-class object; this module is what actually produces and
ranks instances of it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from backend.intelligence.model_gateway.contracts import ModelDraft, StructuredRequest
from backend.intelligence.model_gateway.gateway import ModelGateway

from .contracts import ContextContractError, ContextScope
from .world_state import UncertaintyBand, UnknownState, UnknownStatus, WorldStateAtom

UNKNOWN_USE_CASE = "family_world_state.unknown_generation"
UNKNOWN_PROMPT_VERSION = "world-model-unknown-engine/v1"
UNKNOWN_SCHEMA_VERSION = "world-model-unknown-engine/v1"


class ImpactBand(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AnswerabilityBand(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class UrgencyBand(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


_THREE_TIER_WEIGHT = {"LOW": 0.2, "MEDIUM": 0.5, "HIGH": 0.9}
#: Uncertainty is inverted: HIGH uncertainty makes an Unknown *more* worth
#: resolving (there is more to learn), unlike confidence in belief_engine.py
#: where HIGH uncertainty discounts toward the neutral midpoint.
_UNCERTAINTY_WEIGHT = {
    UncertaintyBand.LOW: 0.2,
    UncertaintyBand.MEDIUM: 0.5,
    UncertaintyBand.HIGH: 0.9,
}


@dataclass(frozen=True, slots=True)
class InformationValueInputs:
    decision_impact: ImpactBand
    uncertainty: UncertaintyBand
    answerability: AnswerabilityBand
    urgency: UrgencyBand


def compute_information_value(inputs: InformationValueInputs) -> float:
    """`decision_impact x uncertainty x answerability x urgency`, each
    factor mapped to a fixed {LOW:0.2, MEDIUM:0.5, HIGH:0.9} weight — a
    product of four categorical bands, not a calibrated probability. This
    is deliberately coarse (max score 0.9^4 ~= 0.656, min ~= 0.0016): V1 has
    no data to justify finer precision, matching the same discipline as
    `belief_engine.derive_confidence`.
    """

    return (
        _THREE_TIER_WEIGHT[inputs.decision_impact.value]
        * _UNCERTAINTY_WEIGHT[inputs.uncertainty]
        * _THREE_TIER_WEIGHT[inputs.answerability.value]
        * _THREE_TIER_WEIGHT[inputs.urgency.value]
    )


def rank_unknowns(
    unknowns_with_inputs: Sequence[tuple[UnknownState, InformationValueInputs]],
) -> tuple[UnknownState, ...]:
    """Highest information value first — "which question is most worth
    asking next", not an arbitrary or creation-order list. Ties break by
    `unknown_id` for determinism (never by insertion order, which is not a
    stable property once these are persisted and re-read)."""

    ranked = sorted(
        unknowns_with_inputs,
        key=lambda pair: (-compute_information_value(pair[1]), pair[0].unknown_id),
    )
    return tuple(unknown for unknown, _inputs in ranked)


def unknown_output_schema() -> dict[str, object]:
    return {
        "type": "object",
        "required": [
            "question",
            "why_it_matters",
            "decision_impact",
            "answerability",
            "urgency",
            "blocking_hypothesis_ids",
        ],
        "properties": {
            "question": {"type": "string", "minLength": 1},
            "why_it_matters": {"type": "string", "minLength": 1},
            "decision_impact": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
            "answerability": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
            "urgency": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
            "blocking_hypothesis_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "additionalProperties": False,
    }


def build_unknown_request(
    hypotheses: Sequence[WorldStateAtom],
    *,
    context_snapshot_ref: str,
    tenant_id: str,
    family_id: str,
    data_class: str,
    request_id: str | None = None,
) -> StructuredRequest:
    if not hypotheses:
        raise ContextContractError("UNKNOWN_REQUEST_REQUIRES_HYPOTHESES")
    payload = {
        "hypotheses": [
            {
                "atom_id": h.atom_id,
                "statement": h.value_ref,
                "support_level": getattr(h, "support_level", None),
            }
            for h in hypotheses
        ]
    }
    return StructuredRequest(
        use_case=UNKNOWN_USE_CASE,
        prompt_version=UNKNOWN_PROMPT_VERSION,
        schema_version=UNKNOWN_SCHEMA_VERSION,
        data_class=data_class,
        payload=payload,
        output_schema=unknown_output_schema(),
        context_snapshot_ref=context_snapshot_ref,
        input_refs=tuple(h.atom_id for h in hypotheses),
        request_id=request_id,
        tenant_id=tenant_id,
        family_id=family_id,
    )


def validate_and_build_unknown(
    draft: ModelDraft,
    *,
    unknown_id: str,
    scope: ContextScope,
    subject_ids: tuple[str, ...],
    hypotheses: Sequence[WorldStateAtom],
    existing_unknowns: Sequence[UnknownState],
    created_at: datetime,
) -> UnknownState | None:
    """Returns `None` (not an atom) if the proposed question duplicates an
    already-`OPEN` Unknown for this family — this is the dedup check the
    model cannot be trusted to do itself (it has no reliable memory of
    every Unknown ever raised, only what happens to be in this one
    request's context window)."""

    output = draft.output
    question = output.get("question")
    why_it_matters = output.get("why_it_matters")
    if not isinstance(question, str) or not question.strip():
        raise ContextContractError("UNKNOWN_QUESTION_REQUIRED")
    if not isinstance(why_it_matters, str) or not why_it_matters.strip():
        raise ContextContractError("UNKNOWN_WHY_IT_MATTERS_REQUIRED")

    try:
        ImpactBand(output["decision_impact"])
        AnswerabilityBand(output["answerability"])
        UrgencyBand(output["urgency"])
    except (KeyError, ValueError) as exc:
        raise ContextContractError("UNKNOWN_BAND_INVALID") from exc

    blocking_ids = output.get("blocking_hypothesis_ids", [])
    if not isinstance(blocking_ids, list):
        raise ContextContractError("UNKNOWN_BLOCKING_IDS_MUST_BE_LIST")
    known_hypothesis_ids = {h.atom_id for h in hypotheses}
    unknown_cited = set(blocking_ids) - known_hypothesis_ids
    if unknown_cited:
        raise ContextContractError(f"UNKNOWN_CITES_UNKNOWN_HYPOTHESIS:{sorted(unknown_cited)}")

    for existing in existing_unknowns:
        if existing.status is UnknownStatus.OPEN and existing.question.strip() == question.strip():
            return None

    return UnknownState(
        unknown_id=unknown_id,
        scope=scope,
        subject_ids=subject_ids,
        question=question,
        why_it_matters=why_it_matters,
        source_refs=tuple(blocking_ids),
        status=UnknownStatus.OPEN,
        created_at=created_at,
    )


async def generate_unknown(
    gateway: ModelGateway,
    *,
    provider_id: str,
    hypotheses: Sequence[WorldStateAtom],
    existing_unknowns: Sequence[UnknownState],
    scope: ContextScope,
    subject_ids: tuple[str, ...],
    context_snapshot_ref: str,
    unknown_id: str,
    now: datetime,
) -> UnknownState | None:
    """Full WM-004C pipeline: hypotheses -> model call -> validated
    UnknownState (or `None` if the model's proposal duplicates an existing
    open Unknown). Mirrors `belief_engine.generate_hypothesis`."""

    request = build_unknown_request(
        hypotheses,
        context_snapshot_ref=context_snapshot_ref,
        tenant_id=scope.tenant_id,
        family_id=scope.family_id,
        data_class=scope.data_class.value,
    )
    draft = await gateway.generate_structured(request, provider_id=provider_id)
    return validate_and_build_unknown(
        draft,
        unknown_id=unknown_id,
        scope=scope,
        subject_ids=subject_ids,
        hypotheses=hypotheses,
        existing_unknowns=existing_unknowns,
        created_at=now,
    )


__all__ = [
    "AnswerabilityBand",
    "ImpactBand",
    "InformationValueInputs",
    "UNKNOWN_PROMPT_VERSION",
    "UNKNOWN_SCHEMA_VERSION",
    "UNKNOWN_USE_CASE",
    "UrgencyBand",
    "build_unknown_request",
    "compute_information_value",
    "generate_unknown",
    "rank_unknowns",
    "unknown_output_schema",
    "validate_and_build_unknown",
]
