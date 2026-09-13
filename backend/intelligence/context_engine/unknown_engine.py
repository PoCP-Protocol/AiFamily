"""Unknown Engine (AIFAMILY-WM-004C).

`UnknownState` (defined once, in `world_state.py`) is the *only* canonical
ignorance object in this kernel — there is deliberately no second,
Atom-based "Unknown" representation anywhere in this module or in
`postgres_unknown_repository.py`.

Two halves, the same separation `belief_engine.py` uses:

1. **Deterministic**: `compute_information_value()`/`rank_unknowns()`/
   `compute_priority()` need no model at all. This is most of what this
   engine does day to day, and it is what makes "which question is most
   worth asking next" a reproducible, auditable computation rather than a
   model opinion.
2. **Generative, gated**: `generate_unknown()` lets a model *propose* a
   candidate Unknown from the current hypotheses, but per ADR-0172 every
   proposal is re-validated deterministically before becoming a real
   `UnknownState`:

   - `target_predicate` must be one of the caller-supplied
     `allowed_target_predicates` — the model is never free to invent a
     predicate; an unregistered/undisclosed one fails closed with
     `UNKNOWN_TARGET_PREDICATE_NOT_ALLOWED`.
   - every `blocking_hypothesis_ids` entry must be an `atom_id` that was
     actually part of *this request's own* hypothesis context — a
     hallucinated reference is rejected, never silently trusted.
   - `unknown_key` (AIFAMILY-WM-004C, B9) is a canonical identity built
     from tenant/family/subjects/target_predicate/blocking_refs — *not* a
     hash of the question's wording — so the same underlying cognitive gap
     phrased two different ways collapses to one row instead of a stream
     of near-duplicates.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from backend.intelligence.agent_runtime.contracts import AgentAuthorization, AgentRun, AgentTask
from backend.intelligence.model_gateway.contracts import ModelDraft, StructuredRequest

from .contracts import ContextContractError, ContextScope
from .unknown_identity import build_unknown_key
from .world_state import UncertaintyBand, UnknownState, UnknownStatus, WorldStateAtom


class _AgentRuntimeExecutor(Protocol):
    """Structural interface for `AgentRuntime`/`DurableAgentRuntime` — see
    `belief_engine._AgentRuntimeExecutor` for why this module depends on the
    shape, not the concrete class."""

    async def execute(
        self, task: AgentTask, authorization: AgentAuthorization | None
    ) -> AgentRun: ...


UNKNOWN_USE_CASE = "family_world_state.unknown_generation"
UNKNOWN_PROMPT_VERSION = "world-model-unknown-engine/v1"
UNKNOWN_SCHEMA_VERSION = "world-model-unknown-engine/v1"
UNKNOWN_CONTRACT_VERSION = "world-model-unknown-engine/v1"


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


class UnknownPriority(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


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


def compute_priority(
    *,
    decision_impact: ImpactBand,
    answerability: AnswerabilityBand,
    urgency: UrgencyBand,
) -> UnknownPriority:
    """AIFAMILY-WM-004C B8: priority is a fixed, deterministic mapping from
    the three categorical bands the model supplied — never a float the
    model invents and never something a caller can pass in directly. A
    HIGH-impact, HIGH-urgency, at-least-MEDIUM-answerable gap is CRITICAL;
    a LOW/LOW/LOW gap is LOW; everything else is NORMAL/HIGH by the table
    below. Coarse by design, matching `compute_information_value`."""

    if decision_impact is ImpactBand.HIGH and urgency is UrgencyBand.HIGH:
        return (
            UnknownPriority.CRITICAL
            if answerability is not AnswerabilityBand.LOW
            else UnknownPriority.HIGH
        )
    if decision_impact is ImpactBand.LOW and urgency is UrgencyBand.LOW:
        return UnknownPriority.LOW
    if decision_impact is ImpactBand.HIGH or urgency is UrgencyBand.HIGH:
        return UnknownPriority.HIGH
    return UnknownPriority.NORMAL


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


def unknown_output_schema(allowed_target_predicates: Sequence[str]) -> dict[str, object]:
    return {
        "type": "object",
        "required": [
            "question",
            "why_it_matters",
            "target_predicate",
            "decision_impact",
            "answerability",
            "urgency",
            "blocking_hypothesis_ids",
        ],
        "properties": {
            "question": {"type": "string", "minLength": 1},
            "why_it_matters": {"type": "string", "minLength": 1},
            "target_predicate": {"type": "string", "enum": list(allowed_target_predicates)},
            "decision_impact": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
            "answerability": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
            "urgency": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
            "preferred_source": {"type": ["string", "null"]},
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
    allowed_target_predicates: Sequence[str],
    context_snapshot_ref: str,
    tenant_id: str,
    family_id: str,
    data_class: str,
    request_id: str | None = None,
) -> StructuredRequest:
    if not hypotheses:
        raise ContextContractError("UNKNOWN_REQUEST_REQUIRES_HYPOTHESES")
    if not allowed_target_predicates:
        raise ContextContractError("UNKNOWN_REQUEST_REQUIRES_ALLOWED_TARGET_PREDICATES")
    payload = {
        "hypotheses": [
            {
                "atom_id": h.atom_id,
                "statement": h.value_ref,
                "support_level": h.support_level.value if h.support_level else None,
            }
            for h in hypotheses
        ],
        "allowed_target_predicates": list(allowed_target_predicates),
    }
    return StructuredRequest(
        use_case=UNKNOWN_USE_CASE,
        prompt_version=UNKNOWN_PROMPT_VERSION,
        schema_version=UNKNOWN_SCHEMA_VERSION,
        data_class=data_class,
        payload=payload,
        output_schema=unknown_output_schema(allowed_target_predicates),
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
    allowed_target_predicates: Sequence[str],
    existing_unknowns: Sequence[UnknownState],
    created_at: datetime,
) -> UnknownState | None:
    """Returns `None` (not an UnknownState) if the proposed identity
    (`unknown_key`, AIFAMILY-WM-004C B9 — not the question's literal
    wording) duplicates an already-`OPEN` Unknown for this family. This is
    the dedup check the model cannot be trusted to do itself: it has no
    reliable memory of every Unknown ever raised, and two independently
    generated calls describing the same gap in different words must still
    collapse to one row."""

    output = draft.output
    question = output.get("question")
    why_it_matters = output.get("why_it_matters")
    if not isinstance(question, str) or not question.strip():
        raise ContextContractError("UNKNOWN_QUESTION_REQUIRED")
    if not isinstance(why_it_matters, str) or not why_it_matters.strip():
        raise ContextContractError("UNKNOWN_WHY_IT_MATTERS_REQUIRED")

    target_predicate = output.get("target_predicate")
    if not isinstance(target_predicate, str) or not target_predicate:
        raise ContextContractError("UNKNOWN_TARGET_PREDICATE_REQUIRED")
    if target_predicate not in set(allowed_target_predicates):
        raise ContextContractError(f"UNKNOWN_TARGET_PREDICATE_NOT_ALLOWED:{target_predicate}")

    try:
        decision_impact = ImpactBand(output["decision_impact"])
        answerability = AnswerabilityBand(output["answerability"])
        urgency = UrgencyBand(output["urgency"])
    except (KeyError, ValueError) as exc:
        raise ContextContractError("UNKNOWN_BAND_INVALID") from exc

    blocking_ids = output.get("blocking_hypothesis_ids", [])
    if not isinstance(blocking_ids, list):
        raise ContextContractError("UNKNOWN_BLOCKING_IDS_MUST_BE_LIST")
    known_hypothesis_ids = {h.atom_id for h in hypotheses}
    hallucinated = set(blocking_ids) - known_hypothesis_ids
    if hallucinated:
        raise ContextContractError(
            f"UNKNOWN_CITES_HALLUCINATED_BLOCKING_REF:{sorted(hallucinated)}"
        )

    preferred_source = output.get("preferred_source")
    if preferred_source is not None and not isinstance(preferred_source, str):
        raise ContextContractError("UNKNOWN_PREFERRED_SOURCE_MUST_BE_STRING_OR_NULL")

    unknown_key = build_unknown_key(
        tenant_id=scope.tenant_id,
        family_id=scope.family_id,
        subject_ids=subject_ids,
        target_predicate=target_predicate,
        blocking_refs=blocking_ids,
        unknown_contract_version=UNKNOWN_CONTRACT_VERSION,
    )
    for existing in existing_unknowns:
        if existing.status is UnknownStatus.OPEN and existing.unknown_key == unknown_key:
            return None

    priority = compute_priority(
        decision_impact=decision_impact, answerability=answerability, urgency=urgency
    )

    return UnknownState(
        unknown_id=unknown_id,
        scope=scope,
        subject_ids=subject_ids,
        question=question,
        why_it_matters=why_it_matters,
        target_predicate=target_predicate,
        decision_impact=decision_impact.value,
        answerability=answerability.value,
        urgency=urgency.value,
        preferred_source=preferred_source,
        blocking_refs=tuple(sorted(set(blocking_ids))),
        unknown_key=unknown_key,
        source_refs=tuple(blocking_ids),
        priority=priority.value,
        status=UnknownStatus.OPEN,
        created_at=created_at,
    )


async def generate_unknown(
    runtime: _AgentRuntimeExecutor,
    *,
    agent_id: str,
    authorization: AgentAuthorization | None,
    request_id: str,
    hypotheses: Sequence[WorldStateAtom],
    allowed_target_predicates: Sequence[str],
    existing_unknowns: Sequence[UnknownState],
    scope: ContextScope,
    subject_ids: tuple[str, ...],
    context_snapshot_ref: str,
    unknown_id: str,
    now: datetime,
) -> UnknownState | None:
    """Full WM-004C pipeline: hypotheses -> AgentRuntime call -> validated
    UnknownState (or `None` if the model's proposal's canonical identity
    duplicates an existing open Unknown). Mirrors
    `belief_engine.generate_hypothesis`. AIFAMILY-FIL-001: this is the only
    function in this module that triggers a model execution, and it does so
    through `AgentRuntime.execute()`, never a directly-held `ModelGateway`
    — see module docstring."""

    task = _build_unknown_agent_task(
        hypotheses,
        agent_id=agent_id,
        request_id=request_id,
        allowed_target_predicates=allowed_target_predicates,
        context_snapshot_ref=context_snapshot_ref,
        tenant_id=scope.tenant_id,
        family_id=scope.family_id,
        data_class=scope.data_class.value,
    )
    run = await runtime.execute(task, authorization)
    return validate_and_build_unknown(
        run.draft,
        unknown_id=unknown_id,
        scope=scope,
        subject_ids=subject_ids,
        hypotheses=hypotheses,
        allowed_target_predicates=allowed_target_predicates,
        existing_unknowns=existing_unknowns,
        created_at=now,
    )


def _build_unknown_agent_task(
    hypotheses: Sequence[WorldStateAtom],
    *,
    agent_id: str,
    request_id: str,
    allowed_target_predicates: Sequence[str],
    context_snapshot_ref: str,
    tenant_id: str,
    family_id: str,
    data_class: str,
) -> AgentTask:
    """Same ingredients as `build_unknown_request()`, repackaged as an
    `AgentTask` — see `belief_engine._build_hypothesis_agent_task` for why
    the pure `StructuredRequest` builder stays separate (the gated real-model
    livecheck tests use it directly against the gateway)."""

    request = build_unknown_request(
        hypotheses,
        allowed_target_predicates=allowed_target_predicates,
        context_snapshot_ref=context_snapshot_ref,
        tenant_id=tenant_id,
        family_id=family_id,
        data_class=data_class,
        request_id=request_id,
    )
    return AgentTask(
        request_id=request_id,
        agent_id=agent_id,
        tenant_id=tenant_id,
        family_id=family_id,
        use_case=UNKNOWN_USE_CASE,
        context_snapshot_ref=context_snapshot_ref,
        prompt_version=UNKNOWN_PROMPT_VERSION,
        schema_version=UNKNOWN_SCHEMA_VERSION,
        data_class=data_class,
        payload=dict(request.payload),
        output_schema=request.output_schema,
        input_refs=request.input_refs,
    )


__all__ = [
    "AnswerabilityBand",
    "ImpactBand",
    "InformationValueInputs",
    "UNKNOWN_CONTRACT_VERSION",
    "UNKNOWN_PROMPT_VERSION",
    "UNKNOWN_SCHEMA_VERSION",
    "UNKNOWN_USE_CASE",
    "UnknownPriority",
    "UrgencyBand",
    "build_unknown_request",
    "compute_information_value",
    "compute_priority",
    "generate_unknown",
    "rank_unknowns",
    "unknown_output_schema",
    "validate_and_build_unknown",
]
