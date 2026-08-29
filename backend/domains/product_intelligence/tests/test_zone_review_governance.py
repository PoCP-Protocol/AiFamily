"""Application-layer tests for `application/zone_commands.py` — the Product
Zone (Three-Zone Strategy Engine) governance commands. Pure application-layer
slice: an in-memory Fake implementing `application/zone_ports.py::
ZoneAssessmentRepositoryPort`, no SQLAlchemy/DB fixtures (per this Agent's
file-ownership scope — `infrastructure/fake_repository.py` is Agent C's file
and is not touched here).

Covers ADR-Governance §4/§5 core scenarios: the `ZONE_REVIEW_PERMISSION`
hard gate on approve/reject/retire, the HUMAN-only gate on submit, illegal
status jumps, the evidence-gate (delegated to `transition_to` but exercised
here through the command layer), and the override-reason requirement.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ..application import zone_commands
from ..application.context import ActorContext
from ..domain.entities import ProductConcept
from ..domain.errors import (
    ProductIntelligenceForbiddenError,
    ProductIntelligenceNotFoundError,
    ProductIntelligenceValidationError,
)
from ..domain.zone_entities import ProductZoneAssessment, ZonePolicyVersion
from ..infrastructure.fake_repository import FakeProductIntelligenceRepository

UTC_NOW = datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc)

ZONE_REVIEW_PERMISSION = zone_commands.ZONE_REVIEW_PERMISSION


class FakeZoneAssessmentRepository:
    """Minimal in-memory Fake implementing `ZoneAssessmentRepositoryPort`
    for this test file only. Does not implement/replace
    `infrastructure/fake_repository.py` (Agent C's file)."""

    def __init__(self) -> None:
        self.assessments: dict[str, ProductZoneAssessment] = {}
        self.policy_versions: dict[str, ZonePolicyVersion] = {}

    async def save_zone_assessment(self, entity: ProductZoneAssessment) -> None:
        self.assessments[entity.id] = entity

    async def load_zone_assessment(self, entity_id: str, tenant_scope: str) -> ProductZoneAssessment:
        entity = self.assessments.get(entity_id)
        if entity is None or entity.tenant_scope != tenant_scope:
            raise ProductIntelligenceNotFoundError("zone_assessment_not_found")
        return entity

    async def load_active_zone_policy_version(self, tenant_scope: str | None = None) -> ZonePolicyVersion:
        for policy in self.policy_versions.values():
            if policy.status == "ACTIVE":
                return policy
        raise ProductIntelligenceNotFoundError("zone_policy_version_not_found")

    async def save_zone_policy_version(self, entity: ZonePolicyVersion) -> None:
        self.policy_versions[entity.policy_id] = entity


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
    concept_id: str = "concept-1", tenant_scope: str = "tenant-a",
) -> FakeProductIntelligenceRepository:
    """Seeds a minimal real `ProductConcept` directly (bypassing the full
    Signal->...->ProductConcept chain, since these zone-engine tests only
    need `load_product_concept` to succeed for the given id/tenant, not a
    real chain history) — integration fix, see `zone_commands.py`'s
    `create_zone_assessment` docstring item 2 (cross-tenant
    `product_concept_id` gap closed via `ProductIntelligenceRepositoryPort.
    load_product_concept`).
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
    """All six dimensions high -> should classify UNIQUE against the
    default fixture policy (defensibility 90 >= 75, floor 90 >= 50)."""
    return [
        {
            "dimension": dimension,
            "score": score,
            "rationale": "strong signal",
            "evidence_refs": [f"evidence-{dimension}"],
            "evidence_strength": 0.8,
            "assessed_by": "human-scorer-1",
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


def _low_dimension_input() -> list[dict]:
    """COMMODITY: low `customer_scarcity`, HIGH `replaceability` (so
    `inverse_replaceability` is also low -> differentiation_index low), and
    low defensibility dimensions -> both indices land under the 40
    thresholds of the fixture policy.
    """
    scores = {
        "customer_scarcity": 10.0,
        "replaceability": 90.0,  # inverts to 10 -> keeps differentiation low
        "data_advantage": 10.0,
        "network_effect": 10.0,
        "learning_effect": 10.0,
        "switching_cost": 10.0,
    }
    return [
        {
            "dimension": dimension,
            "score": score,
            "rationale": "weak signal",
            "evidence_refs": [f"evidence-{dimension}"],
            "evidence_strength": 0.5,
            "assessed_by": "human-scorer-1",
            "assessed_at": UTC_NOW,
        }
        for dimension, score in scores.items()
    ]


def _reviewer_context(permissions: frozenset[str] = frozenset({ZONE_REVIEW_PERMISSION})) -> ActorContext:
    return ActorContext(actor_id="human-reviewer-1", actor_type="HUMAN", tenant_scope="tenant-a", permissions=permissions)


def _human_no_permission_context() -> ActorContext:
    return ActorContext(actor_id="human-no-perm", actor_type="HUMAN", tenant_scope="tenant-a", permissions=frozenset())


def _ai_context_with_permission_string() -> ActorContext:
    # AI actor that somehow carries the permission string — must still be
    # forbidden, per ADR-Governance §4 ("AI and SYSTEM actors are forbidden
    # from approving regardless of any permission string they might carry").
    return ActorContext(actor_id="ai-agent-1", actor_type="AI", tenant_scope="tenant-a", permissions=frozenset({ZONE_REVIEW_PERMISSION}))


def _system_context_with_permission_string() -> ActorContext:
    return ActorContext(actor_id="system-job-1", actor_type="SYSTEM", tenant_scope="tenant-a", permissions=frozenset({ZONE_REVIEW_PERMISSION}))


@pytest.fixture
def repo():
    return FakeZoneAssessmentRepository()


async def _scored_assessment(repo, *, dimension_input=None, creator_context=None):
    await repo.save_zone_policy_version(_build_policy())
    creator_context = creator_context or _reviewer_context()
    pi_repo = _pi_repo_with_concept(concept_id="concept-1", tenant_scope=creator_context.tenant_scope)
    draft = await zone_commands.create_zone_assessment(
        repo, pi_repo, creator_context, product_concept_id="concept-1", zone_policy_version_id="zone-policy-v0",
    )
    scored = await zone_commands.score_zone_assessment(
        repo, creator_context, assessment_id=draft.id, dimension_assessments=dimension_input or _high_dimension_input(),
    )
    return scored


async def _under_review_assessment(repo, **kwargs):
    scored = await _scored_assessment(repo, **kwargs)
    return await zone_commands.submit_zone_review(repo, _reviewer_context(), assessment_id=scored.id)


# --- create/score -----------------------------------------------------------


@pytest.mark.asyncio
async def test_create_zone_assessment_is_draft_with_empty_dimensions(repo):
    await repo.save_zone_policy_version(_build_policy())
    context = _reviewer_context()
    pi_repo = _pi_repo_with_concept(concept_id="concept-1", tenant_scope=context.tenant_scope)
    draft = await zone_commands.create_zone_assessment(
        repo, pi_repo, context, product_concept_id="concept-1", zone_policy_version_id="zone-policy-v0",
    )
    assert draft.status == "DRAFT"
    # Integration fix: DRAFT now allows an empty dimension_assessments list
    # (see zone_entities.py's updated validator) instead of six placeholder
    # rows.
    assert len(draft.dimension_assessments) == 0
    assert draft.tenant_scope == "tenant-a"


@pytest.mark.asyncio
async def test_score_zone_assessment_moves_draft_to_scored_with_real_dimensions(repo):
    scored = await _scored_assessment(repo)
    assert scored.status == "SCORED"
    assert scored.recommended_zone == "UNIQUE"
    assert all(d.rationale != "pending_initial_assessment" for d in scored.dimension_assessments)


@pytest.mark.asyncio
async def test_score_zone_assessment_commodity_classification(repo):
    scored = await _scored_assessment(repo, dimension_input=_low_dimension_input())
    assert scored.recommended_zone == "COMMODITY"


# --- submit ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_zone_review_any_human_without_special_permission(repo):
    scored = await _scored_assessment(repo)
    submitter = _human_no_permission_context()
    submitted = await zone_commands.submit_zone_review(repo, submitter, assessment_id=scored.id)
    assert submitted.status == "UNDER_REVIEW"


@pytest.mark.asyncio
async def test_submit_zone_review_forbidden_for_ai_actor(repo):
    scored = await _scored_assessment(repo)
    ai_context = ActorContext(actor_id="ai-agent-1", actor_type="AI", tenant_scope="tenant-a")
    with pytest.raises(ProductIntelligenceForbiddenError):
        await zone_commands.submit_zone_review(repo, ai_context, assessment_id=scored.id)


@pytest.mark.asyncio
async def test_submit_zone_review_forbidden_for_system_actor(repo):
    scored = await _scored_assessment(repo)
    system_context = ActorContext(actor_id="system-job-1", actor_type="SYSTEM", tenant_scope="tenant-a")
    with pytest.raises(ProductIntelligenceForbiddenError):
        await zone_commands.submit_zone_review(repo, system_context, assessment_id=scored.id)


# --- approve permission gate --------------------------------------------------


@pytest.mark.asyncio
async def test_human_without_zone_review_permission_cannot_approve(repo):
    under_review = await _under_review_assessment(repo)
    context = _human_no_permission_context()
    with pytest.raises(ProductIntelligenceForbiddenError):
        await zone_commands.approve_zone_assessment(
            repo, context, assessment_id=under_review.id, approved_zone="UNIQUE", review_reason="looks good",
        )


@pytest.mark.asyncio
async def test_ai_actor_with_permission_string_cannot_approve(repo):
    under_review = await _under_review_assessment(repo)
    context = _ai_context_with_permission_string()
    with pytest.raises(ProductIntelligenceForbiddenError):
        await zone_commands.approve_zone_assessment(
            repo, context, assessment_id=under_review.id, approved_zone="UNIQUE", review_reason="looks good",
        )


@pytest.mark.asyncio
async def test_system_actor_with_permission_string_cannot_approve(repo):
    under_review = await _under_review_assessment(repo)
    context = _system_context_with_permission_string()
    with pytest.raises(ProductIntelligenceForbiddenError):
        await zone_commands.approve_zone_assessment(
            repo, context, assessment_id=under_review.id, approved_zone="UNIQUE", review_reason="looks good",
        )


@pytest.mark.asyncio
async def test_human_with_zone_review_permission_can_approve(repo):
    under_review = await _under_review_assessment(repo)
    context = _reviewer_context()
    approved = await zone_commands.approve_zone_assessment(
        repo, context, assessment_id=under_review.id, approved_zone="UNIQUE", review_reason="matches evidence",
    )
    assert approved.status == "APPROVED"
    assert approved.approved_zone == "UNIQUE"
    assert approved.reviewed_by == context.actor_id


@pytest.mark.asyncio
async def test_approve_override_without_reason_is_rejected(repo):
    under_review = await _under_review_assessment(repo)  # recommended_zone == UNIQUE
    context = _reviewer_context()
    with pytest.raises(ProductIntelligenceValidationError):
        await zone_commands.approve_zone_assessment(
            repo, context, assessment_id=under_review.id, approved_zone="COMMODITY", review_reason="disagree", override_reason=None,
        )


@pytest.mark.asyncio
async def test_approve_override_with_reason_succeeds(repo):
    under_review = await _under_review_assessment(repo)  # recommended_zone == UNIQUE
    context = _reviewer_context()
    approved = await zone_commands.approve_zone_assessment(
        repo, context, assessment_id=under_review.id, approved_zone="COMMODITY",
        review_reason="disagree with model", override_reason="commercial context outweighs the dimension scores",
    )
    assert approved.approved_zone == "COMMODITY"
    assert approved.override_reason is not None


# --- illegal transitions -------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_directly_from_draft_is_illegal(repo):
    await repo.save_zone_policy_version(_build_policy())
    context = _reviewer_context()
    pi_repo = _pi_repo_with_concept(concept_id="concept-1", tenant_scope=context.tenant_scope)
    draft = await zone_commands.create_zone_assessment(
        repo, pi_repo, context, product_concept_id="concept-1", zone_policy_version_id="zone-policy-v0",
    )
    with pytest.raises(ProductIntelligenceValidationError):
        await zone_commands.approve_zone_assessment(
            repo, context, assessment_id=draft.id, approved_zone="COMMODITY", review_reason="skip ahead",
        )


@pytest.mark.asyncio
async def test_approve_directly_from_scored_without_submit_is_illegal(repo):
    scored = await _scored_assessment(repo)
    context = _reviewer_context()
    with pytest.raises(ProductIntelligenceValidationError):
        await zone_commands.approve_zone_assessment(
            repo, context, assessment_id=scored.id, approved_zone=scored.recommended_zone, review_reason="skip review",
        )


# --- evidence gate --------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_evidence_blocks_submit_to_under_review(repo):
    await repo.save_zone_policy_version(_build_policy())
    context = _reviewer_context()
    pi_repo = _pi_repo_with_concept(concept_id="concept-1", tenant_scope=context.tenant_scope)
    draft = await zone_commands.create_zone_assessment(
        repo, pi_repo, context, product_concept_id="concept-1", zone_policy_version_id="zone-policy-v0",
    )
    bad_input = _high_dimension_input()
    bad_input[0]["evidence_refs"] = []
    with pytest.raises(ProductIntelligenceValidationError):
        # DimensionAssessment's own field_validator rejects empty
        # evidence_refs before transition_to's evidence gate is even
        # reached — either way, "no evidence" must fail at this step.
        await zone_commands.score_zone_assessment(
            repo, context, assessment_id=draft.id, dimension_assessments=bad_input,
        )


# --- reject / retire ------------------------------------------------------------


@pytest.mark.asyncio
async def test_reject_requires_zone_review_permission(repo):
    under_review = await _under_review_assessment(repo)
    context = _human_no_permission_context()
    with pytest.raises(ProductIntelligenceForbiddenError):
        await zone_commands.reject_zone_assessment(repo, context, assessment_id=under_review.id, review_reason="insufficient evidence")


@pytest.mark.asyncio
async def test_reject_with_permission_succeeds(repo):
    under_review = await _under_review_assessment(repo)
    context = _reviewer_context()
    rejected = await zone_commands.reject_zone_assessment(repo, context, assessment_id=under_review.id, review_reason="insufficient evidence")
    assert rejected.status == "REJECTED"


@pytest.mark.asyncio
async def test_retire_requires_zone_review_permission(repo):
    under_review = await _under_review_assessment(repo)
    approved = await zone_commands.approve_zone_assessment(
        repo, _reviewer_context(), assessment_id=under_review.id, approved_zone="UNIQUE", review_reason="ok",
    )
    context = _human_no_permission_context()
    with pytest.raises(ProductIntelligenceForbiddenError):
        await zone_commands.retire_zone_assessment(repo, context, assessment_id=approved.id, reason="superseded")


@pytest.mark.asyncio
async def test_retire_with_permission_succeeds(repo):
    under_review = await _under_review_assessment(repo)
    approved = await zone_commands.approve_zone_assessment(
        repo, _reviewer_context(), assessment_id=under_review.id, approved_zone="UNIQUE", review_reason="ok",
    )
    retired = await zone_commands.retire_zone_assessment(repo, _reviewer_context(), assessment_id=approved.id, reason="superseded by new policy")
    assert retired.status == "RETIRED"


# --- tenant isolation ------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_zone_assessment_cross_tenant_raises_not_found(repo):
    scored = await _scored_assessment(repo)
    other_tenant_context = ActorContext(
        actor_id="human-other-tenant", actor_type="HUMAN", tenant_scope="tenant-b", permissions=frozenset({ZONE_REVIEW_PERMISSION}),
    )
    with pytest.raises(ProductIntelligenceNotFoundError):
        await zone_commands.submit_zone_review(repo, other_tenant_context, assessment_id=scored.id)
