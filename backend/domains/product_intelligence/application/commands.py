"""Application service commands — the acceptance-chain creation path
(Override #6 item 2): each `create_*` command loads its parent, so the
chain is provably traceable back to a `MarketSignal`, not just
independently-created rows that happen to share ids.

PR-001R (chief-architect review on PR #27, items 3/4/5): `created_by` and
`tenant_scope` now come exclusively from the caller's `ActorContext`, never
from request parameters. Every parent load is tenant-scoped
(`ports.py` `load_*(entity_id, tenant_scope)`), so a cross-tenant reference
raises `ProductIntelligenceNotFoundError` before any child row can be
created. `generated_by`/`model_ref`/`prompt_use_case_version`/`confidence`
are required together when `context.actor_type == "AI"`.

Permission Pattern (chief-architect review on PR #33): state-transition
guardrails are split across two deliberately separate layers, and this is
not accidental duplication —
  - `domain/entities.py` (e.g. `GrowthHypothesis.mark_validated`) owns
    *state-machine legality*: is this transition ever a legal move for this
    kind of actor, independent of who specifically is calling. It has no
    notion of permissions/roles.
  - `application/commands.py` (here) owns *actor eligibility*: given a real,
    specific caller, is *this* actor allowed to invoke *this* transition
    right now (checked via `context.permissions`). This is where
    fine-grained authorization (e.g.
    `product_intelligence.hypothesis.review`) lives, because permissions are
    an application/authorization concern, not a domain invariant.
Both checks running is intentional defense in depth, not redundancy to be
collapsed into one.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ..domain.entities import (
    CustomerInsight,
    GrowthHypothesis,
    GrowthProblem,
    GrowthStrategy,
    MarketSignal,
    Opportunity,
    ProductConcept,
)
from ..domain.errors import ProductIntelligenceForbiddenError, ProductIntelligenceValidationError
from .context import ActorContext
from .ports import ProductIntelligenceRepositoryPort

HYPOTHESIS_REVIEW_PERMISSION = "product_intelligence.hypothesis.review"


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_ai_provenance_if_ai_actor(
    context: ActorContext, *, model_ref: str | None, prompt_use_case_version: str | None, confidence: float | None,
) -> None:
    """PR-001R item 4: when the calling actor is AI, `model_ref` /
    `prompt_use_case_version` / `confidence` must all be supplied by the
    caller (in addition to the always-required `generated_by` derived from
    `context.actor_id` below) — an AI actor cannot create a record without
    full provenance. `_AiProvenanceFields`'s "all-or-none" validator in
    `domain/entities.py` still applies as a second, independent check.
    """
    if context.actor_type != "AI":
        return
    if model_ref is None or prompt_use_case_version is None or confidence is None:
        raise ProductIntelligenceValidationError("ai_actor_requires_full_provenance")


async def create_market_signal(
    repo: ProductIntelligenceRepositoryPort, context: ActorContext, *, raw_text: str, source_ref: str | None = None,
) -> MarketSignal:
    now = _now()
    signal = MarketSignal(
        id=_new_id("signal"), created_at=now, updated_at=now, created_by=context.actor_id,
        tenant_scope=context.tenant_scope, raw_text=raw_text, source_ref=source_ref,
    )
    await repo.save_market_signal(signal)
    return signal


async def create_customer_insight(
    repo: ProductIntelligenceRepositoryPort, context: ActorContext, *, signal_id: str, statement: str,
    model_ref: str | None = None, prompt_use_case_version: str | None = None, confidence: float | None = None,
) -> CustomerInsight:
    _require_ai_provenance_if_ai_actor(context, model_ref=model_ref, prompt_use_case_version=prompt_use_case_version, confidence=confidence)
    await repo.load_market_signal(signal_id, context.tenant_scope)  # traceability + tenant check
    now = _now()
    generated_by = context.actor_id if context.actor_type == "AI" else None
    insight = CustomerInsight(
        id=_new_id("insight"), created_at=now, updated_at=now, created_by=context.actor_id, tenant_scope=context.tenant_scope,
        statement=statement, signal_id=signal_id, generated_by=generated_by, model_ref=model_ref,
        prompt_use_case_version=prompt_use_case_version, confidence=confidence,
    )
    await repo.save_customer_insight(insight)
    return insight


async def create_opportunity(
    repo: ProductIntelligenceRepositoryPort, context: ActorContext, *, insight_id: str, statement: str,
    model_ref: str | None = None, prompt_use_case_version: str | None = None, confidence: float | None = None,
) -> Opportunity:
    _require_ai_provenance_if_ai_actor(context, model_ref=model_ref, prompt_use_case_version=prompt_use_case_version, confidence=confidence)
    await repo.load_customer_insight(insight_id, context.tenant_scope)
    now = _now()
    generated_by = context.actor_id if context.actor_type == "AI" else None
    opportunity = Opportunity(
        id=_new_id("opp"), created_at=now, updated_at=now, created_by=context.actor_id, tenant_scope=context.tenant_scope,
        insight_id=insight_id, statement=statement, generated_by=generated_by, model_ref=model_ref,
        prompt_use_case_version=prompt_use_case_version, confidence=confidence,
    )
    await repo.save_opportunity(opportunity)
    return opportunity


async def create_growth_problem(
    repo: ProductIntelligenceRepositoryPort, context: ActorContext, *, opportunity_id: str, symptom: str,
) -> GrowthProblem:
    await repo.load_opportunity(opportunity_id, context.tenant_scope)
    now = _now()
    problem = GrowthProblem(
        id=_new_id("problem"), created_at=now, updated_at=now, created_by=context.actor_id, tenant_scope=context.tenant_scope,
        symptom=symptom, opportunity_id=opportunity_id,
    )
    await repo.save_growth_problem(problem)
    return problem


async def create_growth_hypothesis(
    repo: ProductIntelligenceRepositoryPort, context: ActorContext, *, problem_id: str, statement: str,
    model_ref: str | None = None, prompt_use_case_version: str | None = None, confidence: float | None = None,
) -> GrowthHypothesis:
    _require_ai_provenance_if_ai_actor(context, model_ref=model_ref, prompt_use_case_version=prompt_use_case_version, confidence=confidence)
    await repo.load_growth_problem(problem_id, context.tenant_scope)
    now = _now()
    generated_by = context.actor_id if context.actor_type == "AI" else None
    # Rule (Override #6 item 3 / instruction 03 rule 4): status is always
    # DRAFT at creation regardless of actor — no path here sets VALIDATED.
    # Only `GrowthHypothesis.mark_validated()` can, and only via
    # `validate_growth_hypothesis` below, which requires actor_type=HUMAN.
    hypothesis = GrowthHypothesis(
        id=_new_id("hyp"), created_at=now, updated_at=now, created_by=context.actor_id, tenant_scope=context.tenant_scope,
        problem_id=problem_id, statement=statement, generated_by=generated_by, model_ref=model_ref,
        prompt_use_case_version=prompt_use_case_version, confidence=confidence,
    )
    await repo.save_growth_hypothesis(hypothesis)
    return hypothesis


async def create_growth_strategy(
    repo: ProductIntelligenceRepositoryPort, context: ActorContext, *, problem_id: str, hypothesis_ids: list[str],
    statement: str, model_ref: str | None = None, prompt_use_case_version: str | None = None, confidence: float | None = None,
) -> GrowthStrategy:
    _require_ai_provenance_if_ai_actor(context, model_ref=model_ref, prompt_use_case_version=prompt_use_case_version, confidence=confidence)
    await repo.load_growth_problem(problem_id, context.tenant_scope)
    for hid in hypothesis_ids:
        await repo.load_growth_hypothesis(hid, context.tenant_scope)  # traceability + tenant check per hypothesis
    now = _now()
    generated_by = context.actor_id if context.actor_type == "AI" else None
    strategy = GrowthStrategy(
        id=_new_id("strategy"), created_at=now, updated_at=now, created_by=context.actor_id, tenant_scope=context.tenant_scope,
        problem_id=problem_id, hypothesis_ids=hypothesis_ids, statement=statement,
        generated_by=generated_by, model_ref=model_ref, prompt_use_case_version=prompt_use_case_version, confidence=confidence,
    )
    await repo.save_growth_strategy(strategy)
    return strategy


async def create_product_concept(
    repo: ProductIntelligenceRepositoryPort, context: ActorContext, *, strategy_id: str, title: str,
    description: str | None = None, model_ref: str | None = None, prompt_use_case_version: str | None = None,
    confidence: float | None = None,
) -> ProductConcept:
    _require_ai_provenance_if_ai_actor(context, model_ref=model_ref, prompt_use_case_version=prompt_use_case_version, confidence=confidence)
    await repo.load_growth_strategy(strategy_id, context.tenant_scope)
    now = _now()
    generated_by = context.actor_id if context.actor_type == "AI" else None
    concept = ProductConcept(
        id=_new_id("concept"), created_at=now, updated_at=now, created_by=context.actor_id, tenant_scope=context.tenant_scope,
        strategy_id=strategy_id, title=title, description=description,
        generated_by=generated_by, model_ref=model_ref, prompt_use_case_version=prompt_use_case_version, confidence=confidence,
    )
    await repo.save_product_concept(concept)
    return concept


async def validate_growth_hypothesis(
    repo: ProductIntelligenceRepositoryPort, context: ActorContext, *, hypothesis_id: str, reason: str,
) -> GrowthHypothesis:
    """The only path in this domain that can move a hypothesis to
    VALIDATED — requires `context.actor_type == "HUMAN"`, enforced inside
    `GrowthHypothesis.mark_validated`, not by inspecting a client-supplied
    field.

    Application Policy gate (added on top of the domain check, see module
    docstring): the caller must additionally hold the
    `product_intelligence.hypothesis.review` permission. `mark_validated`
    still independently re-checks `actor_type == "HUMAN"` below — that is
    intentional, not dead code to remove; see the "Permission Pattern" note
    at the top of this file.
    """
    if context.actor_type != "HUMAN" or HYPOTHESIS_REVIEW_PERMISSION not in context.permissions:
        raise ProductIntelligenceForbiddenError("hypothesis_review_permission_required")

    hypothesis = await repo.load_growth_hypothesis(hypothesis_id, context.tenant_scope)
    validated = hypothesis.mark_validated(actor_id=context.actor_id, actor_type=context.actor_type, reason=reason)
    await repo.save_growth_hypothesis(validated)
    return validated
