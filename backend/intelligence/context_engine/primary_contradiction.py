"""Primary Contradiction Engine (Golden E2E stage R4.3) — the next stage in
this repo's World State Kernel cognition chain after HYPOTHESIS
(`belief_engine.py`) and UNKNOWN (`unknown_engine.py`).

A `PrimaryContradictionProposal` is the model's tentative answer to "what is
this family's most decision-relevant current tension" — never a fact, never
a diagnosis, and structurally incapable of presenting itself as the single
certain interpretation: it must always carry at least one alternative framing
it is *not* proposing as primary (`alternatives`), plus a categorical
`uncertainty` band (never a model-invented float, see
`belief_engine.derive_confidence`'s docstring for why).

Same two-half discipline as `belief_engine.py`/`unknown_engine.py`:

    Evidence atoms + Hypotheses (+ optional Conflicts)
        -> build_primary_contradiction_request()   [deterministic]
        -> AgentRuntime.execute()                   [the only model call]
        -> validate_and_build_proposal()            [deterministic validation]
        -> PrimaryContradictionProposal

AIFAMILY-FIL-001 (INV-02): this module never holds a `ModelGateway` reference
— `generate_primary_contradiction()` is the only function that triggers a
model call, and it does so exclusively through the `AgentRuntime`-shaped
`_AgentRuntimeExecutor` Protocol, exactly like `belief_engine.generate_hypothesis`
and `unknown_engine.generate_unknown`.

Unlike `WorldStateProposal`, a `PrimaryContradictionProposal` is not promoted
to a `WorldStateAtom` in this module — whether/how a confirmed primary
contradiction becomes durable state is a separate, later concern outside this
module's scope. This is a proposal object returned to a caller, analogous to
`WorldStateProposal` before promotion.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from backend.intelligence.agent_runtime.contracts import AgentAuthorization, AgentRun, AgentTask
from backend.intelligence.model_gateway.contracts import ModelDraft, StructuredRequest

from .conflict_engine import ConflictType, WorldStateConflict  # noqa: F401  (typing only)
from .contracts import ContextContractError, ContextScope
from .world_state import UncertaintyBand, WorldStateAtom, _require_aware, _require_text


class _AgentRuntimeExecutor(Protocol):
    """Structural interface for `AgentRuntime`/`DurableAgentRuntime` — see
    `belief_engine._AgentRuntimeExecutor` for why this module depends on the
    shape, not the concrete class."""

    async def execute(
        self, task: AgentTask, authorization: AgentAuthorization | None
    ) -> AgentRun: ...


PRIMARY_CONTRADICTION_USE_CASE = "family_world_state.primary_contradiction_proposal"
PRIMARY_CONTRADICTION_PROMPT_VERSION = "world-model-primary-contradiction/v1"
PRIMARY_CONTRADICTION_SCHEMA_VERSION = "world-model-primary-contradiction/v1"

_UNCERTAINTY_ORDER = (UncertaintyBand.LOW, UncertaintyBand.MEDIUM, UncertaintyBand.HIGH)


@dataclass(frozen=True, slots=True)
class PrimaryContradictionProposal:
    """An AI-authored candidate framing of a family's most decision-relevant
    current tension — never a fact or diagnosis.

    Structurally required to carry its own uncertainty (`uncertainty`) and at
    least one alternative it considered and rejected as primary
    (`alternatives`), so it can never be silently treated as ground truth —
    mirrors `WorldStateProposal`'s discipline of "AI output that is not yet
    an atom" (see `world_state.py`).
    """

    proposal_id: str
    scope: ContextScope
    subject_ids: tuple[str, ...]
    statement: str
    evidence_refs: tuple[str, ...]
    supporting_hypothesis_refs: tuple[str, ...]
    contradiction_refs: tuple[str, ...]
    alternatives: tuple[str, ...]
    uncertainty: UncertaintyBand
    why_priority_now: str
    created_at: datetime

    def __post_init__(self) -> None:
        _require_text("proposal_id", self.proposal_id)
        _require_text("statement", self.statement)
        _require_text("why_priority_now", self.why_priority_now)
        if not isinstance(self.subject_ids, tuple) or not self.subject_ids:
            raise ContextContractError("subject_ids must be a non-empty tuple")
        if not self.alternatives:
            raise ContextContractError("PRIMARY_CONTRADICTION_REQUIRES_ALTERNATIVES")
        _require_aware("created_at", self.created_at)


def primary_contradiction_output_schema() -> dict[str, object]:
    """JSON schema the model's structured response must satisfy."""

    return {
        "type": "object",
        "required": [
            "statement",
            "alternatives",
            "uncertainty",
            "why_priority_now",
            "evidence_atom_ids",
            "supporting_hypothesis_ids",
            "contradiction_ids",
        ],
        "properties": {
            "statement": {"type": "string", "minLength": 1},
            "alternatives": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            },
            "uncertainty": {"type": "string", "enum": [u.value for u in _UNCERTAINTY_ORDER]},
            "why_priority_now": {"type": "string", "minLength": 1},
            "evidence_atom_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "supporting_hypothesis_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "contradiction_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "additionalProperties": False,
    }


def build_primary_contradiction_request(
    evidence_atoms: Sequence[WorldStateAtom],
    hypotheses: Sequence[WorldStateAtom],
    conflicts: Sequence[WorldStateConflict],
    *,
    context_snapshot_ref: str,
    tenant_id: str,
    family_id: str,
    data_class: str,
    request_id: str | None = None,
) -> StructuredRequest:
    """Project evidence atoms, hypotheses, and conflicts into a
    `StructuredRequest`. Only each input's own already-persisted content is
    forwarded — no raw family conversation text beyond what a caller already
    chose to store as `value_ref`, mirroring `build_hypothesis_request`'s
    reasoning about not leaking anything beyond what's already stored."""

    if not evidence_atoms:
        raise ContextContractError("PRIMARY_CONTRADICTION_REQUEST_REQUIRES_EVIDENCE")
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
        ],
        "hypotheses": [
            {
                "atom_id": h.atom_id,
                "predicate": h.predicate,
                "statement": h.value_ref,
                "support_level": h.support_level.value if h.support_level else None,
                "contradiction_level": h.contradiction_level.value
                if h.contradiction_level
                else None,
                "uncertainty": h.uncertainty.value if h.uncertainty else None,
            }
            for h in hypotheses
        ],
        "conflicts": [
            {
                "conflict_id": conflict.conflict_id,
                "conflict_type": conflict.conflict_type.value,
            }
            for conflict in conflicts
        ],
    }
    input_refs = tuple(atom.atom_id for atom in evidence_atoms) + tuple(
        h.atom_id for h in hypotheses
    )
    return StructuredRequest(
        use_case=PRIMARY_CONTRADICTION_USE_CASE,
        prompt_version=PRIMARY_CONTRADICTION_PROMPT_VERSION,
        schema_version=PRIMARY_CONTRADICTION_SCHEMA_VERSION,
        data_class=data_class,
        payload=payload,
        output_schema=primary_contradiction_output_schema(),
        context_snapshot_ref=context_snapshot_ref,
        input_refs=input_refs,
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
    hypotheses: Sequence[WorldStateAtom],
    conflicts: Sequence[WorldStateConflict],
    created_at: datetime,
) -> PrimaryContradictionProposal:
    """Turn a schema-validated `ModelDraft` into a `PrimaryContradictionProposal`.

    Re-validates `evidence_atom_ids` and `supporting_hypothesis_ids` against
    the *actual* atoms/hypotheses passed in (not just "is this a string") —
    mirrors `belief_engine.validate_and_build_proposal`'s
    `HYPOTHESIS_CITES_UNKNOWN_EVIDENCE` discipline exactly. `contradiction_ids`
    are accepted as-is: this module does not require citing a real conflict
    (a family may have a primary contradiction proposal with no formally
    recorded `WorldStateConflict` yet)."""

    output = draft.output
    statement = output.get("statement")
    if not isinstance(statement, str) or not statement.strip():
        raise ContextContractError("PRIMARY_CONTRADICTION_STATEMENT_REQUIRED")

    why_priority_now = output.get("why_priority_now")
    if not isinstance(why_priority_now, str) or not why_priority_now.strip():
        raise ContextContractError("PRIMARY_CONTRADICTION_WHY_PRIORITY_NOW_REQUIRED")

    alternatives = output.get("alternatives")
    if not isinstance(alternatives, list) or not alternatives:
        raise ContextContractError("PRIMARY_CONTRADICTION_REQUIRES_ALTERNATIVES")
    if not all(isinstance(a, str) and a.strip() for a in alternatives):
        raise ContextContractError("PRIMARY_CONTRADICTION_ALTERNATIVES_MUST_BE_NONEMPTY_STRINGS")

    try:
        uncertainty = UncertaintyBand(output["uncertainty"])
    except (KeyError, ValueError) as exc:
        raise ContextContractError("PRIMARY_CONTRADICTION_UNCERTAINTY_INVALID") from exc

    cited_evidence_ids = output.get("evidence_atom_ids", [])
    if not isinstance(cited_evidence_ids, list):
        raise ContextContractError("PRIMARY_CONTRADICTION_EVIDENCE_IDS_MUST_BE_LIST")
    known_evidence_ids = {atom.atom_id for atom in evidence_atoms}
    unknown_evidence = set(cited_evidence_ids) - known_evidence_ids
    if unknown_evidence:
        raise ContextContractError(
            f"PRIMARY_CONTRADICTION_CITES_UNKNOWN_EVIDENCE:{sorted(unknown_evidence)}"
        )

    cited_hypothesis_ids = output.get("supporting_hypothesis_ids", [])
    if not isinstance(cited_hypothesis_ids, list):
        raise ContextContractError("PRIMARY_CONTRADICTION_HYPOTHESIS_IDS_MUST_BE_LIST")
    known_hypothesis_ids = {h.atom_id for h in hypotheses}
    unknown_hypotheses = set(cited_hypothesis_ids) - known_hypothesis_ids
    if unknown_hypotheses:
        raise ContextContractError(
            f"PRIMARY_CONTRADICTION_CITES_UNKNOWN_HYPOTHESIS:{sorted(unknown_hypotheses)}"
        )

    cited_conflict_ids = output.get("contradiction_ids", [])
    if not isinstance(cited_conflict_ids, list):
        raise ContextContractError("PRIMARY_CONTRADICTION_CONFLICT_IDS_MUST_BE_LIST")

    return PrimaryContradictionProposal(
        proposal_id=proposal_id,
        scope=scope,
        subject_ids=subject_ids,
        statement=statement,
        evidence_refs=tuple(cited_evidence_ids),
        supporting_hypothesis_refs=tuple(cited_hypothesis_ids),
        contradiction_refs=tuple(cited_conflict_ids),
        alternatives=tuple(alternatives),
        uncertainty=uncertainty,
        why_priority_now=why_priority_now,
        created_at=created_at,
    )


async def generate_primary_contradiction(
    runtime: _AgentRuntimeExecutor,
    *,
    agent_id: str,
    authorization: AgentAuthorization | None,
    request_id: str,
    evidence_atoms: Sequence[WorldStateAtom],
    hypotheses: Sequence[WorldStateAtom],
    conflicts: Sequence[WorldStateConflict],
    scope: ContextScope,
    subject_ids: tuple[str, ...],
    context_snapshot_ref: str,
    proposal_id: str,
    now: datetime,
) -> PrimaryContradictionProposal:
    """The full pipeline: evidence + hypotheses + conflicts -> AgentRuntime
    call -> validated `PrimaryContradictionProposal`. This is the only
    function in this module that triggers a model execution; every other
    function here is a pure, deterministic step around it. AIFAMILY-FIL-001:
    the execution boundary is `AgentRuntime.execute()`, not a direct
    `ModelGateway` call — see module docstring."""

    task = _build_primary_contradiction_agent_task(
        evidence_atoms,
        hypotheses,
        conflicts,
        agent_id=agent_id,
        request_id=request_id,
        context_snapshot_ref=context_snapshot_ref,
        tenant_id=scope.tenant_id,
        family_id=scope.family_id,
        data_class=scope.data_class.value,
    )
    run = await runtime.execute(task, authorization)
    return validate_and_build_proposal(
        run.draft,
        proposal_id=proposal_id,
        scope=scope,
        subject_ids=subject_ids,
        evidence_atoms=evidence_atoms,
        hypotheses=hypotheses,
        conflicts=conflicts,
        created_at=now,
    )


def _build_primary_contradiction_agent_task(
    evidence_atoms: Sequence[WorldStateAtom],
    hypotheses: Sequence[WorldStateAtom],
    conflicts: Sequence[WorldStateConflict],
    *,
    agent_id: str,
    request_id: str,
    context_snapshot_ref: str,
    tenant_id: str,
    family_id: str,
    data_class: str,
) -> AgentTask:
    """Same ingredients as `build_primary_contradiction_request()`, repackaged
    as an `AgentTask` — see `belief_engine._build_hypothesis_agent_task` for
    why the pure `StructuredRequest` builder stays separate."""

    request = build_primary_contradiction_request(
        evidence_atoms,
        hypotheses,
        conflicts,
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
        use_case=PRIMARY_CONTRADICTION_USE_CASE,
        context_snapshot_ref=context_snapshot_ref,
        prompt_version=PRIMARY_CONTRADICTION_PROMPT_VERSION,
        schema_version=PRIMARY_CONTRADICTION_SCHEMA_VERSION,
        data_class=data_class,
        payload=dict(request.payload),
        output_schema=request.output_schema,
        input_refs=request.input_refs,
    )


__all__ = [
    "PRIMARY_CONTRADICTION_PROMPT_VERSION",
    "PRIMARY_CONTRADICTION_SCHEMA_VERSION",
    "PRIMARY_CONTRADICTION_USE_CASE",
    "ConflictType",
    "PrimaryContradictionProposal",
    "WorldStateConflict",
    "build_primary_contradiction_request",
    "generate_primary_contradiction",
    "primary_contradiction_output_schema",
    "validate_and_build_proposal",
]
