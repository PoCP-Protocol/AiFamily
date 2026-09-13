"""Goal Proposal (AIFAMILY-WM-005) — an AI-authored, not-yet-decided candidate
goal for a family.

Same architecture as `belief_engine.py`'s Belief Engine: this module produces
a `GoalProposal`, a frozen dataclass that is explicitly NOT a decision. Turning
a `GoalProposal` into something the family actually pursues requires a real
human guardian's decision (see `guardian_goal_decision.py`) — nothing in this
module writes that decision, and nothing here mutates any business domain.

AIFAMILY-FIL-001 (INV-02): the only function here that triggers a model call
is `generate_goal_proposal()`, and it calls through `AgentRuntime.execute()`
— the same governed entry point Belief Engine and Unknown Engine use — never
a directly-held `ModelGateway`. `build_goal_proposal_request()` stays a pure
function producing the payload/schema the agent task needs;
`validate_and_build_goal_proposal()` is a pure validation step that works on
`AgentRun.draft` (a `ModelDraft`).

Deliberately self-contained: this module does not import a sibling
`primary_contradiction.py` type. A `GoalProposal` is generated *from* a primary
contradiction, but the relationship is carried as plain strings
(`primary_contradiction_statement` in the request, `reasoning_ref` on the
proposal) rather than as an imported dataclass — this keeps the module usable
regardless of that sibling module's own development state, and avoids two
cognition modules coupling through a shared concrete type that neither the
Belief Engine nor the Unknown Engine require of each other either.

Learning Contract fields (`expected_observation`, `measurement_window`,
`failure_criteria`, `stop_criteria`, `escalation_criteria`) are required
non-empty for the same reason `success_criteria` is required: a goal that
does not say up front how anyone will know it worked, when to stop, or when
to escalate to a human professional is not a goal this platform is willing to
let an AI propose. `escalation_criteria` in particular is a safety-relevant
structural requirement, not a nice-to-have — see the module docstring on
`guardian_goal_decision.py` for the human-decision half of this contract.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from backend.intelligence.agent_runtime.contracts import AgentAuthorization, AgentRun, AgentTask
from backend.intelligence.model_gateway.contracts import ModelDraft, StructuredRequest

from .contracts import ContextContractError, ContextScope
from .world_state import WorldStateAtom


class _AgentRuntimeExecutor(Protocol):
    """Structural interface for `AgentRuntime`/`DurableAgentRuntime` — this
    module never imports the concrete runtime class, only the shape it
    needs, so a caller can inject either the plain or the durable/
    idempotent variant without this module caring which."""

    async def execute(
        self, task: AgentTask, authorization: AgentAuthorization | None
    ) -> AgentRun: ...


GOAL_PROPOSAL_USE_CASE = "family_world_state.goal_proposal_generation"
GOAL_PROPOSAL_PROMPT_VERSION = "world-model-goal-proposal/v1"
GOAL_PROPOSAL_SCHEMA_VERSION = "world-model-goal-proposal/v1"


def _require_text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContextContractError(name)


def _require_non_empty_tuple(name: str, value: tuple[str, ...]) -> None:
    if not isinstance(value, tuple) or not value:
        raise ContextContractError(name)


@dataclass(frozen=True, slots=True)
class GoalProposal:
    """An AI-authored candidate goal that has not been admitted yet.

    Explicitly NOT a decision — see the module docstring on
    `guardian_goal_decision.py` for what turns this into something a family
    actually pursues. Construction alone enforces every field-level
    requirement in this dataclass's own contract (success_criteria,
    reasoning_ref, and the full Learning Contract), so an invalid
    `GoalProposal` cannot exist even transiently.
    """

    goal_proposal_id: str
    scope: ContextScope
    subject_ids: tuple[str, ...]
    statement: str
    desired_change: str
    success_criteria: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    reasoning_ref: str
    expected_observation: str
    measurement_window: str
    failure_criteria: tuple[str, ...]
    stop_criteria: tuple[str, ...]
    escalation_criteria: tuple[str, ...]
    created_at: datetime
    family_need_ref: str | None = None
    non_goals: tuple[str, ...] = ()
    unknown_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text("goal_proposal_id", self.goal_proposal_id)
        if not isinstance(self.subject_ids, tuple) or not self.subject_ids:
            raise ContextContractError("subject_ids must be a non-empty tuple")
        _require_text("statement", self.statement)
        _require_text("desired_change", self.desired_change)
        _require_non_empty_tuple("GOAL_PROPOSAL_REQUIRES_SUCCESS_CRITERIA", self.success_criteria)
        _require_text("reasoning_ref", self.reasoning_ref)
        _require_text("expected_observation", self.expected_observation)
        _require_text("measurement_window", self.measurement_window)
        _require_non_empty_tuple("GOAL_PROPOSAL_REQUIRES_FAILURE_CRITERIA", self.failure_criteria)
        _require_non_empty_tuple("GOAL_PROPOSAL_REQUIRES_STOP_CRITERIA", self.stop_criteria)
        _require_non_empty_tuple(
            "GOAL_PROPOSAL_REQUIRES_ESCALATION_CRITERIA", self.escalation_criteria
        )
        if self.created_at.tzinfo is None:
            raise ContextContractError("created_at_requires_timezone")


def goal_proposal_output_schema() -> dict[str, object]:
    """JSON schema the model's structured response must satisfy. Refusing
    an unstructured response is what makes `ValueError`s in
    `validate_and_build_goal_proposal` a validation failure, not a parsing
    accident."""

    return {
        "type": "object",
        "required": [
            "statement",
            "desired_change",
            "success_criteria",
            "expected_observation",
            "measurement_window",
            "failure_criteria",
            "stop_criteria",
            "escalation_criteria",
            "evidence_atom_ids",
        ],
        "properties": {
            "statement": {"type": "string", "minLength": 1},
            "desired_change": {"type": "string", "minLength": 1},
            "success_criteria": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            },
            "non_goals": {"type": "array", "items": {"type": "string"}},
            "expected_observation": {"type": "string", "minLength": 1},
            "measurement_window": {"type": "string", "minLength": 1},
            "failure_criteria": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            },
            "stop_criteria": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            },
            "escalation_criteria": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            },
            "evidence_atom_ids": {"type": "array", "items": {"type": "string"}},
            "unknown_ids": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": False,
    }


def build_goal_proposal_request(
    evidence_atoms: Sequence[WorldStateAtom],
    *,
    primary_contradiction_statement: str,
    context_snapshot_ref: str,
    tenant_id: str,
    family_id: str,
    data_class: str,
    request_id: str | None = None,
) -> StructuredRequest:
    """Project evidence atoms plus the primary contradiction's statement into
    a `StructuredRequest`. Only already-persisted atom content and the
    caller-supplied contradiction statement are sent — no raw family
    conversation text beyond what a caller already chose to store."""

    if not evidence_atoms:
        raise ContextContractError("GOAL_PROPOSAL_REQUEST_REQUIRES_EVIDENCE")
    _require_text(
        "GOAL_PROPOSAL_REQUEST_REQUIRES_PRIMARY_CONTRADICTION",
        primary_contradiction_statement,
    )
    payload = {
        "primary_contradiction_statement": primary_contradiction_statement,
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
    }
    return StructuredRequest(
        use_case=GOAL_PROPOSAL_USE_CASE,
        prompt_version=GOAL_PROPOSAL_PROMPT_VERSION,
        schema_version=GOAL_PROPOSAL_SCHEMA_VERSION,
        data_class=data_class,
        payload=payload,
        output_schema=goal_proposal_output_schema(),
        context_snapshot_ref=context_snapshot_ref,
        input_refs=tuple(atom.atom_id for atom in evidence_atoms),
        request_id=request_id,
        tenant_id=tenant_id,
        family_id=family_id,
    )


def validate_and_build_goal_proposal(
    draft: ModelDraft,
    *,
    goal_proposal_id: str,
    scope: ContextScope,
    subject_ids: tuple[str, ...],
    evidence_atoms: Sequence[WorldStateAtom],
    family_need_ref: str | None,
    reasoning_ref: str,
    created_at: datetime,
) -> GoalProposal:
    """Turn a schema-validated `ModelDraft` into a `GoalProposal`.

    Re-validates evidence references against the *actual* atoms passed in
    (not just "is this a string") — a model citing an `atom_id` that was
    never in its own input would be a hallucinated reference, and must be
    rejected here rather than silently accepted into the world state."""

    output = draft.output

    statement = output.get("statement")
    if not isinstance(statement, str) or not statement.strip():
        raise ContextContractError("GOAL_PROPOSAL_STATEMENT_REQUIRED")

    desired_change = output.get("desired_change")
    if not isinstance(desired_change, str) or not desired_change.strip():
        raise ContextContractError("GOAL_PROPOSAL_DESIRED_CHANGE_REQUIRED")

    success_criteria = output.get("success_criteria")
    if not isinstance(success_criteria, list) or not success_criteria:
        raise ContextContractError("GOAL_PROPOSAL_REQUIRES_SUCCESS_CRITERIA")

    expected_observation = output.get("expected_observation")
    if not isinstance(expected_observation, str) or not expected_observation.strip():
        raise ContextContractError("GOAL_PROPOSAL_REQUIRES_EXPECTED_OBSERVATION")

    measurement_window = output.get("measurement_window")
    if not isinstance(measurement_window, str) or not measurement_window.strip():
        raise ContextContractError("GOAL_PROPOSAL_REQUIRES_MEASUREMENT_WINDOW")

    failure_criteria = output.get("failure_criteria")
    if not isinstance(failure_criteria, list) or not failure_criteria:
        raise ContextContractError("GOAL_PROPOSAL_REQUIRES_FAILURE_CRITERIA")

    stop_criteria = output.get("stop_criteria")
    if not isinstance(stop_criteria, list) or not stop_criteria:
        raise ContextContractError("GOAL_PROPOSAL_REQUIRES_STOP_CRITERIA")

    escalation_criteria = output.get("escalation_criteria")
    if not isinstance(escalation_criteria, list) or not escalation_criteria:
        raise ContextContractError("GOAL_PROPOSAL_REQUIRES_ESCALATION_CRITERIA")

    cited_ids = output.get("evidence_atom_ids")
    if not isinstance(cited_ids, list):
        raise ContextContractError("GOAL_PROPOSAL_EVIDENCE_REQUIRED")
    known_ids = {atom.atom_id for atom in evidence_atoms}
    unknown_cited = set(cited_ids) - known_ids
    if unknown_cited:
        raise ContextContractError(f"GOAL_PROPOSAL_CITES_UNKNOWN_EVIDENCE:{sorted(unknown_cited)}")

    non_goals = output.get("non_goals") or []
    unknown_refs = output.get("unknown_ids") or []

    return GoalProposal(
        goal_proposal_id=goal_proposal_id,
        scope=scope,
        subject_ids=subject_ids,
        statement=statement,
        desired_change=desired_change,
        success_criteria=tuple(success_criteria),
        evidence_refs=tuple(cited_ids),
        reasoning_ref=reasoning_ref,
        expected_observation=expected_observation,
        measurement_window=measurement_window,
        failure_criteria=tuple(failure_criteria),
        stop_criteria=tuple(stop_criteria),
        escalation_criteria=tuple(escalation_criteria),
        created_at=created_at,
        family_need_ref=family_need_ref,
        non_goals=tuple(non_goals),
        unknown_refs=tuple(unknown_refs),
    )


async def generate_goal_proposal(
    runtime: _AgentRuntimeExecutor,
    *,
    agent_id: str,
    authorization: AgentAuthorization | None,
    request_id: str,
    evidence_atoms: Sequence[WorldStateAtom],
    primary_contradiction_statement: str,
    scope: ContextScope,
    subject_ids: tuple[str, ...],
    context_snapshot_ref: str,
    goal_proposal_id: str,
    family_need_ref: str | None,
    reasoning_ref: str,
    now: datetime,
) -> GoalProposal:
    """The full WM-005 pipeline: evidence + primary contradiction ->
    AgentRuntime call -> validated `GoalProposal`. This is the only function
    in this module that triggers a model execution; every other function
    here is a pure, deterministic step around it. AIFAMILY-FIL-001: the
    execution boundary is `AgentRuntime.execute()`, not a direct
    `ModelGateway` call — see module docstring."""

    task = _build_goal_proposal_agent_task(
        evidence_atoms,
        primary_contradiction_statement=primary_contradiction_statement,
        agent_id=agent_id,
        request_id=request_id,
        context_snapshot_ref=context_snapshot_ref,
        tenant_id=scope.tenant_id,
        family_id=scope.family_id,
        data_class=scope.data_class.value,
    )
    run = await runtime.execute(task, authorization)
    draft = run.draft
    return validate_and_build_goal_proposal(
        draft,
        goal_proposal_id=goal_proposal_id,
        scope=scope,
        subject_ids=subject_ids,
        evidence_atoms=evidence_atoms,
        family_need_ref=family_need_ref,
        reasoning_ref=reasoning_ref,
        created_at=now,
    )


def _build_goal_proposal_agent_task(
    evidence_atoms: Sequence[WorldStateAtom],
    *,
    primary_contradiction_statement: str,
    agent_id: str,
    request_id: str,
    context_snapshot_ref: str,
    tenant_id: str,
    family_id: str,
    data_class: str,
) -> AgentTask:
    """Same ingredients as `build_goal_proposal_request()`, repackaged as an
    `AgentTask` — the shape `AgentRuntime.execute()` requires. Kept separate
    from `build_goal_proposal_request()` because that function's
    `StructuredRequest` output is also usable directly by gated real-model
    livecheck tests that call the gateway themselves rather than through
    AgentRuntime."""

    request = build_goal_proposal_request(
        evidence_atoms,
        primary_contradiction_statement=primary_contradiction_statement,
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
        use_case=GOAL_PROPOSAL_USE_CASE,
        context_snapshot_ref=context_snapshot_ref,
        prompt_version=GOAL_PROPOSAL_PROMPT_VERSION,
        schema_version=GOAL_PROPOSAL_SCHEMA_VERSION,
        data_class=data_class,
        payload=dict(request.payload),
        output_schema=request.output_schema,
        input_refs=request.input_refs,
    )


__all__ = [
    "GOAL_PROPOSAL_PROMPT_VERSION",
    "GOAL_PROPOSAL_SCHEMA_VERSION",
    "GOAL_PROPOSAL_USE_CASE",
    "GoalProposal",
    "build_goal_proposal_request",
    "generate_goal_proposal",
    "goal_proposal_output_schema",
    "validate_and_build_goal_proposal",
]
