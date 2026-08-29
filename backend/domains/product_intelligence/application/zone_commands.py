"""Application service commands for the Product Zone (Three-Zone Strategy
Engine) governance lifecycle — `architecture/ADR_PRODUCT_ZONE_GOVERNANCE_V0.md`.

Same Permission Pattern split as `commands.py` (see that module's docstring):
`domain/zone_entities.py::ProductZoneAssessment.transition_to` owns
*state-machine legality* (legal from/to per
`zone_value_objects.ZONE_ASSESSMENT_STATUS_TRANSITIONS`, the evidence gate,
the `approved_zone`/`override_reason` pairing) and deliberately does NOT
check `actor_type`/permissions — that check lives here, in the application
layer, exactly as `transition_to`'s own docstring states ("that is the
application layer's (Agent B's) responsibility").

Integration fix (Agent G), applied after all of A/B/C/D/E's work landed —
two items Agent B flagged explicitly as known gaps in the original version
of this module, both resolved here rather than carried forward:

1. DRAFT-stage `dimension_assessments`: `zone_entities.py`'s validator now
   allows an empty list while `status == "DRAFT"` (see that module's
   updated `_dimension_assessments_cover_all_six_exactly_once` and
   `transition_to`) — Option (b) from Agent B's original note, not the
   placeholder-row workaround (Option (a)) this module used to carry.
   `create_zone_assessment` below constructs DRAFT with `[]`, not six fake
   rows.
2. Cross-tenant `product_concept_id` reference: `create_zone_assessment`
   now takes a second port, `ProductIntelligenceRepositoryPort`
   (`application/ports.py`), and calls its tenant-scoped
   `load_product_concept(product_concept_id, context.tenant_scope)` before
   creating the assessment — the same "load raises NotFoundError on
   cross-tenant, not a distinguishable Forbidden" pattern PR-001R already
   uses everywhere else in this domain. This composes the two ports at the
   call site precisely because Agent B's `ZoneAssessmentRepositoryPort` had
   no way to see `ProductConcept` rows — that separation of ports was
   correct; the gap was that nothing composed them until now.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ..domain.errors import ProductIntelligenceForbiddenError, ProductIntelligenceValidationError
from ..domain.zone_entities import DimensionAssessment, ProductZoneAssessment
from ..domain.zone_scoring_engine import score_assessment
from .context import ActorContext
from .ports import ProductIntelligenceRepositoryPort
from .zone_ports import ZoneAssessmentRepositoryPort

ZONE_REVIEW_PERMISSION = "product_intelligence.zone.review"


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_zone_review_permission(context: ActorContext) -> None:
    """ADR-Governance §4 frozen rule: `approved_zone` can only be set by
    `actor_type == "HUMAN"` AND `ZONE_REVIEW_PERMISSION in permissions`.
    `AI`/`SYSTEM` are forbidden regardless of any permission string they
    might carry.
    """
    if context.actor_type != "HUMAN" or ZONE_REVIEW_PERMISSION not in context.permissions:
        raise ProductIntelligenceForbiddenError("zone_review_permission_required")


async def create_zone_assessment(
    repo: ZoneAssessmentRepositoryPort,
    product_intelligence_repo: ProductIntelligenceRepositoryPort,
    context: ActorContext,
    *,
    product_concept_id: str,
    zone_policy_version_id: str,
) -> ProductZoneAssessment:
    """Creates a `DRAFT` `ProductZoneAssessment` for `product_concept_id`.

    Takes `product_intelligence_repo` (`application/ports.py`) specifically
    to call its tenant-scoped `load_product_concept` — this raises
    `ProductIntelligenceNotFoundError` if `product_concept_id` does not
    exist or belongs to a different tenant, before any assessment row is
    created. See module docstring "Integration fix" item 2.
    """
    await product_intelligence_repo.load_product_concept(product_concept_id, context.tenant_scope)

    now = _now()
    assessment = ProductZoneAssessment(
        id=_new_id("zoneassess"),
        created_at=now,
        updated_at=now,
        created_by=context.actor_id,
        tenant_scope=context.tenant_scope,
        status="DRAFT",
        subject_ref=product_concept_id,
        zone_policy_version_id=zone_policy_version_id,
        dimension_assessments=[],
        # Indices/scores/recommended_zone are unset/meaningless at DRAFT —
        # zeroed here (not computed) because the scoring engine is the only
        # legitimate source of these numbers (ADR-Governance §2: "computed
        # by the scoring engine, not by the constructor"); `score_zone_
        # assessment` overwrites all five below.
        differentiation_index=0.0,
        defensibility_index=0.0,
        commodity_score=0.0,
        advantage_score=0.0,
        unique_score=0.0,
        recommended_zone="COMMODITY",
        assessment_origin="HUMAN" if context.actor_type == "HUMAN" else ("AI_PROPOSAL" if context.actor_type == "AI" else "RULE"),
    )
    await repo.save_zone_assessment(assessment)
    return assessment


async def score_zone_assessment(
    repo: ZoneAssessmentRepositoryPort,
    context: ActorContext,
    *,
    assessment_id: str,
    dimension_assessments: list[dict],
) -> ProductZoneAssessment:
    """DRAFT -> SCORED. Replaces the entire `dimension_assessments` list
    (never a partial merge — see module docstring) with the caller's real
    six-dimension input, computes the three scores + `recommended_zone` via
    `zone_scoring_engine.score_assessment` against the currently-ACTIVE
    `ZonePolicyVersion`, then transitions via `transition_to` (which
    re-validates the evidence gate and the DRAFT->SCORED legality).

    No permission gate here deliberately: scoring is a computation, not a
    review decision (ADR-Governance §4's permission gate is specifically
    about setting `approved_zone`/entering `APPROVED`, not about running
    the deterministic scoring formula). Any actor type may trigger scoring.
    """
    assessment = await repo.load_zone_assessment(assessment_id, context.tenant_scope)
    policy = await repo.load_active_zone_policy_version(context.tenant_scope)

    now = _now()
    new_dimension_assessments = [
        DimensionAssessment(
            dimension=d["dimension"],
            score=d["score"],
            rationale=d["rationale"],
            evidence_refs=d["evidence_refs"],
            evidence_strength=d.get("evidence_strength", 0.5),
            assessed_by=d.get("assessed_by", context.actor_id),
            assessed_at=d.get("assessed_at", now),
        )
        for d in dimension_assessments
    ]

    (
        differentiation_index,
        defensibility_index,
        commodity_score,
        advantage_score,
        unique_score,
        recommended_zone,
    ) = score_assessment(new_dimension_assessments, policy)

    scored = assessment.model_copy(
        update={
            "dimension_assessments": new_dimension_assessments,
            "differentiation_index": differentiation_index,
            "defensibility_index": defensibility_index,
            "commodity_score": commodity_score,
            "advantage_score": advantage_score,
            "unique_score": unique_score,
            "recommended_zone": recommended_zone,
            "zone_policy_version_id": policy.policy_id,
        }
    )
    scored = scored.transition_to(new_status="SCORED", actor_id=context.actor_id)
    await repo.save_zone_assessment(scored)
    return scored


async def submit_zone_review(
    repo: ZoneAssessmentRepositoryPort,
    context: ActorContext,
    *,
    assessment_id: str,
) -> ProductZoneAssessment:
    """SCORED -> UNDER_REVIEW.

    Permission judgment call (ADR-Governance does not explicitly rule on
    "who may submit for review", only on "who may approve" — §4's frozen
    rule is scoped to `approved_zone`/entering `APPROVED`). This command
    takes the conservative reading: submitting for review is a lesser act
    than approving it (it does not set `approved_zone`, does not require
    `ZONE_REVIEW_PERMISSION`), but per ADR-Governance §5 ("AI/SYSTEM actors
    cannot cause any transition into APPROVED") and the general spirit of
    "a human must be in the loop for anything entering the review
    pipeline", this command still requires `context.actor_type == "HUMAN"`
    — an AI/SYSTEM actor cannot even *initiate* a review, only a human
    can decide "this is ready for review". No extra permission string is
    required beyond being HUMAN: this is a deliberately lower bar than
    `approve_zone_assessment`/`reject_zone_assessment`, which both require
    `ZONE_REVIEW_PERMISSION` in addition to `actor_type == "HUMAN"`.
    """
    if context.actor_type != "HUMAN":
        raise ProductIntelligenceForbiddenError("zone_review_submission_requires_human_actor")

    assessment = await repo.load_zone_assessment(assessment_id, context.tenant_scope)
    submitted = assessment.transition_to(new_status="UNDER_REVIEW", actor_id=context.actor_id)
    await repo.save_zone_assessment(submitted)
    return submitted


async def approve_zone_assessment(
    repo: ZoneAssessmentRepositoryPort,
    context: ActorContext,
    *,
    assessment_id: str,
    approved_zone: str,
    review_reason: str,
    override_reason: str | None = None,
) -> ProductZoneAssessment:
    """UNDER_REVIEW -> APPROVED. Hard permission gate per ADR-Governance §4:
    `context.actor_type == "HUMAN"` AND `ZONE_REVIEW_PERMISSION in
    context.permissions`, else `ProductIntelligenceForbiddenError` —
    checked BEFORE any load/transition so an unauthorized caller cannot
    even trigger a load (defense in depth, no information leak either).

    Override-reason pre-check: `ProductZoneAssessment`'s own
    `model_validator` (`_override_reason_required_when_approved_zone_
    diverges`) already rejects `approved_zone != recommended_zone` without
    `override_reason` — but that validator fires as a `pydantic`/domain
    `ProductIntelligenceValidationError` only once the application layer
    has already constructed the candidate object via `model_copy`. This
    command checks the same condition explicitly, first, so the error
    message is unambiguous about *why* (`zone_override_requires_reason`)
    rather than relying on the entity's more generic validation error to
    surface correctly through whatever call path invoked this command;
    it is intentional double-checking (matching this module's own
    "defense in depth, not redundancy to collapse" convention from
    `commands.py`), not a belief that the entity-level check is wrong.

    Multi-reviewer extension point (ADR-Governance §4 `review_policy.
    unique_requires_reviewers`): V0's fixture policy is fixed at `1`, and
    this command applies the policy as a single-call, single-actor
    approval — one `approve_zone_assessment` call transitions straight to
    `APPROVED`. If a future `ZonePolicyVersion.review_policy[
    "unique_requires_reviewers"]` is ever raised above `1`, this function
    signature is NOT sufficient as-is: it would need to (a) stop
    transitioning straight to `APPROVED` on the first qualifying approve
    call, (b) accumulate distinct HUMAN reviewer ids in a new field (e.g.
    a `reviewed_by_history: list[str]` on the entity, which does not exist
    today — `zone_entities.py` only has a single `reviewed_by: str | None`),
    and (c) only call `transition_to(new_status="APPROVED", ...)` once the
    accumulated distinct-reviewer count meets the policy's requirement.
    None of that is implemented here — V0's `review_policy` is always `1`,
    so this straight-through single-call approval is correct for V0 and
    this comment exists purely so a future policy bump doesn't get wired
    into this function without noticing it needs a shape change first.
    """
    _require_zone_review_permission(context)

    assessment = await repo.load_zone_assessment(assessment_id, context.tenant_scope)

    if approved_zone != assessment.recommended_zone and not override_reason:
        raise ProductIntelligenceValidationError("zone_override_requires_reason")

    updated = assessment.model_copy(
        update={
            "approved_zone": approved_zone,
            "override_reason": override_reason,
        }
    )
    approved = updated.transition_to(
        new_status="APPROVED", actor_id=context.actor_id, reason=review_reason,
    )
    await repo.save_zone_assessment(approved)
    return approved


async def reject_zone_assessment(
    repo: ZoneAssessmentRepositoryPort,
    context: ActorContext,
    *,
    assessment_id: str,
    review_reason: str,
) -> ProductZoneAssessment:
    """UNDER_REVIEW -> REJECTED.

    Permission judgment call: ADR-Governance §4 only names `approved_zone`
    in its frozen permission rule, not `REJECTED` explicitly. This command
    treats reject as the same tier of formal economic judgment as approve
    (a reviewer looked at the evidence and made a decision either way —
    rejecting a UNIQUE-claim assessment is exactly as consequential as
    approving one) and therefore requires the identical gate:
    `actor_type == "HUMAN"` AND `ZONE_REVIEW_PERMISSION in permissions`.
    The alternative reading (reject is "safe" so anyone can do it) would
    let an unauthorized actor block/stall a review pipeline outcome, which
    is its own form of governance bypass — so the stricter reading is
    applied.
    """
    _require_zone_review_permission(context)

    assessment = await repo.load_zone_assessment(assessment_id, context.tenant_scope)
    rejected = assessment.transition_to(
        new_status="REJECTED", actor_id=context.actor_id, reason=review_reason,
    )
    await repo.save_zone_assessment(rejected)
    return rejected


async def retire_zone_assessment(
    repo: ZoneAssessmentRepositoryPort,
    context: ActorContext,
    *,
    assessment_id: str,
    reason: str,
) -> ProductZoneAssessment:
    """APPROVED -> RETIRED.

    Permission judgment call: retiring an already-APPROVED assessment is
    withdrawing a prior formal governance decision, not making a new
    scoring/review judgment call from evidence — but it still changes
    what a portfolio view treats as "currently valid", so this command
    applies the same `ZONE_REVIEW_PERMISSION` gate as approve/reject
    rather than leaving retirement ungated. No ADR text contradicts this;
    it is the same "when in doubt, match the strictest adjacent rule"
    reasoning as `reject_zone_assessment` above.
    """
    _require_zone_review_permission(context)

    assessment = await repo.load_zone_assessment(assessment_id, context.tenant_scope)
    retired = assessment.transition_to(
        new_status="RETIRED", actor_id=context.actor_id, reason=reason,
    )
    await repo.save_zone_assessment(retired)
    return retired
