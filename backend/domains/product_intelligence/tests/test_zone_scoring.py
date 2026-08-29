"""Pure domain-layer tests for the Product Zone scoring engine + entities.

No fake_repo/sqlalchemy fixtures — this is Agent A's domain-only slice
(`zone_value_objects.py` / `zone_entities.py` / `zone_scoring_engine.py`),
per the PR-002 task split. See `architecture/ADR_PRODUCT_ZONE_SCORING_V0.md`
and `architecture/ADR_PRODUCT_ZONE_GOVERNANCE_V0.md` for the frozen contract
being tested against.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ..domain.errors import ProductIntelligenceValidationError
from ..domain.zone_entities import (
    DimensionAssessment,
    ProductZoneAssessment,
    ZonePolicyVersion,
)
from ..domain.zone_scoring_engine import (
    classify_zone,
    compute_defensibility_index,
    compute_differentiation_index,
    inverse_replaceability,
    score_assessment,
)

UTC_NOW = datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc)


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
        classification_rules=(
            "UNIQUE if defensibility_index>=75 and all floor-gate dims>=50; "
            "COMMODITY if differentiation_index<40 and defensibility_index<40; "
            "else ADVANTAGE"
        ),
        review_policy={"unique_requires_reviewers": 1},
        effective_from=UTC_NOW,
        status="ACTIVE",
    )
    defaults.update(overrides)
    return ZonePolicyVersion(**defaults)


def _build_dimension_assessment(dimension: str, score: float, **overrides) -> DimensionAssessment:
    defaults = dict(
        dimension=dimension,
        score=score,
        rationale=f"rationale for {dimension}",
        evidence_refs=[f"evidence:{dimension}:1"],
        evidence_strength=0.7,
        assessed_by="analyst-1",
        assessed_at=UTC_NOW,
    )
    defaults.update(overrides)
    return DimensionAssessment(**defaults)


def _build_six_dimensions(**dimension_scores: float) -> list[DimensionAssessment]:
    defaults = dict(
        customer_scarcity=60.0,
        replaceability=30.0,
        data_advantage=80.0,
        network_effect=80.0,
        learning_effect=80.0,
        switching_cost=80.0,
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
        id="zone-assessment-1",
        created_at=UTC_NOW,
        updated_at=UTC_NOW,
        created_by="analyst-1",
        tenant_scope="tenant-1",
        subject_ref="product-concept-1",
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


# ---------------------------------------------------------------------------
# 1. Normal scoring end-to-end
# ---------------------------------------------------------------------------


def test_high_defensibility_and_floor_gate_yields_unique_zone():
    policy = _build_policy()
    dims = _build_six_dimensions(
        customer_scarcity=90.0,
        replaceability=10.0,
        data_advantage=90.0,
        network_effect=90.0,
        learning_effect=90.0,
        switching_cost=90.0,
    )
    (
        differentiation_index,
        defensibility_index,
        commodity_score,
        advantage_score,
        unique_score,
        recommended_zone,
    ) = score_assessment(dims, policy)

    assert differentiation_index == pytest.approx((90.0 + (100.0 - 10.0)) / 2.0)
    assert defensibility_index == pytest.approx(90.0)
    assert recommended_zone == "UNIQUE"
    assert unique_score == pytest.approx(defensibility_index)


def test_low_indices_yield_commodity_zone():
    policy = _build_policy()
    dims = _build_six_dimensions(
        customer_scarcity=10.0,
        replaceability=90.0,  # inverse_replaceability = 10 -> low differentiation
        data_advantage=10.0,
        network_effect=10.0,
        learning_effect=10.0,
        switching_cost=10.0,
    )
    (differentiation_index, defensibility_index, *_rest, recommended_zone) = score_assessment(dims, policy)

    assert differentiation_index < 40.0
    assert defensibility_index < 40.0
    assert recommended_zone == "COMMODITY"


def test_middling_indices_yield_advantage_zone():
    policy = _build_policy()
    dims = _build_six_dimensions(
        customer_scarcity=55.0,
        replaceability=45.0,
        data_advantage=55.0,
        network_effect=55.0,
        learning_effect=55.0,
        switching_cost=55.0,
    )
    (*_rest, recommended_zone) = score_assessment(dims, policy)
    assert recommended_zone == "ADVANTAGE"


# ---------------------------------------------------------------------------
# 2. replaceability direction semantics
# ---------------------------------------------------------------------------


def test_inverse_replaceability_flips_direction():
    assert inverse_replaceability(100.0) == 0.0
    assert inverse_replaceability(0.0) == 100.0
    assert inverse_replaceability(30.0) == 70.0


_EQUAL_WEIGHTS = {
    "customer_scarcity": 1.0,
    "replaceability": 1.0,
    "data_advantage": 1.0,
    "network_effect": 1.0,
    "learning_effect": 1.0,
    "switching_cost": 1.0,
}


def test_lower_replaceability_yields_higher_differentiation_index():
    high_replaceability_index = compute_differentiation_index(
        customer_scarcity=60.0, replaceability=90.0, weights=_EQUAL_WEIGHTS
    )
    low_replaceability_index = compute_differentiation_index(
        customer_scarcity=60.0, replaceability=10.0, weights=_EQUAL_WEIGHTS
    )

    assert low_replaceability_index > high_replaceability_index


def test_two_assessments_differing_only_in_replaceability_diverge_in_differentiation_index():
    policy = _build_policy()
    low_replaceability_dims = _build_six_dimensions(replaceability=10.0)
    high_replaceability_dims = _build_six_dimensions(replaceability=90.0)

    low_result = score_assessment(low_replaceability_dims, policy)
    high_result = score_assessment(high_replaceability_dims, policy)

    low_differentiation_index = low_result[0]
    high_differentiation_index = high_result[0]

    assert low_differentiation_index != high_differentiation_index
    # Lower replaceability (harder to replace) => higher differentiation.
    assert low_differentiation_index > high_differentiation_index


# ---------------------------------------------------------------------------
# 3. Floor gate
# ---------------------------------------------------------------------------


def test_floor_gate_blocks_unique_even_with_high_average_defensibility():
    policy = _build_policy()
    # Average of the four defensibility dims is still >= 75, but
    # switching_cost collapses to 10 (< floor gate of 50).
    dims = _build_six_dimensions(
        data_advantage=100.0,
        network_effect=100.0,
        learning_effect=100.0,
        switching_cost=10.0,
    )
    defensibility_index = compute_defensibility_index(100.0, 100.0, 100.0, 10.0, weights=_EQUAL_WEIGHTS)
    assert defensibility_index >= 75.0  # average alone would qualify for UNIQUE

    (*_rest, recommended_zone) = score_assessment(dims, policy)
    assert recommended_zone != "UNIQUE"


def test_classify_zone_floor_gate_directly():
    policy = _build_policy()
    dimension_scores = {
        "data_advantage": 100.0,
        "network_effect": 100.0,
        "learning_effect": 100.0,
        "switching_cost": 49.9,  # just under the floor gate
    }
    zone = classify_zone(
        differentiation_index=90.0,
        defensibility_index=87.475,
        dimension_scores=dimension_scores,
        policy=policy,
    )
    assert zone == "ADVANTAGE"


# ---------------------------------------------------------------------------
# 4. Re-computability / determinism
# ---------------------------------------------------------------------------


def test_score_assessment_is_deterministic_across_repeated_calls():
    policy = _build_policy()
    dims = _build_six_dimensions()

    first = score_assessment(dims, policy)
    second = score_assessment(dims, policy)

    assert first == second


def test_zone_policy_version_checksum_is_deterministic():
    policy_a = _build_policy()
    policy_b = _build_policy()
    assert policy_a.checksum == policy_b.checksum

    policy_different = _build_policy(version=2)
    assert policy_different.checksum != policy_a.checksum


# ---------------------------------------------------------------------------
# 5. Score bounds validation
# ---------------------------------------------------------------------------


def test_dimension_assessment_rejects_score_above_100():
    with pytest.raises(ValidationError):
        _build_dimension_assessment("customer_scarcity", 100.1)


def test_dimension_assessment_rejects_score_below_0():
    with pytest.raises(ValidationError):
        _build_dimension_assessment("customer_scarcity", -0.1)


# ---------------------------------------------------------------------------
# 6. Evidence gate
# ---------------------------------------------------------------------------


def test_dimension_assessment_rejects_empty_evidence_refs():
    with pytest.raises(ProductIntelligenceValidationError):
        _build_dimension_assessment("customer_scarcity", 50.0, evidence_refs=[])


def test_product_zone_assessment_rejects_missing_evidence_on_any_dimension():
    policy = _build_policy()
    dims = _build_six_dimensions()
    # Directly construct a bad DimensionAssessment bypassing the helper's
    # default evidence_refs would already fail at DimensionAssessment
    # construction; verify that failure happens before an assessment can be
    # built at all — i.e. the gate is unavoidable, not just "usually applied".
    with pytest.raises(ProductIntelligenceValidationError):
        DimensionAssessment(
            dimension="customer_scarcity",
            score=50.0,
            rationale="no evidence",
            evidence_refs=[],
            assessed_by="analyst-1",
            assessed_at=UTC_NOW,
        )


# ---------------------------------------------------------------------------
# 7. approved_zone / recommended_zone divergence requires override_reason
# ---------------------------------------------------------------------------


def test_approved_zone_diverging_without_override_reason_fails():
    policy = _build_policy()
    dims = _build_six_dimensions(
        customer_scarcity=90.0,
        replaceability=10.0,
        data_advantage=90.0,
        network_effect=90.0,
        learning_effect=90.0,
        switching_cost=90.0,
    )
    with pytest.raises(ProductIntelligenceValidationError):
        _build_assessment(dims, policy, approved_zone="ADVANTAGE")


def test_approved_zone_diverging_with_override_reason_succeeds():
    policy = _build_policy()
    dims = _build_six_dimensions(
        customer_scarcity=90.0,
        replaceability=10.0,
        data_advantage=90.0,
        network_effect=90.0,
        learning_effect=90.0,
        switching_cost=90.0,
    )
    assessment = _build_assessment(
        dims,
        policy,
        approved_zone="ADVANTAGE",
        override_reason="Reviewer judged data_advantage evidence too thin for UNIQUE despite score.",
    )
    assert assessment.approved_zone == "ADVANTAGE"
    assert assessment.recommended_zone == "UNIQUE"


def test_approved_zone_matching_recommended_zone_does_not_require_override_reason():
    policy = _build_policy()
    dims = _build_six_dimensions(
        customer_scarcity=90.0,
        replaceability=10.0,
        data_advantage=90.0,
        network_effect=90.0,
        learning_effect=90.0,
        switching_cost=90.0,
    )
    assessment = _build_assessment(dims, policy, approved_zone="UNIQUE")
    assert assessment.approved_zone == assessment.recommended_zone
    assert assessment.override_reason is None


# ---------------------------------------------------------------------------
# 8. Structural invariants on ProductZoneAssessment
# ---------------------------------------------------------------------------


def test_assessment_requires_exactly_six_dimensions():
    policy = _build_policy()
    dims = _build_six_dimensions()[:5]
    with pytest.raises(ProductIntelligenceValidationError):
        score_assessment(dims, policy)  # missing dims -> engine-level failure first

    # Also verify the entity-level guard independently with a full but
    # duplicated set (6 entries, but a repeated dimension name).
    six_with_duplicate = _build_six_dimensions()[:5] + [_build_dimension_assessment("customer_scarcity", 20.0)]
    full_policy_dims = _build_six_dimensions()
    scored = score_assessment(full_policy_dims, policy)
    with pytest.raises(ProductIntelligenceValidationError):
        _build_assessment(six_with_duplicate, policy, differentiation_index=scored[0], defensibility_index=scored[1],
                           commodity_score=scored[2], advantage_score=scored[3], unique_score=scored[4],
                           recommended_zone=scored[5])


def test_assessment_rejects_subject_type_other_than_product_concept():
    policy = _build_policy()
    dims = _build_six_dimensions()
    with pytest.raises(ProductIntelligenceValidationError):
        _build_assessment(dims, policy, subject_type="PRODUCT_COMPONENT")


# ---------------------------------------------------------------------------
# 9. Lifecycle transitions
# ---------------------------------------------------------------------------


def test_lifecycle_draft_to_approved_direct_is_illegal():
    policy = _build_policy()
    dims = _build_six_dimensions()
    assessment = _build_assessment(dims, policy)
    with pytest.raises(ProductIntelligenceValidationError):
        assessment.transition_to(new_status="APPROVED", actor_id="reviewer-1")


def test_lifecycle_happy_path_draft_to_approved_via_intermediate_states():
    policy = _build_policy()
    dims = _build_six_dimensions()
    assessment = _build_assessment(dims, policy)

    scored = assessment.transition_to(new_status="SCORED", actor_id="analyst-1")
    assert scored.status == "SCORED"
    assert scored.version == assessment.version + 1

    under_review = scored.transition_to(new_status="UNDER_REVIEW", actor_id="analyst-1")
    assert under_review.status == "UNDER_REVIEW"

    approved = under_review.transition_to(new_status="APPROVED", actor_id="reviewer-1", reason="Meets bar.")
    assert approved.status == "APPROVED"
    assert approved.reviewed_by == "reviewer-1"
    assert approved.reviewed_at is not None


def test_lifecycle_rejected_and_retired_are_terminal():
    policy = _build_policy()
    dims = _build_six_dimensions()
    assessment = _build_assessment(dims, policy)
    under_review = assessment.transition_to(new_status="SCORED", actor_id="a").transition_to(
        new_status="UNDER_REVIEW", actor_id="a"
    )
    rejected = under_review.transition_to(new_status="REJECTED", actor_id="reviewer-1", reason="Insufficient evidence.")
    assert rejected.status == "REJECTED"
    with pytest.raises(ProductIntelligenceValidationError):
        rejected.transition_to(new_status="UNDER_REVIEW", actor_id="reviewer-1")


def test_lifecycle_approved_to_retired_allowed_but_not_back_to_approved():
    policy = _build_policy()
    dims = _build_six_dimensions()
    assessment = _build_assessment(dims, policy)
    approved = (
        assessment.transition_to(new_status="SCORED", actor_id="a")
        .transition_to(new_status="UNDER_REVIEW", actor_id="a")
        .transition_to(new_status="APPROVED", actor_id="reviewer-1", reason="ok")
    )
    retired = approved.transition_to(new_status="RETIRED", actor_id="reviewer-1")
    assert retired.status == "RETIRED"
    with pytest.raises(ProductIntelligenceValidationError):
        retired.transition_to(new_status="APPROVED", actor_id="reviewer-1")


def test_lifecycle_missing_evidence_blocks_entry_into_under_review():
    policy = _build_policy()
    dims = _build_six_dimensions()
    assessment = _build_assessment(dims, policy).transition_to(new_status="SCORED", actor_id="a")

    # Simulate a dimension losing its evidence after scoring (e.g. evidence
    # retracted) by rebuilding with an empty evidence_refs bypassively — not
    # possible through DimensionAssessment directly (it's gated), so instead
    # assert the transition-time gate rejects an assessment whose dimension
    # assessments already fail the invariant is unreachable in practice;
    # here we assert the code path exists and is enforced by re-validating
    # via the same guard used by transition_to.
    assert all(d.evidence_refs for d in assessment.dimension_assessments)
    # Directly exercise the guard logic for the "no evidence" branch using a
    # constructed list with a dimension_assessment that has evidence stripped
    # via model_copy after the fact (evidence_refs allows empty list at the
    # model_copy level since validators only run on construction).
    stripped = assessment.model_copy(
        update={
            "dimension_assessments": [
                d.model_copy(update={"evidence_refs": []}) if d.dimension == "customer_scarcity" else d
                for d in assessment.dimension_assessments
            ]
        }
    )
    with pytest.raises(ProductIntelligenceValidationError):
        stripped.transition_to(new_status="UNDER_REVIEW", actor_id="a")


# ---------------------------------------------------------------------------
# 10. Weights: per-group normalized weighted average (closure fix)
# ---------------------------------------------------------------------------


def test_score_assessment_is_deterministic_with_same_policy_including_algorithm_version():
    # Same inputs + same policy (including scoring_algorithm_version) twice
    # must produce byte-identical results — the ADR-Governance §3 "canonical
    # calculation hash" invariant.
    policy = _build_policy(scoring_algorithm_version="ZONE_SCORING_V0")
    dims = _build_six_dimensions()

    first = score_assessment(dims, policy)
    second = score_assessment(dims, policy)

    assert first == second


def test_changing_differentiation_weights_changes_differentiation_index_only():
    # customer_scarcity=90 and inverse_replaceability(30)=70 must differ, or
    # a weight skew between them would leave the weighted average unchanged
    # (degenerate case) and this test would not actually exercise weighting.
    dims = _build_six_dimensions(customer_scarcity=90.0, replaceability=30.0)

    equal_weight_policy = _build_policy(
        weights={
            "customer_scarcity": 1.0,
            "replaceability": 1.0,
            "data_advantage": 1.0,
            "network_effect": 1.0,
            "learning_effect": 1.0,
            "switching_cost": 1.0,
        }
    )
    skewed_weight_policy = _build_policy(
        weights={
            "customer_scarcity": 3.0,
            "replaceability": 1.0,
            "data_advantage": 1.0,
            "network_effect": 1.0,
            "learning_effect": 1.0,
            "switching_cost": 1.0,
        }
    )

    equal_result = score_assessment(dims, equal_weight_policy)
    skewed_result = score_assessment(dims, skewed_weight_policy)

    equal_differentiation_index, equal_defensibility_index = equal_result[0], equal_result[1]
    skewed_differentiation_index, skewed_defensibility_index = skewed_result[0], skewed_result[1]

    assert equal_differentiation_index != skewed_differentiation_index
    # Defensibility group's weights were untouched -> defensibility_index
    # must be unaffected by a purely-differentiation-group weight change
    # (the two groups normalize independently).
    assert equal_defensibility_index == pytest.approx(skewed_defensibility_index)

    expected_skewed = (3.0 * 90.0 + 1.0 * inverse_replaceability(30.0)) / 4.0
    assert skewed_differentiation_index == pytest.approx(expected_skewed)


def test_weights_missing_a_dimension_fails_policy_construction():
    incomplete_weights = {
        "customer_scarcity": 1.0,
        "replaceability": 1.0,
        "data_advantage": 1.0,
        "network_effect": 1.0,
        "learning_effect": 1.0,
        # switching_cost intentionally omitted
    }
    with pytest.raises(ProductIntelligenceValidationError):
        _build_policy(weights=incomplete_weights)


def test_weights_with_negative_value_fails_policy_construction():
    negative_weights = {
        "customer_scarcity": 1.0,
        "replaceability": -1.0,
        "data_advantage": 1.0,
        "network_effect": 1.0,
        "learning_effect": 1.0,
        "switching_cost": 1.0,
    }
    with pytest.raises(ProductIntelligenceValidationError):
        _build_policy(weights=negative_weights)


# ---------------------------------------------------------------------------
# 11. scoring_algorithm_version fail-closed gate
# ---------------------------------------------------------------------------


def test_score_assessment_rejects_unsupported_algorithm_version():
    policy = _build_policy(scoring_algorithm_version="ZONE_SCORING_V99_DOES_NOT_EXIST")
    dims = _build_six_dimensions()
    with pytest.raises(ProductIntelligenceValidationError):
        score_assessment(dims, policy)


# ---------------------------------------------------------------------------
# 12. non_gated_unique_penalty_factor (via thresholds dict)
# ---------------------------------------------------------------------------


def test_non_gated_unique_penalty_factor_default_is_one_half():
    # ADVANTAGE-zone (non-UNIQUE) assessment: unique_score should equal
    # defensibility_index * 0.5 when the policy does not set the key.
    policy = _build_policy()
    dims = _build_six_dimensions(
        customer_scarcity=55.0,
        replaceability=45.0,
        data_advantage=55.0,
        network_effect=55.0,
        learning_effect=55.0,
        switching_cost=55.0,
    )
    (
        _differentiation_index,
        defensibility_index,
        _commodity_score,
        _advantage_score,
        unique_score,
        recommended_zone,
    ) = score_assessment(dims, policy)
    assert recommended_zone != "UNIQUE"
    assert unique_score == pytest.approx(defensibility_index * 0.5)


def test_non_gated_unique_penalty_factor_custom_value_is_applied():
    dims = _build_six_dimensions(
        customer_scarcity=55.0,
        replaceability=45.0,
        data_advantage=55.0,
        network_effect=55.0,
        learning_effect=55.0,
        switching_cost=55.0,
    )
    custom_policy = _build_policy(
        thresholds={
            "unique_defensibility_min": 75.0,
            "unique_floor_gate_min": 50.0,
            "commodity_differentiation_max": 40.0,
            "commodity_defensibility_max": 40.0,
            "non_gated_unique_penalty_factor": 0.25,
        }
    )
    (
        _differentiation_index,
        defensibility_index,
        _commodity_score,
        _advantage_score,
        unique_score,
        recommended_zone,
    ) = score_assessment(dims, custom_policy)

    assert recommended_zone != "UNIQUE"
    assert unique_score == pytest.approx(defensibility_index * 0.25)


# ---------------------------------------------------------------------------
# 13. Checksum sensitivity to the three closure-fix fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "override_kwargs",
    [
        {
            "weights": {
                "customer_scarcity": 2.0,
                "replaceability": 1.0,
                "data_advantage": 1.0,
                "network_effect": 1.0,
                "learning_effect": 1.0,
                "switching_cost": 1.0,
            }
        },
        {
            "thresholds": {
                "unique_defensibility_min": 75.0,
                "unique_floor_gate_min": 50.0,
                "commodity_differentiation_max": 40.0,
                "commodity_defensibility_max": 40.0,
                "non_gated_unique_penalty_factor": 0.9,
            }
        },
        {"scoring_algorithm_version": "ZONE_SCORING_V0_ALT_FOR_TEST"},
    ],
)
def test_checksum_changes_when_weights_thresholds_or_algorithm_version_change(override_kwargs):
    baseline = _build_policy()
    changed = _build_policy(**override_kwargs)
    assert baseline.checksum != changed.checksum
