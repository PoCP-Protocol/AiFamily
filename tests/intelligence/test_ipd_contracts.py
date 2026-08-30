from __future__ import annotations

from dataclasses import replace

import pytest

from backend.intelligence.product_management.ipd_contracts import (
    ArtifactStatus,
    ComponentDefinition,
    GateDecision,
    GateEvidence,
    IPDContractError,
    IPDStage,
    LifecycleRecommendation,
    PilotRun,
    PilotStatus,
    ProductCharter,
    ProductPackage,
    ProductRequirement,
    ProductZone,
    ReleaseBaseline,
    SkillDefinition,
)


def _requirement(
    *,
    requirement_id: str = "IPD-P1-JOURNEY-ACTION-CHECKIN",
    charter_id: str = "charter-p1-v1",
) -> ProductRequirement:
    return ProductRequirement(
        requirement_id=requirement_id,
        charter_id=charter_id,
        capability="JOURNEY",
        feature="ACTION",
        operation="CHECKIN",
        user_story="家庭可以记录一次今日行动并获得下一步反馈",
        acceptance_refs=("tests/intelligence/experience/test_gateway.py",),
        domain_owner="journey",
        data_owner="journey",
        channel_refs=("UI-09",),
        priority=1,
    )


def _charter() -> ProductCharter:
    return ProductCharter(
        charter_id="charter-p1-v1",
        product_id="P1-FAMILY-GROWTH-CORE",
        product_line="Family Growth Core",
        version="1.0.0",
        target_customer="有明确家庭成长需要的家长",
        problem_statement="家庭完成测评后无法持续把理解转成可暂停的小行动",
        value_hypothesis="一条可验证的测评到行动闭环能提升成长采纳和持续反馈",
        owner="product:p1",
        scope_in=("UI-02", "UI-03", "UI-05", "UI-09"),
        scope_out=("real_payment", "family_ranking"),
        success_metrics=("assessment_completion", "action_adoption", "projection_lag"),
        requirements=(_requirement(),),
    )


def _evidence(stage: str) -> tuple[GateEvidence, ...]:
    return (
        GateEvidence(
            evidence_id=f"evidence-{stage}",
            kind="test",
            reference="tests/intelligence/test_ipd_contracts.py",
            summary=f"{stage} contract evidence",
        ),
    )


def test_product_charter_advances_sequentially_with_gate_history() -> None:
    charter = _charter()
    concept = charter.advance(
        IPDStage.CONCEPT,
        decision=GateDecision.GO,
        decided_by="ipmt:p1",
        evidence=_evidence("concept"),
    )
    planned = concept.advance(
        IPDStage.PLAN,
        decision=GateDecision.GO,
        decided_by="pdt:p1",
        evidence=_evidence("plan"),
    )

    assert charter.current_stage is IPDStage.MARKET
    assert planned.current_stage is IPDStage.PLAN
    assert tuple(record.to_stage for record in planned.gate_history) == (
        IPDStage.CONCEPT,
        IPDStage.PLAN,
    )


def test_product_charter_rejects_skipped_or_non_go_gate() -> None:
    charter = _charter()
    with pytest.raises(IPDContractError, match="SEQUENTIAL"):
        charter.advance(
            IPDStage.PLAN,
            decision=GateDecision.GO,
            decided_by="ipmt:p1",
            evidence=_evidence("plan"),
        )
    with pytest.raises(IPDContractError, match="REQUIRES_GO"):
        charter.advance(
            IPDStage.CONCEPT,
            decision=GateDecision.CONDITIONAL,
            decided_by="ipmt:p1",
            evidence=_evidence("concept"),
        )


def test_charter_requires_requirement_alignment_and_acceptance_evidence() -> None:
    with pytest.raises(IPDContractError, match="ACCEPTANCE_REQUIRED"):
        ProductRequirement(
            requirement_id="IPD-P1-JOURNEY-ACTION-CHECKIN",
            charter_id="charter-p1-v1",
            capability="JOURNEY",
            feature="ACTION",
            operation="CHECKIN",
            user_story="家庭可以记录行动",
            acceptance_refs=(),
            domain_owner="journey",
            data_owner="journey",
        )

    with pytest.raises(IPDContractError, match="CHARTER_MISMATCH"):
        replace(
            _charter(),
            requirements=(_requirement(charter_id="charter-other"),),
        )


def _package(
    *,
    status: ArtifactStatus = ArtifactStatus.DRAFT,
    generated_by: str | None = None,
) -> ProductPackage:
    return ProductPackage(
        package_id="package-21-v1",
        version="1.0.0",
        charter_id="charter-p1-v1",
        concept_id="concept-p1-v1",
        requirement_baseline_id="requirements-p1-v1",
        target_scenario="家庭节奏恢复",
        duration_days=21,
        zone=ProductZone.ADVANTAGE,
        component_refs=("component:understand:v1", "component:action:v1"),
        skill_refs=("skill:compose:v1",),
        success_metrics=("action_adoption",),
        guardrails=("consent_required",),
        stop_conditions=("safety_breach",),
        delivery_capacity="10 families/week",
        unit_cost_assumption="1000 microUSD/run",
        rollback_rule="pause and restore prior package version",
        release_baseline_id="release-p1-v1" if status is ArtifactStatus.RELEASED else None,
        evidence_refs=("evidence:package-1",),
        status=status,
        generated_by=generated_by,
    )


def _gate_evidence(kind: str = "test") -> tuple[GateEvidence, ...]:
    return (
        GateEvidence(
            evidence_id=f"evidence:{kind}",
            kind="test",
            reference="tests/intelligence/test_ipd_contracts.py",
            summary=f"{kind} evidence",
        ),
    )


def test_pdm_components_and_skills_are_immutable_and_ai_stays_draft() -> None:
    component = ComponentDefinition(
        component_id="component:action",
        version="1.0.0",
        owner="pdt:family-growth",
        purpose="today action",
        target_scenario="家庭节奏恢复",
        zone=ProductZone.ADVANTAGE,
        inputs=("context",),
        outputs=("action_proposal",),
        evidence_refs=("evidence:component",),
        rollback_rule="restore previous version",
        status=ArtifactStatus.DRAFT,
        generated_by="ai:product-factory",
    )
    assert component.status is ArtifactStatus.DRAFT
    with pytest.raises((AttributeError, IPDContractError)):
        component.version = "2.0.0"  # type: ignore[misc]

    with pytest.raises(IPDContractError, match="AI_ARTIFACT_MUST_REMAIN_DRAFT"):
        ComponentDefinition(
            component_id="component:published",
            version="1.0.0",
            owner="pdt:family-growth",
            purpose="today action",
            target_scenario="家庭节奏恢复",
            zone=ProductZone.ADVANTAGE,
            evidence_refs=("evidence:component",),
            rollback_rule="restore previous version",
            status=ArtifactStatus.RELEASED,
            generated_by="ai:product-factory",
        )

    SkillDefinition(
        skill_id="skill:compose",
        version="1.0.0",
        owner="ai-runtime",
        purpose="compose a product draft",
        input_schema="product-input.v1",
        output_schema="product-draft.v1",
        quality_eval_refs=("eval:compose-v1",),
        safety_policy="minor-safe",
        human_handoff="ipmt-review",
        evidence_refs=("evidence:skill",),
    )


def test_product_package_gate_is_sequential_and_requires_human_evidence() -> None:
    package = _package()
    with pytest.raises(IPDContractError, match="SEQUENTIAL"):
        package.advance(
            ArtifactStatus.QUALIFIED,
            decision=GateDecision.GO,
            decided_by="human:ipmt",
            evidence=_gate_evidence("skip"),
        )
    with pytest.raises(IPDContractError, match="REQUIRES_GO"):
        package.advance(
            ArtifactStatus.PILOT,
            decision=GateDecision.CONDITIONAL,
            decided_by="human:ipmt",
            evidence=_gate_evidence("conditional"),
        )
    pilot = package.advance(
        ArtifactStatus.PILOT,
        decision=GateDecision.GO,
        decided_by="human:ipmt",
        evidence=_gate_evidence("pilot"),
    )
    qualified = pilot.advance(
        ArtifactStatus.QUALIFIED,
        decision=GateDecision.GO,
        decided_by="human:quality",
        evidence=_gate_evidence("qualified"),
    )
    assert (pilot.gate_history[-1].from_stage, pilot.gate_history[-1].to_stage) == (
        IPDStage.PLAN,
        IPDStage.DEVELOP,
    )
    assert (qualified.gate_history[-1].from_stage, qualified.gate_history[-1].to_stage) == (
        IPDStage.DEVELOP,
        IPDStage.QUALIFY,
    )
    with pytest.raises(IPDContractError, match="RELEASE_BASELINE_REQUIRED"):
        qualified.advance(
            ArtifactStatus.RELEASED,
            decision=GateDecision.GO,
            decided_by="human:release",
            evidence=_gate_evidence("release"),
        )


def test_pilot_requires_completed_evidence_for_scale_revise_kill() -> None:
    pilot = PilotRun(
        pilot_id="pilot-21-v1",
        package_id="package-21-v1",
        package_version="1.0.0",
        cohort_ref="cohort:synthetic",
        max_participants=10,
        metrics=("action_adoption",),
        guardrails=("consent_required",),
        stop_conditions=("safety_breach",),
        rollback_rule="restore package-21-v0",
        evidence_refs=("evidence:pilot-plan",),
    )
    started = pilot.start(decided_by="human:pilot-owner", evidence=_gate_evidence("start"))
    completed = started.complete(evidence=_gate_evidence("complete"))
    decided = completed.decide(
        LifecycleRecommendation.REVISE,
        decided_by="human:ipmt",
        evidence=_gate_evidence("revise"),
    )
    assert decided.status is PilotStatus.COMPLETED
    assert decided.lifecycle_recommendation is LifecycleRecommendation.REVISE
    killed = completed.decide(
        LifecycleRecommendation.KILL,
        decided_by="human:ipmt",
        evidence=_gate_evidence("kill"),
    )
    assert killed.status is PilotStatus.KILLED


def _release(
    *,
    status: ArtifactStatus = ArtifactStatus.DRAFT,
    generated_by: str | None = None,
) -> ReleaseBaseline:
    return ReleaseBaseline(
        release_id="release-p1-v1",
        package_id="package-21-v1",
        package_version="1.0.0",
        component_refs=("component:action:v1",),
        skill_refs=("skill:compose:v1",),
        blueprint_version_id="blueprint:p1:v1",
        model_refs=("model:approved:v1",),
        prompt_refs=("prompt:compose:v1",),
        schema_refs=("schema:product-package:v1",),
        knowledge_refs=("knowledge:family-growth:v1",),
        migration_refs=("migration:2026-08-30",),
        runbook_ref="runbook:release-p1",
        rollback_ref="rollback:release-p1-v0",
        environment="staging",
        evidence_refs=("evidence:release",),
        status=status,
        generated_by=generated_by,
        approved_by=(
            "human:release"
            if status in {ArtifactStatus.RELEASED, ArtifactStatus.PAUSED, ArtifactStatus.RETIRED}
            else None
        ),
    )


def test_release_baseline_requires_human_approval_and_supports_rollback_retire() -> None:
    draft = _release()
    with pytest.raises(IPDContractError, match="RELEASE_APPROVAL_EVIDENCE_REQUIRED"):
        draft.approve(decided_by="human:release", human_gate_ref="", evidence=())
    reviewed = draft.approve(
        decided_by="human:release",
        human_gate_ref="gate:release",
        evidence=_gate_evidence("approval"),
    )
    released = reviewed.release(decided_by="human:release", evidence=_gate_evidence("release"))
    paused = released.pause(decided_by="human:ops", evidence=_gate_evidence("pause"))
    rolled_back = paused.rollback(
        target_ref="release-p1-v0",
        decided_by="human:ops",
        evidence=_gate_evidence("rollback"),
    )
    retired = rolled_back.retire(decided_by="human:ipmt", evidence=_gate_evidence("retire"))
    assert retired.status is ArtifactStatus.RETIRED
    assert retired.rollback_target_ref == "release-p1-v0"
