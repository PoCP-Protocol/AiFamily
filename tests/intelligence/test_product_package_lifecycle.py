from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.human_gate.contracts import (
    ActorType,
    DecisionOutcome,
    HumanDecision,
)
from backend.intelligence.product_management.application.product_package_lifecycle import (
    ProductPackageLifecycleError,
    ProductPackageLifecycleResult,
    advance_product_package_lifecycle,
)
from backend.intelligence.product_management.ipd_contracts import (
    ArtifactStatus,
    GateEvidence,
    ProductPackage,
    ProductZone,
    ReleaseBaseline,
)


def _evidence(kind: str) -> tuple[GateEvidence, ...]:
    return (
        GateEvidence(
            evidence_id=f"evidence:{kind}",
            kind="test",
            reference=f"tests/{kind}",
            summary=f"{kind} verified",
        ),
    )


def _package(*, status: ArtifactStatus = ArtifactStatus.DRAFT) -> ProductPackage:
    return ProductPackage(
        package_id="package:21:v1",
        version="1.0.0",
        charter_id="charter:family-growth:v1",
        concept_id="concept:family-growth:v1",
        requirement_baseline_id="requirements:family-growth:v1",
        target_scenario="家庭节奏恢复",
        duration_days=21,
        zone=ProductZone.ADVANTAGE,
        component_refs=("component:understand:v1", "component:action:v1"),
        skill_refs=("skill:compose:v1",),
        success_metrics=("metric:action-adoption",),
        guardrails=("guardrail:consent",),
        stop_conditions=("stop:safety",),
        delivery_capacity="10 families/week",
        unit_cost_assumption="1000 microUSD/run",
        rollback_rule="restore previous package",
        release_baseline_id="release:package:21:v1" if status is ArtifactStatus.RELEASED else None,
        evidence_refs=("evidence:package:baseline",),
        status=status,
    )


def _release(*, status: ArtifactStatus = ArtifactStatus.RELEASED) -> ReleaseBaseline:
    return ReleaseBaseline(
        release_id="release:package:21:v1",
        package_id="package:21:v1",
        package_version="1.0.0",
        component_refs=("component:understand:v1",),
        skill_refs=("skill:compose:v1",),
        blueprint_version_id="blueprint:package:21:v1",
        model_refs=("model:approved:v1",),
        prompt_refs=("prompt:compose:v1",),
        schema_refs=("schema:package:v1",),
        knowledge_refs=("knowledge:family-growth:v1",),
        migration_refs=("migration:2026-08-31",),
        runbook_ref="runbook:package:21",
        rollback_ref="rollback:package:21:v0",
        environment="staging",
        evidence_refs=("evidence:release:verified",),
        status=status,
        approved_by="human:release" if status is ArtifactStatus.RELEASED else None,
    )


def _decision(
    *,
    outcome: DecisionOutcome = DecisionOutcome.ACCEPT,
    actor_type: ActorType = ActorType.PROFESSIONAL,
    decided_at: datetime | None = None,
) -> HumanDecision:
    return HumanDecision(
        decision_id="decision:package:21:v1",
        task_id="task:package:21:v1",
        actor_id="professional:ipmt",
        actor_type=actor_type,
        outcome=outcome,
        reason=(
            "证据已复核，可进入下一阶段"
            if outcome is DecisionOutcome.ACCEPT
            else "需要补充验证"
        ),
        decided_at=decided_at or datetime(2026, 8, 31, 10, 0, tzinfo=UTC),
    )


def test_accept_maps_to_go_and_advances_one_status_with_audit() -> None:
    now = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
    result = advance_product_package_lifecycle(
        _package(),
        decision=_decision(),
        evidence=_evidence("pilot-gate"),
        target_status=ArtifactStatus.PILOT,
        decision_expires_at=now + timedelta(hours=1),
        now=now,
    )
    assert isinstance(result, ProductPackageLifecycleResult)
    assert result.package.status is ArtifactStatus.PILOT
    assert result.package.gate_history[-1].decision.value == "GO"
    assert result.audit.from_status is ArtifactStatus.DRAFT
    assert result.audit.to_status is ArtifactStatus.PILOT
    assert result.audit.gate_decision.value == "GO"
    assert result.audit.evidence_ids == ("evidence:pilot-gate",)


@pytest.mark.parametrize(
    ("outcome", "code"),
    [
        (DecisionOutcome.REJECT, "ACCEPT_REQUIRED"),
        (DecisionOutcome.ESCALATE, "ACCEPT_REQUIRED"),
    ],
)
def test_reject_or_escalate_fails_closed_before_transition(outcome, code) -> None:
    with pytest.raises(ProductPackageLifecycleError, match=code):
        advance_product_package_lifecycle(
            _package(),
            decision=_decision(outcome=outcome),
            evidence=_evidence("blocked"),
            target_status=ArtifactStatus.PILOT,
        )


def test_expired_or_incomplete_decision_fails_closed() -> None:
    now = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
    with pytest.raises(ProductPackageLifecycleError, match="EXPIRED"):
        advance_product_package_lifecycle(
            _package(),
            decision=_decision(),
            evidence=_evidence("expired"),
            target_status=ArtifactStatus.PILOT,
            decision_expires_at=now - timedelta(seconds=1),
            now=now,
        )
    with pytest.raises(ProductPackageLifecycleError, match="EVIDENCE_REQUIRED"):
        advance_product_package_lifecycle(
            _package(),
            decision=_decision(),
            evidence=(),
            target_status=ArtifactStatus.PILOT,
            now=now,
        )


def test_release_requires_released_matching_baseline() -> None:
    now = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
    qualified = _package(status=ArtifactStatus.QUALIFIED)
    with pytest.raises(ProductPackageLifecycleError, match="RELEASE_BASELINE_REQUIRED"):
        advance_product_package_lifecycle(
            qualified,
            decision=_decision(),
            evidence=_evidence("release"),
            target_status=ArtifactStatus.RELEASED,
            now=now,
        )

    package = replace(
        _package(status=ArtifactStatus.QUALIFIED),
        release_baseline_id="release:package:21:v1",
    )
    with pytest.raises(ProductPackageLifecycleError, match="NOT_RELEASED"):
        advance_product_package_lifecycle(
            package,
            decision=_decision(),
            evidence=_evidence("release"),
            target_status=ArtifactStatus.RELEASED,
            release_baseline=_release(status=ArtifactStatus.DRAFT),
            now=now,
        )


def test_transition_is_sequential_and_non_human_is_rejected() -> None:
    now = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
    with pytest.raises(ProductPackageLifecycleError, match="IPD_STAGE|STATUS_MUST_BE_SEQUENTIAL"):
        advance_product_package_lifecycle(
            _package(),
            decision=_decision(),
            evidence=_evidence("skip"),
            target_status=ArtifactStatus.QUALIFIED,
            now=now,
        )
    # HumanDecision normally rejects AI/SYSTEM at construction.  The adapter
    # still checks the actor type defensively at its own boundary.
    non_human = _decision()
    object.__setattr__(non_human, "actor_type", ActorType.AI)
    with pytest.raises(ProductPackageLifecycleError, match="HUMAN_ACTOR_REQUIRED"):
        advance_product_package_lifecycle(
            _package(),
            decision=non_human,
            evidence=_evidence("non-human"),
            target_status=ArtifactStatus.PILOT,
            now=now,
        )
