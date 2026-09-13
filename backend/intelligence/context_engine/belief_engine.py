"""Belief Engine (AIFAMILY-WM-004B) — the first component in this repo's
World State Kernel that is allowed to call a generative model.

Per ADR-0172 (Deterministic Truth Projection + Generative Cognition), this
module is the boundary where generative reasoning is permitted, and it is
permitted *only* to produce `HYPOTHESIS` — never `FACT`. The pipeline is
fixed:

    World State (evidence atoms + conflicts)
        -> Evidence Selection (caller's job, not this module's)
        -> build_hypothesis_request()          [deterministic]
        -> ModelGateway.generate_structured()  [the only model call]
        -> validate_and_promote_hypothesis()   [deterministic validation]
        -> WorldStateAtom(epistemic_kind=HYPOTHESIS, status=... )

No step here imports a provider SDK directly — only
`backend.intelligence.model_gateway`, matching R7. The caller supplies an
already-constructed `ModelGateway` and `provider_id` (this module does not
wire admission/registry/safety runtime itself, mirroring the Router/
Executor separation established in `growth_plan_ai_wiring.py`).

Belief signal is categorical (`BeliefBand`/`UncertaintyBand`), not a fake
float probability — see `world_state.py`'s `BeliefBand` docstring for why.
`WorldStateProposal.confidence` (a float, required by the WM-001 kernel
contract) is never taken from the model's own output; it is always
`derive_confidence()`'s deterministic mapping from the categorical bands the
model *did* supply, so no model-invented precision enters the kernel.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from backend.intelligence.model_gateway.contracts import ModelDraft, StructuredRequest
from backend.intelligence.model_gateway.gateway import ModelGateway

from .contracts import ContextContractError, ContextScope
from .world_state import (
    BeliefBand,
    UncertaintyBand,
    WorldStateAtom,
    WorldStateEpistemicKind,
    WorldStateProposal,
    promote_proposal_to_atom,
)

HYPOTHESIS_USE_CASE = "family_world_state.hypothesis_generation"
HYPOTHESIS_PROMPT_VERSION = "world-model-belief-engine/v1"
HYPOTHESIS_SCHEMA_VERSION = "world-model-belief-engine/v1"

_BAND_ORDER = (BeliefBand.NONE, BeliefBand.WEAK, BeliefBand.MODERATE, BeliefBand.STRONG)
_UNCERTAINTY_ORDER = (UncertaintyBand.LOW, UncertaintyBand.MEDIUM, UncertaintyBand.HIGH)

#: Deterministic support-minus-contradiction-minus-uncertainty midpoints.
#: Coarse by design (four support levels x three uncertainty levels), not a
#: calibrated model — there is no calibration data in V1 to justify finer
#: precision, and inventing some would be exactly the "fake Bayesian
#: probability" the project owner ruled out for WM-004B.
_SUPPORT_WEIGHT = {
    BeliefBand.NONE: 0.0,
    BeliefBand.WEAK: 0.25,
    BeliefBand.MODERATE: 0.5,
    BeliefBand.STRONG: 0.75,
}
_UNCERTAINTY_DISCOUNT = {
    UncertaintyBand.LOW: 1.0,
    UncertaintyBand.MEDIUM: 0.7,
    UncertaintyBand.HIGH: 0.4,
}


def derive_confidence(
    *,
    support_level: BeliefBand,
    contradiction_level: BeliefBand,
    uncertainty: UncertaintyBand,
) -> float:
    """Deterministic float derived from the model's categorical bands —
    never a float the model reports directly. `contradiction_level`
    subtracts from `support_level`'s weight; `uncertainty` then discounts
    the result. Clamped to [0.05, 0.95]: never absolute certainty (nothing
    in this kernel should ever look infallible) and never absolute zero
    (a WorldStateProposal with confidence 0.0 would be indistinguishable
    from "this hypothesis was never seriously considered")."""

    raw = 0.5 + (_SUPPORT_WEIGHT[support_level] - _SUPPORT_WEIGHT[contradiction_level]) / 2
    discount = _UNCERTAINTY_DISCOUNT[uncertainty]
    discounted = raw * discount + (1 - discount) * 0.5
    return max(0.05, min(0.95, discounted))


def hypothesis_output_schema() -> dict[str, object]:
    """JSON schema the model's structured response must satisfy. Refusing
    an unstructured response is what makes `ValueError`s in
    `validate_and_promote_hypothesis` a validation failure, not a parsing
    accident."""

    return {
        "type": "object",
        "required": [
            "statement",
            "support_level",
            "contradiction_level",
            "uncertainty",
            "evidence_atom_ids",
        ],
        "properties": {
            "statement": {"type": "string", "minLength": 1},
            "support_level": {"type": "string", "enum": [b.value for b in _BAND_ORDER]},
            "contradiction_level": {"type": "string", "enum": [b.value for b in _BAND_ORDER]},
            "uncertainty": {"type": "string", "enum": [u.value for u in _UNCERTAINTY_ORDER]},
            "evidence_atom_ids": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            },
        },
        "additionalProperties": False,
    }


def build_hypothesis_request(
    evidence_atoms: Sequence[WorldStateAtom],
    *,
    context_snapshot_ref: str,
    tenant_id: str,
    family_id: str,
    data_class: str,
    request_id: str | None = None,
) -> StructuredRequest:
    """Project evidence atoms into a `StructuredRequest`. Only the atoms'
    own already-persisted content is sent — no raw family conversation
    text beyond what a caller already chose to store as `value_ref`."""

    if not evidence_atoms:
        raise ContextContractError("HYPOTHESIS_REQUEST_REQUIRES_EVIDENCE")
    payload = {
        "evidence": [
            {
                "atom_id": atom.atom_id,
                "epistemic_kind": atom.epistemic_kind.value,
                "predicate": atom.predicate,
                "value_ref": atom.value_ref,
                "asserted_by": atom.asserted_by,
            }
            for atom in evidence_atoms
        ]
    }
    return StructuredRequest(
        use_case=HYPOTHESIS_USE_CASE,
        prompt_version=HYPOTHESIS_PROMPT_VERSION,
        schema_version=HYPOTHESIS_SCHEMA_VERSION,
        data_class=data_class,
        payload=payload,
        output_schema=hypothesis_output_schema(),
        context_snapshot_ref=context_snapshot_ref,
        input_refs=tuple(atom.atom_id for atom in evidence_atoms),
        request_id=request_id,
        tenant_id=tenant_id,
        family_id=family_id,
    )


def validate_and_build_proposal(
    draft: ModelDraft,
    *,
    proposal_id: str,
    scope: ContextScope,
    subject_ids: tuple[str, ...],
    evidence_atoms: Sequence[WorldStateAtom],
) -> WorldStateProposal:
    """Turn a schema-validated `ModelDraft` into a `WorldStateProposal`.

    Re-validates evidence references against the *actual* atoms passed in
    (not just "is this a string") — a model citing an `atom_id` that was
    never in its own input would be a hallucinated reference, and must be
    rejected here rather than silently accepted into the world state.
    """

    output = draft.output
    statement = output.get("statement")
    if not isinstance(statement, str) or not statement.strip():
        raise ContextContractError("HYPOTHESIS_STATEMENT_REQUIRED")

    try:
        support_level = BeliefBand(output["support_level"])
        contradiction_level = BeliefBand(output["contradiction_level"])
        uncertainty = UncertaintyBand(output["uncertainty"])
    except (KeyError, ValueError) as exc:
        raise ContextContractError("HYPOTHESIS_BAND_INVALID") from exc

    cited_ids = output.get("evidence_atom_ids")
    if not isinstance(cited_ids, list) or not cited_ids:
        raise ContextContractError("HYPOTHESIS_EVIDENCE_REQUIRED")
    known_ids = {atom.atom_id for atom in evidence_atoms}
    unknown_cited = set(cited_ids) - known_ids
    if unknown_cited:
        raise ContextContractError(f"HYPOTHESIS_CITES_UNKNOWN_EVIDENCE:{sorted(unknown_cited)}")

    confidence = derive_confidence(
        support_level=support_level,
        contradiction_level=contradiction_level,
        uncertainty=uncertainty,
    )

    return WorldStateProposal(
        proposal_id=proposal_id,
        scope=scope,
        subject_ids=subject_ids,
        proposed_kind=WorldStateEpistemicKind.HYPOTHESIS,
        statement=statement,
        evidence_refs=tuple(cited_ids),
        confidence=confidence,
        support_level=support_level,
        contradiction_level=contradiction_level,
        uncertainty=uncertainty,
    )


async def generate_hypothesis(
    gateway: ModelGateway,
    *,
    provider_id: str,
    evidence_atoms: Sequence[WorldStateAtom],
    scope: ContextScope,
    subject_ids: tuple[str, ...],
    context_snapshot_ref: str,
    proposal_id: str,
    atom_id: str,
    now: datetime,
) -> WorldStateAtom:
    """The full WM-004B pipeline: evidence -> model call -> validated
    HYPOTHESIS atom. This is the only function in this module that calls
    the model; every other function here is a pure, deterministic step
    around it."""

    request = build_hypothesis_request(
        evidence_atoms,
        context_snapshot_ref=context_snapshot_ref,
        tenant_id=scope.tenant_id,
        family_id=scope.family_id,
        data_class=scope.data_class.value,
    )
    draft = await gateway.generate_structured(request, provider_id=provider_id)
    proposal = validate_and_build_proposal(
        draft,
        proposal_id=proposal_id,
        scope=scope,
        subject_ids=subject_ids,
        evidence_atoms=evidence_atoms,
    )
    return promote_proposal_to_atom(
        proposal,
        atom_id=atom_id,
        provenance=draft.provenance.context_snapshot_ref,
        observed_at=now,
        recorded_at=now,
        valid_from=now,
    )


__all__ = [
    "HYPOTHESIS_PROMPT_VERSION",
    "HYPOTHESIS_SCHEMA_VERSION",
    "HYPOTHESIS_USE_CASE",
    "build_hypothesis_request",
    "derive_confidence",
    "generate_hypothesis",
    "hypothesis_output_schema",
    "validate_and_build_proposal",
]
