"""Independent adversarial test suite for the Product Zone (Three-Zone
Strategy Engine) governance slice — PR-002 Agent E.

This file does NOT modify any production code and does NOT modify any other
Agent's test file. It is a standalone cross-check against the total-suite
checklist handed down by the chief architect. Most items on that checklist
are already covered by Agent A's `test_zone_scoring.py` (domain-only) and
Agent B's `test_zone_review_governance.py` (application-layer); this file
explicitly does NOT duplicate those and instead:

1. Confirms (via a short smoke assertion, not a full re-test) that a
   checklist item is already exercised elsewhere, documenting *where*.
2. Adds real new coverage for items the chief architect flagged as
   possibly-missing: policy-version historical immutability, cross-tenant
   `ProductConcept` reference (a known, flagged gap — see
   `application/zone_commands.py::create_zone_assessment` docstring,
   "Tenancy judgment call"), and APPROVED-state immutability-via-model_copy.

Uses its own local `ActorContext` fixtures carrying
`ZONE_REVIEW_PERMISSION` (`product_intelligence.zone.review`) — per the task
brief, `conftest.py`'s shared `human_context`/`ai_context`/
`other_tenant_human_context` fixtures intentionally do NOT carry this
permission (they carry the older `product_intelligence.hypothesis.review`
only), and `conftest.py` is explicitly out of scope to edit here.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ..application import zone_commands
from ..application.context import ActorContext
from ..domain.entities import ProductConcept
from ..domain.errors import (
    ProductIntelligenceForbiddenError,
    ProductIntelligenceNotFoundError,
    ProductIntelligenceValidationError,
)
from ..domain.zone_entities import DimensionAssessment, ProductZoneAssessment, ZonePolicyVersion
from ..domain.zone_scoring_engine import score_assessment
from ..infrastructure.fake_repository import FakeProductIntelligenceRepository
from ..infrastructure.zone_fake_repository import FakeZoneAssessmentRepository

UTC_NOW = datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc)

ZONE_REVIEW_PERMISSION = zone_commands.ZONE_REVIEW_PERMISSION


# ---------------------------------------------------------------------------
# Local fixtures (this file's own ActorContexts; conftest.py untouched)
# ---------------------------------------------------------------------------


@pytest.fixture
def repo() -> FakeZoneAssessmentRepository:
    return FakeZoneAssessmentRepository()


def _reviewer_context(tenant_scope: str = "tenant-a") -> ActorContext:
    """HUMAN + ZONE_REVIEW_PERMISSION. Local to this file — see module
    docstring for why `conftest.py`'s shared fixtures are not reused here."""
    return ActorContext(
        actor_id="human-reviewer-adversarial",
        actor_type="HUMAN",
        tenant_scope=tenant_scope,
        permissions=frozenset({ZONE_REVIEW_PERMISSION}),
    )


def _human_no_permission_context(tenant_scope: str = "tenant-a") -> ActorContext:
    return ActorContext(
        actor_id="human-no-perm-adversarial", actor_type="HUMAN", tenant_scope=tenant_scope, permissions=frozenset(),
    )


def _ai_context(tenant_scope: str = "tenant-a") -> ActorContext:
    return ActorContext(actor_id="ai-agent-adversarial", actor_type="AI", tenant_scope=tenant_scope)


def _system_context(tenant_scope: str = "tenant-a") -> ActorContext:
    return ActorContext(actor_id="system-job-adversarial", actor_type="SYSTEM", tenant_scope=tenant_scope)


def _build_policy(**overrides) -> ZonePolicyVersion:
    defaults = dict(
        policy_id="zone-policy-v0",
        version=1,
        dimension_definitions={
            "customer_scarcity": "positive",
            "replaceability": "negative",
            "data_advantage": "positive",
            "network_effect": "positive",
            "learning_effect": "positive",
            "switching_cost": "positive",
        },
        weights={
            "customer_scarcity": 1.0,
            "replaceability": 1.0,
            "data_advantage": 1.0,
            "network_effect": 1.0,
            "learning_effect": 1.0,
            "switching_cost": 1.0,
        },
        thresholds={
            "unique_defensibility_min": 75.0,
            "unique_floor_gate_min": 50.0,
            "commodity_differentiation_max": 40.0,
            "commodity_defensibility_max": 40.0,
        },
        classification_rules="UNIQUE if defensibility>=75 and floor>=50; COMMODITY if diff<40 and def<40; else ADVANTAGE",
        review_policy={"unique_requires_reviewers": 1},
        effective_from=UTC_NOW,
        status="ACTIVE",
    )
    defaults.update(overrides)
    return ZonePolicyVersion(**defaults)


def _pi_repo_with_concept(
    concept_id: str = "concept-adversarial-1", tenant_scope: str = "tenant-a",
) -> FakeProductIntelligenceRepository:
    """Seeds a minimal real `ProductConcept` directly (bypassing the full
    Signal->...->ProductConcept chain, since these zone-engine tests only
    need `load_product_concept` to succeed for the given id/tenant, not a
    real chain history) — integration fix, see `zone_commands.py`'s
    `create_zone_assessment` docstring item 2.
    """
    repo = FakeProductIntelligenceRepository()
    now = datetime.now(timezone.utc)
    concept = ProductConcept(
        id=concept_id, created_at=now, updated_at=now, created_by="test-fixture",
        tenant_scope=tenant_scope, strategy_id="stub-strategy-1", title="stub product concept",
    )
    repo._product_concepts[concept_id] = concept
    return repo


def _high_dimension_input(score: float = 90.0) -> list[dict]:
    return [
        {
            "dimension": dimension,
            "score": score,
            "rationale": "strong signal",
            "evidence_refs": [f"evidence-{dimension}"],
            "evidence_strength": 0.8,
            "assessed_by": "human-scorer-adversarial",
            "assessed_at": UTC_NOW,
        }
        for dimension in (
            "customer_scarcity",
            "replaceability",
            "data_advantage",
            "network_effect",
            "learning_effect",
            "switching_cost",
        )
    ]


def _build_dimension_assessment(dimension: str, score: float, **overrides) -> DimensionAssessment:
    defaults = dict(
        dimension=dimension,
        score=score,
        rationale=f"rationale for {dimension}",
        evidence_refs=[f"evidence:{dimension}:1"],
        evidence_strength=0.7,
        assessed_by="analyst-adversarial",
        assessed_at=UTC_NOW,
    )
    defaults.update(overrides)
    return DimensionAssessment(**defaults)


def _build_six_dimensions(**dimension_scores: float) -> list[DimensionAssessment]:
    defaults = dict(
        customer_scarcity=90.0,
        replaceability=10.0,
        data_advantage=90.0,
        network_effect=90.0,
        learning_effect=90.0,
        switching_cost=90.0,
    )
    defaults.update(dimension_scores)
    return [_build_dimension_assessment(name, score) for name, score in defaults.items()]


def _build_assessment(dimension_assessments, policy, **overrides) -> ProductZoneAssessment:
    (
        differentiation_index,
        defensibility_index,
        commodity_score,
        advantage_score,
        unique_score,
        recommended_zone,
    ) = score_assessment(dimension_assessments, policy)

    defaults = dict(
        id="zone-assessment-adversarial-1",
        created_at=UTC_NOW,
        updated_at=UTC_NOW,
        created_by="analyst-adversarial",
        tenant_scope="tenant-a",
        subject_ref="product-concept-adversarial-1",
        zone_policy_version_id=policy.policy_id,
        dimension_assessments=dimension_assessments,
        differentiation_index=differentiation_index,
        defensibility_index=defensibility_index,
        commodity_score=commodity_score,
        advantage_score=advantage_score,
        unique_score=unique_score,
        recommended_zone=recommended_zone,
    )
    defaults.update(overrides)
    return ProductZoneAssessment(**defaults)


async def _scored_assessment(repo, *, dimension_input=None, context=None) -> ProductZoneAssessment:
    await repo.save_zone_policy_version(_build_policy())
    context = context or _reviewer_context()
    pi_repo = _pi_repo_with_concept(concept_id="concept-adversarial-1", tenant_scope=context.tenant_scope)
    draft = await zone_commands.create_zone_assessment(
        repo, pi_repo, context, product_concept_id="concept-adversarial-1", zone_policy_version_id="zone-policy-v0",
    )
    return await zone_commands.score_zone_assessment(
        repo, context, assessment_id=draft.id, dimension_assessments=dimension_input or _high_dimension_input(),
    )


async def _under_review_assessment(repo, **kwargs) -> ProductZoneAssessment:
    scored = await _scored_assessment(repo, **kwargs)
    return await zone_commands.submit_zone_review(repo, _reviewer_context(), assessment_id=scored.id)


# ---------------------------------------------------------------------------
# 1. Score bounds — already covered by Agent A
#    (test_zone_scoring.py::test_dimension_assessment_rejects_score_above_100
#     / ::test_dimension_assessment_rejects_score_below_0). Smoke-check only,
#    from this file's own construction path, to confirm the gate is not
#    accidentally bypassable through a different call shape.
# ---------------------------------------------------------------------------


def test_score_above_100_rejected_smoke():
    with pytest.raises(ValidationError):
        _build_dimension_assessment("customer_scarcity", 100.0001)


def test_score_below_0_rejected_smoke():
    with pytest.raises(ValidationError):
        _build_dimension_assessment("customer_scarcity", -0.0001)


# ---------------------------------------------------------------------------
# 2. Replaceability direction — already covered by Agent A
#    (test_zone_scoring.py::test_inverse_replaceability_flips_direction and
#    ::test_two_assessments_differing_only_in_replaceability_diverge_in_
#    differentiation_index). No new test added; confirmed by inspection.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 3. Same inputs + same policy = same result — already covered by Agent A
#    (test_zone_scoring.py::test_score_assessment_is_deterministic_across_
#    repeated_calls). No new test added; confirmed by inspection.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 4. Different policy version preserves old historical result — chief
#    architect flagged this as possibly uncovered. NEW test.
#
# Claim under test: nothing in this codebase recomputes/overwrites a
# persisted assessment's stored zone/score fields when a newer
# `ZonePolicyVersion` becomes ACTIVE. The only code path that computes
# `recommended_zone`/indices is `score_zone_assessment`, which is invoked
# once per assessment by a caller providing explicit dimension input — there
# is no "re-score all assessments under the new policy" job anywhere in
# `application/zone_commands.py`. This test proves that empirically: score
# an assessment under policy v1, then activate a stricter policy v2, then
# re-load the v1 assessment from the repository and assert every stored
# field (including `zone_policy_version_id`) is untouched.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_different_policy_version_preserves_old_historical_result(repo):
    policy_v1 = _build_policy(policy_id="zone-policy-v1", version=1)
    await repo.save_zone_policy_version(policy_v1)

    context = _reviewer_context()
    pi_repo = _pi_repo_with_concept(concept_id="concept-historical-1", tenant_scope=context.tenant_scope)
    draft = await zone_commands.create_zone_assessment(
        repo, pi_repo, context, product_concept_id="concept-historical-1", zone_policy_version_id="zone-policy-v1",
    )
    scored_under_v1 = await zone_commands.score_zone_assessment(
        repo, context, assessment_id=draft.id, dimension_assessments=_high_dimension_input(score=90.0),
    )
    assert scored_under_v1.recommended_zone == "UNIQUE"
    assert scored_under_v1.zone_policy_version_id == "zone-policy-v1"

    # Snapshot every scored/classification field before the new policy exists.
    frozen_snapshot = {
        "recommended_zone": scored_under_v1.recommended_zone,
        "differentiation_index": scored_under_v1.differentiation_index,
        "defensibility_index": scored_under_v1.defensibility_index,
        "commodity_score": scored_under_v1.commodity_score,
        "advantage_score": scored_under_v1.advantage_score,
        "unique_score": scored_under_v1.unique_score,
        "zone_policy_version_id": scored_under_v1.zone_policy_version_id,
    }

    # A new, much stricter policy version (v2) becomes ACTIVE. If any code
    # path silently recomputed historical assessments against the new active
    # policy, tightening the UNIQUE thresholds to be unreachable would flip
    # `scored_under_v1`'s zone away from UNIQUE when re-loaded.
    # `FakeZoneAssessmentRepository.save_zone_policy_version` keys by
    # `policy_id` (a dict), so saving v2 under a *different* policy_id leaves
    # v1 in the store too and "load_active_zone_policy_version" must be told
    # which one is ACTIVE -- retire v1 first, exactly as a real governance
    # rollout would (ADR-Governance §3's own "DRAFT | ACTIVE | RETIRED").
    policy_v1_retired = policy_v1.model_copy(update={"status": "RETIRED"})
    await repo.save_zone_policy_version(policy_v1_retired)

    policy_v2 = _build_policy(
        policy_id="zone-policy-v2",
        version=2,
        thresholds={
            "unique_defensibility_min": 999.0,  # unreachable -> nothing can score UNIQUE under v2
            "unique_floor_gate_min": 999.0,
            "commodity_differentiation_max": 0.0,
            "commodity_defensibility_max": 0.0,
        },
    )
    await repo.save_zone_policy_version(policy_v2)

    active_policy = await repo.load_active_zone_policy_version(context.tenant_scope)
    assert active_policy.policy_id == "zone-policy-v2"

    # Re-load the ORIGINAL (v1-scored) assessment. Nothing in this codebase
    # re-scores it against the newly-active v2 policy merely because v2
    # became active -- re-scoring only happens via an explicit
    # `score_zone_assessment` call, which nobody issued for this assessment.
    reloaded = await repo.load_zone_assessment(scored_under_v1.id, context.tenant_scope)

    assert reloaded.recommended_zone == frozen_snapshot["recommended_zone"] == "UNIQUE"
    assert reloaded.differentiation_index == pytest.approx(frozen_snapshot["differentiation_index"])
    assert reloaded.defensibility_index == pytest.approx(frozen_snapshot["defensibility_index"])
    assert reloaded.commodity_score == pytest.approx(frozen_snapshot["commodity_score"])
    assert reloaded.advantage_score == pytest.approx(frozen_snapshot["advantage_score"])
    assert reloaded.unique_score == pytest.approx(frozen_snapshot["unique_score"])
    # Crucially: the historical record still points at the policy version it
    # was actually scored under, NOT the newly-active one.
    assert reloaded.zone_policy_version_id == "zone-policy-v1"
    assert reloaded.zone_policy_version_id != active_policy.policy_id


@pytest.mark.asyncio
async def test_scoring_a_new_assessment_after_policy_switch_uses_new_policy_only(repo):
    """Companion to the above: a *new* assessment scored AFTER v2 becomes
    active does pick up v2 (proving the isolation above is about historical
    immutability, not about the new policy being silently ignored
    altogether)."""
    policy_v1 = _build_policy(policy_id="zone-policy-v1", version=1)
    await repo.save_zone_policy_version(policy_v1)
    policy_v1_retired = policy_v1.model_copy(update={"status": "RETIRED"})
    await repo.save_zone_policy_version(policy_v1_retired)

    policy_v2 = _build_policy(
        policy_id="zone-policy-v2",
        version=2,
        thresholds={
            "unique_defensibility_min": 999.0,
            "unique_floor_gate_min": 999.0,
            "commodity_differentiation_max": 0.0,
            "commodity_defensibility_max": 0.0,
        },
    )
    await repo.save_zone_policy_version(policy_v2)

    context = _reviewer_context()
    pi_repo = _pi_repo_with_concept(concept_id="concept-post-switch-1", tenant_scope=context.tenant_scope)
    draft = await zone_commands.create_zone_assessment(
        repo, pi_repo, context, product_concept_id="concept-post-switch-1", zone_policy_version_id="zone-policy-v2",
    )
    scored_under_v2 = await zone_commands.score_zone_assessment(
        repo, context, assessment_id=draft.id, dimension_assessments=_high_dimension_input(score=90.0),
    )
    # Same dimension_input that produced UNIQUE under v1 now cannot reach
    # UNIQUE under v2's unreachable thresholds.
    assert scored_under_v2.recommended_zone != "UNIQUE"
    assert scored_under_v2.zone_policy_version_id == "zone-policy-v2"


# ---------------------------------------------------------------------------
# 5. Assessment cannot reference cross-tenant ProductConcept — chief
#    architect flagged this as a known, likely-unenforced gap (per Agent
#    B/C's own reports and the `create_zone_assessment` docstring's former
#    "Tenancy judgment call" section, which used to state: "this command
#    does create an assessment record referencing it [a cross-tenant
#    product_concept_id] -- that is a real gap").
#
# This gap has since been closed in the integration stage (Agent G): see
# `application/zone_commands.py::create_zone_assessment`, which now takes a
# second port, `ProductIntelligenceRepositoryPort`, and calls its
# tenant-scoped `load_product_concept(product_concept_id, context.
# tenant_scope)` before creating the assessment. This test has therefore
# been converted from `xfail(strict=True)` ("gap confirmed present") into a
# normal regression test ("gap confirmed closed") — a tenant-a actor
# referencing a product_concept_id that belongs to tenant-b (or does not
# exist at all) must now get `ProductIntelligenceNotFoundError`, not a
# silently-created assessment.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assessment_cannot_reference_cross_tenant_product_concept(repo):
    tenant_a_context = _reviewer_context(tenant_scope="tenant-a")
    await repo.save_zone_policy_version(_build_policy())

    # A product_concept_id that actually belongs to tenant-b (seeded below
    # under tenant-b, not tenant-a) — `create_zone_assessment` must reject
    # this via `product_intelligence_repo.load_product_concept`'s
    # tenant-scoped lookup before any assessment row is created.
    cross_tenant_concept_id = "concept-owned-by-tenant-b"
    pi_repo = _pi_repo_with_concept(concept_id=cross_tenant_concept_id, tenant_scope="tenant-b")

    with pytest.raises(ProductIntelligenceNotFoundError):
        await zone_commands.create_zone_assessment(
            repo,
            pi_repo,
            tenant_a_context,
            product_concept_id=cross_tenant_concept_id,
            zone_policy_version_id="zone-policy-v0",
        )


# ---------------------------------------------------------------------------
# 6. Assessment with no evidence cannot approve — already covered by Agent A
#    (test_zone_scoring.py::test_lifecycle_missing_evidence_blocks_entry_
#    into_under_review, which blocks UNDER_REVIEW, a strict prerequisite of
#    APPROVED) and Agent B (test_zone_review_governance.py::
#    test_missing_evidence_blocks_submit_to_under_review). No new test
#    added; confirmed by inspection. Both existing tests together establish
#    that an assessment can never reach APPROVED without evidence, since
#    APPROVED is only reachable from UNDER_REVIEW.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 7/8/9. AI actor / SYSTEM actor / HUMAN-without-permission cannot approve;
#    authorized HUMAN can approve -- already covered by Agent B
#    (test_zone_review_governance.py::test_ai_actor_with_permission_string_
#    cannot_approve / ::test_system_actor_with_permission_string_cannot_
#    approve / ::test_human_without_zone_review_permission_cannot_approve /
#    ::test_human_with_zone_review_permission_can_approve). Smoke-check only
#    from this file's own local ActorContext fixtures (independent
#    construction path, still exercising the same `approve_zone_assessment`
#    gate) to confirm the gate holds outside Agent B's specific fixtures too.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ai_actor_cannot_approve_smoke(repo):
    under_review = await _under_review_assessment(repo)
    with pytest.raises(ProductIntelligenceForbiddenError):
        await zone_commands.approve_zone_assessment(
            repo, _ai_context(), assessment_id=under_review.id, approved_zone="UNIQUE", review_reason="ai says so",
        )


@pytest.mark.asyncio
async def test_system_actor_cannot_approve_smoke(repo):
    under_review = await _under_review_assessment(repo)
    with pytest.raises(ProductIntelligenceForbiddenError):
        await zone_commands.approve_zone_assessment(
            repo, _system_context(), assessment_id=under_review.id, approved_zone="UNIQUE", review_reason="system job",
        )


@pytest.mark.asyncio
async def test_human_without_zone_review_permission_cannot_approve_smoke(repo):
    under_review = await _under_review_assessment(repo)
    with pytest.raises(ProductIntelligenceForbiddenError):
        await zone_commands.approve_zone_assessment(
            repo, _human_no_permission_context(), assessment_id=under_review.id,
            approved_zone="UNIQUE", review_reason="unauthorized attempt",
        )


@pytest.mark.asyncio
async def test_authorized_human_can_approve_smoke(repo):
    under_review = await _under_review_assessment(repo)
    approved = await zone_commands.approve_zone_assessment(
        repo, _reviewer_context(), assessment_id=under_review.id,
        approved_zone="UNIQUE", review_reason="matches evidence",
    )
    assert approved.status == "APPROVED"
    assert approved.approved_zone == "UNIQUE"


# ---------------------------------------------------------------------------
# 10. Override zone without reason rejected — already covered by Agent A
#    (test_zone_scoring.py::test_approved_zone_diverging_without_override_
#    reason_fails, entity level) and Agent B
#    (test_zone_review_governance.py::test_approve_override_without_reason_
#    is_rejected, application/command level). No new test added; confirmed
#    by inspection — both layers independently enforce this.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 11. Illegal state transition rejected — already covered extensively by
#    Agent A (test_zone_scoring.py::test_lifecycle_draft_to_approved_direct_
#    is_illegal / ::test_lifecycle_rejected_and_retired_are_terminal /
#    ::test_lifecycle_approved_to_retired_allowed_but_not_back_to_approved)
#    and Agent B (test_zone_review_governance.py::
#    test_approve_directly_from_draft_is_illegal / ::
#    test_approve_directly_from_scored_without_submit_is_illegal). This
#    file adds one adversarial angle not explicitly exercised elsewhere:
#    attempting to skip straight from SCORED to REJECTED (bypassing
#    UNDER_REVIEW) via the command layer.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reject_directly_from_scored_without_review_is_illegal(repo):
    scored = await _scored_assessment(repo)
    context = _reviewer_context()
    with pytest.raises(ProductIntelligenceValidationError):
        await zone_commands.reject_zone_assessment(
            repo, context, assessment_id=scored.id, review_reason="skip straight to reject",
        )


@pytest.mark.asyncio
async def test_retire_directly_from_under_review_without_approval_is_illegal(repo):
    under_review = await _under_review_assessment(repo)
    context = _reviewer_context()
    with pytest.raises(ProductIntelligenceValidationError):
        await zone_commands.retire_zone_assessment(
            repo, context, assessment_id=under_review.id, reason="skip approval, retire early",
        )


# ---------------------------------------------------------------------------
# 12. Approved version immutable / new revision required — chief architect
#    flagged this as possibly-untested specifically. NEW test.
#
# `transition_to` is documented to always return a NEW instance via
# `model_copy`, never mutate `self`. This test proves the OLD reference's
# fields are untouched after a transition (including into APPROVED), and
# separately that `approve_zone_assessment` (application layer) likewise
# never mutates the object it loaded from the repo — the repo's *old*
# in-memory dict entry for a prior save is a different Python object
# instance from the one returned by the command (would only matter if the
# repo did in-place mutation, which it does not, but proven here rather than
# assumed).
# ---------------------------------------------------------------------------


def test_transition_to_never_mutates_the_original_instance():
    policy = _build_policy()
    dims = _build_six_dimensions()
    draft = _build_assessment(dims, policy)

    draft_status_before = draft.status
    draft_version_before = draft.version
    draft_updated_at_before = draft.updated_at

    scored = draft.transition_to(new_status="SCORED", actor_id="analyst-1")

    # The OLD reference (`draft`) must be byte-for-byte unchanged.
    assert draft.status == draft_status_before == "DRAFT"
    assert draft.version == draft_version_before
    assert draft.updated_at == draft_updated_at_before
    # The NEW reference is a genuinely different object with bumped fields.
    assert scored is not draft
    assert scored.status == "SCORED"
    assert scored.version == draft.version + 1


@pytest.mark.asyncio
async def test_approved_assessment_old_in_memory_reference_is_not_mutated_by_command(repo):
    under_review = await _under_review_assessment(repo)
    # Keep a reference to the pre-approval object as loaded fresh from the
    # repo, mirroring what a concurrent reader holding an older reference
    # would see.
    pre_approval_reference = await repo.load_zone_assessment(under_review.id, under_review.tenant_scope)
    pre_approval_status = pre_approval_reference.status
    pre_approval_version = pre_approval_reference.version

    approved = await zone_commands.approve_zone_assessment(
        repo, _reviewer_context(), assessment_id=under_review.id,
        approved_zone="UNIQUE", review_reason="matches evidence",
    )

    # The command returned a new object...
    assert approved.status == "APPROVED"
    assert approved.version == pre_approval_version + 1
    # ...and the caller's OLD reference (obtained before the approve call)
    # was never mutated in place.
    assert pre_approval_reference.status == pre_approval_status == "UNDER_REVIEW"
    assert pre_approval_reference.version == pre_approval_version
    assert pre_approval_reference is not approved

    # A fresh re-load from the repo reflects the NEW state -- i.e. "approval
    # requires a new revision to be persisted", not an in-place edit of the
    # UNDER_REVIEW row.
    reloaded = await repo.load_zone_assessment(under_review.id, under_review.tenant_scope)
    assert reloaded.status == "APPROVED"
    assert reloaded.version == pre_approval_version + 1


@pytest.mark.asyncio
async def test_approved_assessment_further_transition_produces_new_revision_not_in_place_edit(repo):
    """Attempting to "modify" an APPROVED assessment (e.g. retiring it) must
    go through `transition_to`'s model_copy path, producing a new version
    number rather than editing the APPROVED row's fields directly."""
    under_review = await _under_review_assessment(repo)
    approved = await zone_commands.approve_zone_assessment(
        repo, _reviewer_context(), assessment_id=under_review.id,
        approved_zone="UNIQUE", review_reason="matches evidence",
    )
    approved_version = approved.version

    retired = await zone_commands.retire_zone_assessment(
        repo, _reviewer_context(), assessment_id=approved.id, reason="superseded",
    )

    assert retired is not approved
    assert retired.version == approved_version + 1
    # The APPROVED object reference itself, held from before retirement,
    # still reports APPROVED -- proving retirement created a new revision
    # rather than editing the approved snapshot in place.
    assert approved.status == "APPROVED"
    assert approved.version == approved_version


# ---------------------------------------------------------------------------
# 13/14/15. Postgres migration / constraints / transaction rollback — out of
#    scope for this file per the task brief ("交给我(集成阶段)跑真实PG"). Not
#    exercised here.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 16. Portfolio query uses approved_zone, not unreviewed recommendation —
#    already covered by Agent D
#    (test_portfolio_zone_view.py::test_summary_counts_only_approved_zone_
#    not_recommended and ::test_summary_rejected_assessment_counts_as_
#    unreviewed, which explicitly assert a SCORED/UNDER_REVIEW/REJECTED
#    assessment with a non-null `recommended_zone` never counts toward the
#    approved-zone summary buckets). Confirmed by inspection; no new test
#    added in this file to avoid duplicating Agent D's own port/query-layer
#    fixtures (this file only imports `zone_commands`/domain entities, not
#    Agent D's query-side fixtures, per file-ownership scope).
# ---------------------------------------------------------------------------
