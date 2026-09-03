from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime

import httpx
import pytest

from backend.apps.family_api.family_experience_release_wiring import (
    build_http_family_experience_release_runtime,
)
from backend.intelligence.evaluation.deployment import (
    DeploymentPhase,
    InMemoryDeploymentReceiptStore,
)
from backend.intelligence.evaluation.release_catalog import (
    ReleaseCandidate,
    ReleaseCandidateStatus,
)
from backend.intelligence.evaluation.release_control import ReleaseControlEvent
from backend.intelligence.experience.http_release_bundle_deployment import (
    HttpFamilyExperienceDeploymentPort,
)
from backend.intelligence.experience.release_bundle import FamilyExperienceReleaseBundle
from backend.intelligence.experience.release_bundle_persistence import (
    InMemoryFamilyExperienceReleaseBundleStore,
)

NOW = datetime(2026, 8, 31, 10, 0, tzinfo=UTC)


def _artifacts(environment: str):
    bundle = FamilyExperienceReleaseBundle(
        bundle_id="b" * 64,
        candidate_id="family-experience:candidate-a",
        environment=environment,
        use_case="family_assistant_conversation",
        agent_id="parent_advisor",
        provider_id="provider-a",
        model="multimodal-a",
        model_version="2026-08",
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
        report_ref="benchmark:family-experience:2026-08",
        decision_id="d" * 64,
        control_id="c" * 64,
        approval_signature_ref="s" * 64,
        approval_signature_algorithm="external-kms-v1",
        approved_by="operator-1",
        approved_at=NOW,
        asset_digest="a" * 64,
        human_gate_rule="REVIEW_REQUIRED",
    )
    candidate = ReleaseCandidate(
        candidate_id=bundle.candidate_id,
        environment=environment,
        decision_id=bundle.decision_id,
        provider_id=bundle.provider_id,
        model=bundle.model,
        model_version=bundle.model_version,
        report_ref=bundle.report_ref,
        status=ReleaseCandidateStatus.APPROVED,
        last_control_id=bundle.control_id,
        rollback_target_candidate_id=None,
        registered_at=NOW,
        updated_at=NOW,
    )
    control = ReleaseControlEvent(
        control_id=bundle.control_id,
        kind="APPROVAL",
        idempotency_key=f"approve:{environment}",
        decision_id=bundle.decision_id,
        candidate_id=bundle.candidate_id,
        environment=environment,
        actor_id="operator-1",
        target_candidate_id=None,
        reason="reviewed",
        signature_ref=bundle.approval_signature_ref,
        signature_algorithm=bundle.approval_signature_algorithm,
        created_at=NOW,
    )
    return bundle, candidate, control


async def _exercise_http_runtime(environment: str):
    bundle, candidate, control = _artifacts(environment)
    bundles = InMemoryFamilyExperienceReleaseBundleStore()
    await bundles.append(bundle)
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1/operator/identity":
            return httpx.Response(
                200,
                json={
                    "operator_id": "operator-1",
                    "environment": environment,
                    "authorization_ref": f"auth:{environment}",
                    "scopes": ["ai.release.deploy"],
                },
            )
        if request.url.path == "/v1/operator/tokens":
            return httpx.Response(200, json={"access_token": "short-lived"})
        return httpx.Response(200, json={"external_ref": f"deployment:{environment}"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        runtime = build_http_family_experience_release_runtime(
            environment=environment,
            identity_base_url="https://identity.example",
            deployment_base_url="https://deployment.example",
            bootstrap_token_provider=lambda: "bootstrap",
            audience="family-experience-deployment",
            bundle_store=bundles,
            receipt_store=InMemoryDeploymentReceiptStore(),
            identity_client=client,
            deployment_client=client,
            clock=lambda: NOW,
        )
        receipt = await runtime.apply(
            candidate,
            control,
            phase=DeploymentPhase.CANARY,
            rollout_percent=5,
            idempotency_key=f"deploy:{environment}:canary",
        )
    return bundle, receipt, requests


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", ["development", "test", "staging", "production"])
async def test_release_runtime_has_full_function_parity_across_environments(
    environment: str,
) -> None:
    bundle, receipt, requests = await _exercise_http_runtime(environment)

    assert receipt.external_ref == f"deployment:{environment}"
    assert receipt.created_at == NOW
    assert [request.url.path for request in requests] == [
        "/v1/operator/identity",
        "/v1/operator/identity",
        "/v1/operator/tokens",
        "/v1/releases/family-experience:candidate-a/deployments",
    ]
    deployment_request = requests[-1]
    assert deployment_request.url.raw_path == (
        b"/v1/releases/family-experience%3Acandidate-a/deployments"
    )
    payload = json.loads(deployment_request.content)
    assert payload["release_bundle"]["bundle_id"] == bundle.bundle_id
    assert payload["release_bundle"]["prompt_version"] == bundle.prompt_version
    assert payload["release_bundle"]["schema_version"] == bundle.schema_version
    assert payload["release_bundle"]["human_gate_rule"] == "REVIEW_REQUIRED"
    assert payload["release_bundle"]["draft_only"] is True
    assert payload["release_bundle"]["may_mutate_business_state"] is False
    assert deployment_request.headers["x-ai-control-id"] == bundle.control_id


@pytest.mark.asyncio
async def test_http_bundle_payload_contains_no_raw_prompt_signature_or_family_data() -> None:
    _, _, requests = await _exercise_http_runtime("test")
    payload_text = requests[-1].content.decode("utf-8")

    assert "prompt_template" not in payload_text
    assert "raw_signature" not in payload_text
    assert "family_id" not in payload_text
    assert "tenant_id" not in payload_text
    assert "bootstrap" not in payload_text
    assert "short-lived" not in payload_text


@pytest.mark.asyncio
async def test_http_rollback_also_carries_complete_bundle_and_target() -> None:
    bundle, candidate, approval = _artifacts("staging")
    rollback = replace(
        approval,
        control_id="r" * 64,
        kind="ROLLBACK",
        idempotency_key="rollback:staging",
        target_candidate_id="family-experience:previous",
        reason="canary SLO breached",
    )
    captured: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"external_ref": "rollback:accepted"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        port = HttpFamilyExperienceDeploymentPort(
            base_url="https://deployment.example",
            token_provider=lambda: "short-lived",
            client=client,
        )
        result = await port.rollback(
            bundle,
            candidate,
            rollback,
            idempotency_key="rollback:staging",
        )

    payload = json.loads(captured[0].content)
    assert result.external_ref == "rollback:accepted"
    assert captured[0].url.path.endswith("/rollback")
    assert captured[0].headers["x-ai-control-id"] == rollback.control_id
    assert payload["target_candidate_id"] == "family-experience:previous"
    assert payload["release_bundle"]["bundle_id"] == bundle.bundle_id
    assert payload["release_bundle"]["control_id"] == approval.control_id
