"""Belief Engine (AIFAMILY-WM-004B) — the first component in this repo's
World State Kernel that is allowed to call a generative model.

Per ADR-0172 (Deterministic Truth Projection + Generative Cognition), this
module is the boundary where generative reasoning is permitted, and it is
permitted *only* to produce `HYPOTHESIS` — never `FACT`. The pipeline is
fixed:

    World State (evidence atoms + conflicts)
        -> Evidence Selection (caller's job, not this module's)
        -> build_hypothesis_request()          [deterministic]
        -> AgentRuntime.execute()              [the only model call]
        -> validate_and_promote_hypothesis()   [deterministic validation]
        -> WorldStateAtom(epistemic_kind=HYPOTHESIS, status=... )

AIFAMILY-FIL-001 correction: earlier versions of `generate_hypothesis()`
called `ModelGateway.generate_structured()` directly. Per the platform's
INV-02 invariant ("all production model calls go through
AgentRuntime -> Model Gateway, never a parallel cognition-specific
execution path"), this module now calls `AgentRuntime.execute()` — the
same governed entry point Principal/Planner use — instead of holding a
`ModelGateway` reference itself. `build_hypothesis_request()` stays a pure
function producing the payload/schema `_build_agent_task()` needs;
`validate_and_build_proposal()` is unchanged and works on `AgentRun.draft`
(a `ModelDraft`) exactly as it worked on a gateway-returned one.

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
from typing import Protocol

from backend.intelligence.agent_runtime.contracts import AgentAuthorization, AgentRun, AgentTask
from backend.intelligence.model_gateway.contracts import ModelDraft, StructuredRequest

from .contracts import ContextContractError, ContextScope
from .predicate_registry import PredicateRegistry
from .world_state import (
    BeliefBand,
    UncertaintyBand,
    WorldStateAtom,
    WorldStateEpistemicKind,
    WorldStateProposal,
    promote_proposal_to_atom,
)


class _AgentRuntimeExecutor(Protocol):
    """Structural interface for `AgentRuntime`/`DurableAgentRuntime` — this
    module never imports the concrete runtime class, only the shape it
    needs, so a caller can inject either the plain or the durable/
    idempotent variant without this module caring which."""

    async def execute(
        self, task: AgentTask, authorization: AgentAuthorization | None
    ) -> AgentRun: ...


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
    target_predicate: str,
    predicate_registry: PredicateRegistry | None = None,
) -> WorldStateProposal:
    """Turn a schema-validated `ModelDraft` into a `WorldStateProposal`.

    Re-validates evidence references against the *actual* atoms passed in
    (not just "is this a string") — a model citing an `atom_id` that was
    never in its own input would be a hallucinated reference, and must be
    rejected here rather than silently accepted into the world state.

    `target_predicate` is supplied by the *caller*, never invented by the
    model (the model's structured output schema has no predicate field at
    all — see `hypothesis_output_schema()`), and is validated against the
    governed `PredicateRegistry` before a proposal can even be constructed.
    """

    (predicate_registry or PredicateRegistry.from_yaml()).validate(target_predicate)

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
        target_predicate=target_predicate,
        statement=statement,
        evidence_refs=tuple(cited_ids),
        confidence=confidence,
        support_level=support_level,
        contradiction_level=contradiction_level,
        uncertainty=uncertainty,
    )


async def generate_hypothesis(
    runtime: _AgentRuntimeExecutor,
    *,
    agent_id: str,
    authorization: AgentAuthorization | None,
    request_id: str,
    evidence_atoms: Sequence[WorldStateAtom],
    scope: ContextScope,
    subject_ids: tuple[str, ...],
    context_snapshot_ref: str,
    proposal_id: str,
    atom_id: str,
    target_predicate: str,
    now: datetime,
    predicate_registry: PredicateRegistry | None = None,
) -> WorldStateAtom:
    """The full WM-004B pipeline: evidence -> AgentRuntime call -> validated
    HYPOTHESIS atom. This is the only function in this module that triggers
    a model execution; every other function here is a pure, deterministic
    step around it. AIFAMILY-FIL-001: the execution boundary is
    `AgentRuntime.execute()`, not a direct `ModelGateway` call — see module
    docstring.

    `target_predicate` is validated against the governed registry *before*
    the model is called — there is no point spending a real model call on
    a request whose target predicate would be rejected at promotion time
    anyway."""

    registry = predicate_registry or PredicateRegistry.from_yaml()
    registry.validate(target_predicate)

    task = _build_hypothesis_agent_task(
        evidence_atoms,
        agent_id=agent_id,
        request_id=request_id,
        context_snapshot_ref=context_snapshot_ref,
        tenant_id=scope.tenant_id,
        family_id=scope.family_id,
        data_class=scope.data_class.value,
    )
    run = await runtime.execute(task, authorization)
    draft = run.draft
    proposal = validate_and_build_proposal(
        draft,
        proposal_id=proposal_id,
        scope=scope,
        subject_ids=subject_ids,
        evidence_atoms=evidence_atoms,
        target_predicate=target_predicate,
        predicate_registry=registry,
    )
    return promote_proposal_to_atom(
        proposal,
        atom_id=atom_id,
        provenance=draft.provenance.context_snapshot_ref,
        observed_at=now,
        recorded_at=now,
        valid_from=now,
    )


def _build_hypothesis_agent_task(
    evidence_atoms: Sequence[WorldStateAtom],
    *,
    agent_id: str,
    request_id: str,
    context_snapshot_ref: str,
    tenant_id: str,
    family_id: str,
    data_class: str,
) -> AgentTask:
    """Same ingredients as `build_hypothesis_request()`, repackaged as an
    `AgentTask` — the shape `AgentRuntime.execute()` requires. Kept separate
    from `build_hypothesis_request()` because that function's `StructuredRequest`
    output is also used directly by the gated real-model livecheck tests,
    which call the gateway themselves rather than through AgentRuntime
    (see `tests/family_journeys/test_family_scene_001_real_gateway_livecheck.py`)."""

    request = build_hypothesis_request(
        evidence_atoms,
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
        use_case=HYPOTHESIS_USE_CASE,
        context_snapshot_ref=context_snapshot_ref,
        prompt_version=HYPOTHESIS_PROMPT_VERSION,
        schema_version=HYPOTHESIS_SCHEMA_VERSION,
        data_class=data_class,
        payload=dict(request.payload),
        output_schema=request.output_schema,
        input_refs=request.input_refs,
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
