"""Application service commands for PR-003 V1 (Contradiction & Strategy
Intelligence): `GrowthProblem` -> multi-`GrowthHypothesis` ->
`ContradictionModel` -> `ValueArchitecture` -> `GrowthStrategy`.

Same Permission Pattern split as `commands.py`/`zone_commands.py`: the
domain layer (`ContradictionModel.decide_review`/`mark_primary`) owns
state-machine legality and `actor_type == HUMAN`; this module owns whether
*this specific* actor is allowed to invoke the transition
(`product_intelligence.contradiction.review` permission), and composes the
tenant-scoped parent-loading checks every command in this domain uses.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ..domain.entities import ContradictionModel, ValueArchitecture
from ..domain.errors import ProductIntelligenceForbiddenError, ProductIntelligenceValidationError
from .context import ActorContext
from .ports import ProductIntelligenceRepositoryPort

CONTRADICTION_REVIEW_PERMISSION = "product_intelligence.contradiction.review"


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def _now() -> datetime:
    return datetime.now(UTC)


def _require_contradiction_review_permission(context: ActorContext) -> None:
    if context.actor_type != "HUMAN" or CONTRADICTION_REVIEW_PERMISSION not in context.permissions:
        raise ProductIntelligenceForbiddenError("contradiction_review_permission_required")


async def create_contradiction_model(
    repo: ProductIntelligenceRepositoryPort,
    context: ActorContext,
    *,
    problem_id: str,
    hypothesis_ids: list[str],
    primary_factor_a: str,
    primary_factor_b: str,
    relationship: str,
    description: str | None = None,
    evidence_refs: list[str] | None = None,
) -> ContradictionModel:
    """Creates a `DRAFT` `ContradictionModel`. Requires >= 2 hypothesis ids
    (enforced by the entity's own validator) all belonging to `problem_id`
    and the caller's tenant — traceability + tenant check per hypothesis,
    same pattern `create_growth_strategy` uses.
    """
    await repo.load_growth_problem(problem_id, context.tenant_scope)
    for hid in hypothesis_ids:
        hypothesis = await repo.load_growth_hypothesis(hid, context.tenant_scope)
        if hypothesis.problem_id != problem_id:
            raise ProductIntelligenceValidationError(
                "contradiction_hypothesis_must_belong_to_same_problem"
            )
    now = _now()
    contradiction = ContradictionModel(
        id=_new_id("contradiction"),
        created_at=now,
        updated_at=now,
        created_by=context.actor_id,
        tenant_scope=context.tenant_scope,
        problem_id=problem_id,
        primary_factor_a=primary_factor_a,
        primary_factor_b=primary_factor_b,
        relationship=relationship,
        description=description,
        supporting_hypothesis_ids=hypothesis_ids,
        evidence_refs=evidence_refs or [],
        generated_by=context.actor_id if context.actor_type == "AI" else None,
    )
    await repo.save_contradiction_model(contradiction)
    return contradiction


async def submit_contradiction_for_review(
    repo: ProductIntelligenceRepositoryPort, context: ActorContext, *, contradiction_id: str
) -> ContradictionModel:
    contradiction = await repo.load_contradiction_model(contradiction_id, context.tenant_scope)
    submitted = contradiction.submit_for_review()
    await repo.save_contradiction_model(submitted)
    return submitted


async def decide_contradiction_review(
    repo: ProductIntelligenceRepositoryPort,
    context: ActorContext,
    *,
    contradiction_id: str,
    approved: bool,
    reason: str,
) -> ContradictionModel:
    """The only path that can move a contradiction to APPROVED/REJECTED —
    requires `product_intelligence.contradiction.review`, checked here;
    `actor_type == HUMAN` is checked again inside
    `ContradictionModel.decide_review` (defense in depth, not redundant —
    same reasoning as `zone_commands.approve_zone_assessment`).
    """
    _require_contradiction_review_permission(context)
    contradiction = await repo.load_contradiction_model(contradiction_id, context.tenant_scope)
    decided = contradiction.decide_review(
        approved=approved, actor_id=context.actor_id, actor_type=context.actor_type, reason=reason
    )
    await repo.save_contradiction_model(decided)
    return decided


async def mark_contradiction_primary(
    repo: ProductIntelligenceRepositoryPort,
    context: ActorContext,
    *,
    contradiction_id: str,
    rank: int = 1,
) -> ContradictionModel:
    """Marks one `APPROVED` contradiction as *the* primary one for its
    `GrowthProblem`. Requires the same review permission as approving one —
    "which contradiction currently drives strategy" is itself a strategic
    call, not a bookkeeping detail. Enforces "at most one primary per
    problem" by demoting any other contradiction on the same problem that
    currently holds `primary_rank` — this is the cross-entity check
    `ContradictionModel.mark_primary` itself cannot make (a single entity
    method cannot see its siblings).
    """
    _require_contradiction_review_permission(context)
    contradiction = await repo.load_contradiction_model(contradiction_id, context.tenant_scope)
    siblings = await repo.list_contradiction_models_by_problem(
        contradiction.problem_id, context.tenant_scope
    )
    for sibling in siblings:
        if sibling.id != contradiction_id and sibling.primary_rank is not None:
            now = _now()
            demoted = sibling.model_copy(
                update={
                    "primary_rank": None,
                    "primary_marked_by": None,
                    "primary_marked_at": None,
                    "updated_at": now,
                    "version": sibling.version + 1,
                }
            )
            await repo.save_contradiction_model(demoted)
    marked = contradiction.mark_primary(rank=rank, actor_id=context.actor_id)
    await repo.save_contradiction_model(marked)
    return marked


async def create_value_architecture(
    repo: ProductIntelligenceRepositoryPort,
    context: ActorContext,
    *,
    problem_id: str,
    emotional_current_state: str,
    emotional_desired_state: str,
    action_next_best_action: str,
    rationale: str,
    evidence_refs: list[str],
    growth_outcomes: list[str] | None = None,
    economic_outcomes: list[str] | None = None,
) -> ValueArchitecture:
    """Creates a `ValueArchitecture` for `problem_id` — the project owner's
    four-layer value model (情绪→行动→成长→经济), a formal input to
    `GrowthStrategy` per PR-003 V1. `evidence_refs` non-emptiness is
    enforced by the entity itself; this command only adds the tenant-scoped
    parent check.
    """
    await repo.load_growth_problem(problem_id, context.tenant_scope)
    now = _now()
    value_architecture = ValueArchitecture(
        id=_new_id("valuearch"),
        created_at=now,
        updated_at=now,
        created_by=context.actor_id,
        tenant_scope=context.tenant_scope,
        problem_id=problem_id,
        emotional_current_state=emotional_current_state,
        emotional_desired_state=emotional_desired_state,
        action_next_best_action=action_next_best_action,
        growth_outcomes=growth_outcomes or [],
        economic_outcomes=economic_outcomes or [],
        rationale=rationale,
        evidence_refs=evidence_refs,
        generated_by=context.actor_id if context.actor_type == "AI" else None,
    )
    await repo.save_value_architecture(value_architecture)
    return value_architecture
