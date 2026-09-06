from dataclasses import replace
from datetime import UTC, datetime

import pytest

from backend.domains.service.domain.errors import ServiceValidationError
from backend.domains.service.fgcn.contracts import (
    BlueprintSnapshot,
    ServiceDelivery,
    ServiceTask,
    TaskQualityReview,
    TaskQualityState,
)
from backend.domains.service.fgcn.scenario import (
    S01_FAMILY_PROBLEM,
    S01_OUTCOME_OBSERVATION,
    S01_PROVIDER_DELIVERABLE,
    S01_QUALITY_VERIFICATION_MARKER,
    S01_REWORK_QUALITY_MARKER,
    S01_SCENARIO,
    S01_SERVICE_OUTCOME,
    S01_TASK_ACCEPTANCE_CRITERION,
    S01OutcomeMarkers,
    ServiceScenario,
    parse_s01_outcome_markers,
    render_s01_scenario,
    validate_s01_outcome_observation,
    validate_s01_quality_note,
    validate_s01_rework_note,
)

NOW = datetime(2026, 8, 30, 9, tzinfo=UTC)


def _blueprint(**changes: object) -> BlueprintSnapshot:
    values = {
        "blueprint_ref": "blueprint-s01",
        "version": 1,
        "status": "PUBLISHED",
        "policy_ref": "shadow-policy.v1",
        "policy_version": 1,
        "checksum": "checksum-s01",
        "task_template_keys": ("S01_CALM_START",),
        "scenario": S01_SCENARIO,
    }
    values.update(changes)
    return BlueprintSnapshot(**values)


def test_s01_scenario_freezes_the_real_family_problem_and_result() -> None:
    assert S01_SCENARIO.scenario_key == "S-01"
    assert S01_SCENARIO.family_problem == S01_FAMILY_PROBLEM
    assert S01_SCENARIO.provider_deliverable == S01_PROVIDER_DELIVERABLE
    assert S01_SCENARIO.service_outcome == S01_SERVICE_OUTCOME
    assert "family scores" in S01_SCENARIO.service_outcome
    assert "out of scope" in S01_SCENARIO.service_outcome


@pytest.mark.parametrize(
    "change",
    (
        {
            "scenario": ServiceScenario(
                "S-02",
                S01_FAMILY_PROBLEM,
                S01_PROVIDER_DELIVERABLE,
                S01_SERVICE_OUTCOME,
            )
        },
        {
            "scenario": ServiceScenario(
                "S-01",
                "A generic service request.",
                S01_PROVIDER_DELIVERABLE,
                S01_SERVICE_OUTCOME,
            )
        },
    ),
)
def test_blueprint_rejects_non_s01_or_generic_business_semantics(change) -> None:
    with pytest.raises(ServiceValidationError, match="fgcn_only_s01_scenario_is_supported"):
        _blueprint(**change)


def test_task_requires_s01_outcome_acceptance_not_only_evidence_presence() -> None:
    with pytest.raises(ServiceValidationError, match="fgcn_s01_task_outcome_criterion_required"):
        ServiceTask(
            task_id="task-s01",
            case_id="case-s01",
            blueprint_ref="blueprint-s01",
            blueprint_version=1,
            task_key="S01_CALM_START",
            title="Calm start support",
            description="Deliver one adult-led calm-start intervention.",
            role_key="DELIVERY_RESOURCE",
            acceptance_criteria=("Evidence reference is present",),
            created_at=NOW,
        )


def test_delivery_requires_observed_calm_start_and_rejects_scoring_semantics() -> None:
    common = {
        "delivery_id": "delivery-s01",
        "case_id": "case-s01",
        "task_id": "task-s01",
        "assignee_ref": "provider-s01",
        "evidence_ref": "evidence:s01",
        "delivered_at": NOW,
    }
    with pytest.raises(ServiceValidationError, match="fgcn_s01_delivery_outcome_required"):
        ServiceDelivery(**common, outcome_observation="support was provided")
    with pytest.raises(ServiceValidationError, match="fgcn_s01_scoring_semantics_forbidden"):
        ServiceDelivery(
            **common,
            outcome_observation="S-01 calm start completed; conflict did not escalate; score=1",
        )
    delivery = ServiceDelivery(
        **common,
        outcome_observation=S01_OUTCOME_OBSERVATION,
    )
    assert delivery.outcome_observation == S01_OUTCOME_OBSERVATION


def test_quality_requires_human_s01_outcome_attestation() -> None:
    common = {
        "quality_review_id": "review-s01",
        "case_id": "case-s01",
        "task_id": "task-s01",
        "reviewer_ref": "reviewer-s01",
        "quality_state": TaskQualityState.PASSED,
        "reviewed_at": NOW,
    }
    with pytest.raises(
        ServiceValidationError,
        match="fgcn_s01_quality_outcome_attestation_required",
    ):
        TaskQualityReview(**common, review_note="looks good")
    review = TaskQualityReview(
        **common,
        review_note=S01_QUALITY_VERIFICATION_MARKER,
    )
    assert S01_QUALITY_VERIFICATION_MARKER in review.review_note


def test_quality_rework_requires_localized_reason_and_preserves_score_red_line() -> None:
    common = {
        "quality_review_id": "review-s01-rework",
        "case_id": "case-s01",
        "task_id": "task-s01",
        "reviewer_ref": "reviewer-s01",
        "quality_state": TaskQualityState.REWORK_REQUIRED,
        "reviewed_at": NOW,
    }
    with pytest.raises(ServiceValidationError, match="fgcn_s01_rework_reason_required"):
        TaskQualityReview(**common, review_note="needs another attempt")
    review = TaskQualityReview(**common, review_note=S01_REWORK_QUALITY_MARKER)
    assert review.quality_state is TaskQualityState.REWORK_REQUIRED
    assert validate_s01_rework_note(S01_REWORK_QUALITY_MARKER) == S01_REWORK_QUALITY_MARKER
    with pytest.raises(ServiceValidationError, match="fgcn_s01_scoring_semantics_forbidden"):
        validate_s01_rework_note(f"{S01_REWORK_QUALITY_MARKER} score=1")


def test_s01_acceptance_criterion_is_the_only_task_outcome_boundary() -> None:
    task = ServiceTask(
        task_id="task-s01",
        case_id="case-s01",
        blueprint_ref=_blueprint().blueprint_ref,
        blueprint_version=1,
        task_key="S01_CALM_START",
        title="Calm start support",
        description="Deliver one adult-led calm-start intervention.",
        role_key="DELIVERY_RESOURCE",
        acceptance_criteria=(S01_TASK_ACCEPTANCE_CRITERION,),
        created_at=NOW,
    )
    assert task.acceptance_criteria == (S01_TASK_ACCEPTANCE_CRITERION,)


@pytest.mark.parametrize("locale", ["en", "zh", "fr"])
def test_s01_registered_locales_render_and_parse_structured_outcome(locale: str) -> None:
    scenario = render_s01_scenario(locale)
    assert scenario.scenario_key == "S-01"
    assert scenario.scenario_version == 1
    assert scenario.outcome_key == "CALM_START_CONFLICT_REDUCTION"
    assert scenario.policy_ref == "shadow-policy.v1"
    assert scenario.policy_version == 1
    assert scenario.locale == locale

    observation = {
        "en": "S-01 calm start completed; conflict did not escalate.",
        "zh": "S-01 平稳启动已完成；冲突未升级。",
        "fr": "S-01 démarrage calme terminé ; le conflit ne s'est pas aggravé.",
    }[locale]
    markers = parse_s01_outcome_markers(observation, locale=locale)
    assert markers.calm_start_completed is True
    assert markers.conflict_escalated is False
    assert (
        validate_s01_outcome_observation(observation, locale=locale, markers=markers) == observation
    )


@pytest.mark.parametrize(
    ("locale", "observation"),
    (
        ("zh", "S-01 平稳启动已完成；冲突未升级；总分=1。"),
        ("fr", "S-01 démarrage calme terminé ; le conflit ne s'est pas aggravé ; classement=1."),
    ),
)
def test_s01_forbids_scoring_and_ranking_terms_across_locales(
    locale: str, observation: str
) -> None:
    with pytest.raises(ServiceValidationError, match="fgcn_s01_scoring_semantics_forbidden"):
        parse_s01_outcome_markers(observation, locale=locale)


def test_s01_rejects_unbound_policy_version_locale_and_markers() -> None:
    with pytest.raises(ServiceValidationError, match="fgcn_s01_scenario_metadata_invalid"):
        _blueprint(scenario=replace(S01_SCENARIO, scenario_version=2))
    with pytest.raises(ServiceValidationError, match="fgcn_s01_blueprint_policy_invalid"):
        _blueprint(policy_ref="other-policy.v1")
    with pytest.raises(ServiceValidationError, match="fgcn_s01_locale_unsupported"):
        render_s01_scenario("de")
    with pytest.raises(ServiceValidationError, match="fgcn_s01_outcome_markers_mismatch"):
        validate_s01_outcome_observation(
            "S-01 calm start completed; conflict did not escalate.",
            markers=S01OutcomeMarkers(calm_start_completed=True, conflict_escalated=True),
        )


@pytest.mark.parametrize("locale", ["zh", "fr"])
def test_s01_quality_verification_uses_registered_locale(locale: str) -> None:
    note = {
        "zh": "S-01 结果已验收：平稳启动已完成且冲突未升级。",
        "fr": "Résultat S-01 vérifié : démarrage calme terminé et le conflit ne s'est pas aggravé.",
    }[locale]
    assert validate_s01_quality_note(note, locale=locale) == note
