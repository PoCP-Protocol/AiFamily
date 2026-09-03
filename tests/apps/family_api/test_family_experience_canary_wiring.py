from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from backend.apps.family_api.family_experience_canary_wiring import (
    build_http_family_experience_canary_runtime,
)
from backend.intelligence.evaluation.deployment import (
    DeploymentOperation,
    DeploymentPhase,
    DeploymentReceipt,
    DeploymentResult,
    InMemoryDeploymentReceiptStore,
)
from backend.intelligence.evaluation.release_catalog import (
    ReleaseCandidate,
    ReleaseCandidateStatus,
)
from backend.intelligence.evaluation.release_control import ReleaseControlEvent
from backend.intelligence.experience.canary_supervision import (
    CanaryHealth,
    CanarySloPolicy,
    CanarySupervisionError,
    InMemoryCanaryAssessmentStore,
    InMemoryRollbackControlReader,
)
from backend.intelligence.experience.release_bundle import FamilyExperienceReleaseBundle
from backend.intelligence.experience.release_bundle_deployment import (
    FamilyExperienceReleaseDeploymentService,
)
from backend.intelligence.experience.release_bundle_persistence import (
    InMemoryFamilyExperienceReleaseBundleStore,
)

NOW = datetime(2026, 8, 31, 13, 0, tzinfo=UTC)


class _DeploymentPort:
    def __init__(self) -> None:
        self.rollback_calls = 0

    async def apply(
        self, bundle, candidate, control, *, phase, rollout_percent, idempotency_key
    ):
        return DeploymentResult(external_ref="unused")

    async def rollback(self, bundle, candidate, control, *, idempotency_key):
        self.rollback_calls += 1
        return DeploymentResult(external_ref=f"rollback:{candidate.environment}")


def _artifacts(environment: str):
    candidate = ReleaseCandidate(
        candidate_id="family-experience:candidate-a",
        environment=environment,
        decision_id="d" * 64,
        provider_id="provider-a",
        model="multimodal-a",
        model_version="2026-08",
        report_ref="benchmark:a",
        status=ReleaseCandidateStatus.APPROVED,
        last_control_id="approval-control",
        rollback_target_candidate_id=None,
        registered_at=NOW,
        updated_at=NOW,
    )
    bundle = FamilyExperienceReleaseBundle(
        bundle_id="b" * 64,
        candidate_id=candidate.candidate_id,
        environment=environment,
        use_case="family_assistant_conversation",
        agent_id="parent_advisor",
        provider_id=candidate.provider_id,
        model=candidate.model,
        model_version=candidate.model_version,
        prompt_ref="family_assistant_v1",
        prompt_version="family-companion.v1",
        schema_ref="assistant_response_v1",
        schema_version="family-experience-draft.v1",
        safety_policy_version="minor-safety.v1",
        routing_policy_version="multimodal-routing.v1",
        rate_card_version="family-rate-card.v1",
        budget_policy_version="family-budget.v1",
        knowledge_refs=("knowledge:family-companion:v1",),
        data_class="MINOR_PERSONAL_DATA",
        report_ref=candidate.report_ref,
        decision_id=candidate.decision_id,
        control_id="approval-control",
        approval_signature_ref="approval-signature",
        approval_signature_algorithm="external-kms-v1",
        approved_by="operator-1",
        approved_at=NOW,
        asset_digest="a" * 64,
        human_gate_rule="REVIEW_REQUIRED",
    )
    receipt = DeploymentReceipt(
        receipt_id="canary-receipt",
        operation=DeploymentOperation.APPLY,
        phase=DeploymentPhase.CANARY,
        idempotency_key=f"deploy:{environment}",
        candidate_id=candidate.candidate_id,
        environment=environment,
        control_id="approval-control",
        actor_id="operator-1",
        rollout_percent=5,
        external_ref=f"external:{environment}",
        created_at=NOW,
    )
    control = ReleaseControlEvent(
        control_id="rollback-control",
        kind="ROLLBACK",
        idempotency_key=f"rollback:{environment}",
        decision_id=candidate.decision_id,
        candidate_id=candidate.candidate_id,
        environment=environment,
        actor_id="operator-1",
        target_candidate_id="family-experience:previous",
        reason="pre-authorized SLO rollback",
        signature_ref="rollback-signature",
        signature_algorithm="external-kms-v1",
        created_at=NOW + timedelta(minutes=1),
    )
    return candidate, bundle, receipt, control


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", ["development", "test", "staging", "production"])
async def test_canary_runtime_executes_same_safety_rollback_path_in_every_environment(
    environment: str,
) -> None:
    candidate, bundle, receipt, control = _artifacts(environment)
    bundles = InMemoryFamilyExperienceReleaseBundleStore()
    await bundles.append(bundle)
    deployment_port = _DeploymentPort()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "observation_id": f"observation:{environment}",
                "receipt_id": receipt.receipt_id,
                "candidate_id": candidate.candidate_id,
                "environment": environment,
                "observed_at": (NOW + timedelta(minutes=5)).isoformat(),
                "window_seconds": 300,
                "request_count": 1,
                "error_rate": 0.0,
                "p95_latency_ms": 500,
                "safety_violation_count": 0,
                "minor_safety_violation_count": 1,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        runtime = build_http_family_experience_canary_runtime(
            environment=environment,
            observation_base_url="https://observation.example",
            token_provider=lambda: "system-scoped-token",
            rollback_controls=InMemoryRollbackControlReader((control,)),
            deployment=FamilyExperienceReleaseDeploymentService(
                port=deployment_port,
                bundles=bundles,
                receipts=InMemoryDeploymentReceiptStore(),
                clock=lambda: NOW + timedelta(minutes=5),
            ),
            assessments=InMemoryCanaryAssessmentStore(),
            policy=CanarySloPolicy(
                version="family-experience-canary.v1",
                min_request_count=100,
                max_error_rate=0.02,
                max_p95_latency_ms=1200,
                rollback_authorization_ttl_seconds=3600,
            ),
            observation_client=client,
            clock=lambda: NOW + timedelta(minutes=5),
        )
        result = await runtime.supervise(
            candidate,
            receipt,
            rollback_control_id=control.control_id,
            idempotency_key=f"supervise:{environment}",
        )

    assert result.assessment.health is CanaryHealth.BREACHED
    assert result.assessment.reasons == ("minor_safety_violation",)
    assert result.rollback_receipt is not None
    assert result.rollback_receipt.actor_id == "operator-1"
    assert deployment_port.rollback_calls == 1


@pytest.mark.asyncio
async def test_canary_runtime_rejects_cross_environment_before_observation() -> None:
    candidate, bundle, receipt, control = _artifacts("test")
    bundles = InMemoryFamilyExperienceReleaseBundleStore()
    await bundles.append(bundle)
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        runtime = build_http_family_experience_canary_runtime(
            environment="production",
            observation_base_url="https://observation.example",
            token_provider=lambda: "token",
            rollback_controls=InMemoryRollbackControlReader((control,)),
            deployment=FamilyExperienceReleaseDeploymentService(
                port=_DeploymentPort(),
                bundles=bundles,
                receipts=InMemoryDeploymentReceiptStore(),
            ),
            assessments=InMemoryCanaryAssessmentStore(),
            policy=CanarySloPolicy("v1", 100, 0.02, 1200, 3600),
            observation_client=client,
        )
        with pytest.raises(CanarySupervisionError, match="ENVIRONMENT_MISMATCH"):
            await runtime.supervise(
                candidate,
                receipt,
                rollback_control_id=control.control_id,
                idempotency_key="supervise:cross-env",
            )
    assert calls == 0
