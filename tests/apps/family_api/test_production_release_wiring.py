from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from backend.apps.family_api.production_release_wiring import (
    ProductionReleaseWiringError,
    build_http_production_release_runtime,
    build_production_release_runtime,
)
from backend.intelligence.evaluation.deployment import (
    DeploymentPhase,
    DeploymentResult,
    InMemoryDeploymentReceiptStore,
)
from backend.intelligence.evaluation.operator_identity import (
    OperatorIdentity,
    OperatorIdentityError,
)
from backend.intelligence.evaluation.release_catalog import (
    ReleaseCandidate,
    ReleaseCandidateStatus,
)
from backend.intelligence.evaluation.release_control import ReleaseControlEvent

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


class _IdentityPort:
    def __init__(self, identity: OperatorIdentity) -> None:
        self.identity = identity
        self.environments: list[str] = []

    async def resolve(self, *, environment: str) -> OperatorIdentity:
        self.environments.append(environment)
        return self.identity


class _DeploymentPort:
    def __init__(self) -> None:
        self.calls = 0

    async def apply(self, candidate, control, *, phase, rollout_percent, idempotency_key):
        self.calls += 1
        return DeploymentResult(external_ref=f"external:{idempotency_key}")

    async def rollback(self, candidate, control, *, idempotency_key):
        self.calls += 1
        return DeploymentResult(external_ref=f"rollback:{idempotency_key}")


def _candidate() -> ReleaseCandidate:
    return ReleaseCandidate(
        candidate_id="candidate-a",
        environment="staging",
        decision_id="decision-a",
        provider_id="provider-a",
        model="model-a",
        model_version="v1",
        report_ref="report:a",
        status=ReleaseCandidateStatus.APPROVED,
        last_control_id="control-a",
        rollback_target_candidate_id=None,
        registered_at=NOW,
        updated_at=NOW,
    )


def _control() -> ReleaseControlEvent:
    return ReleaseControlEvent(
        control_id="control-a",
        kind="APPROVAL",
        idempotency_key="approve:a",
        decision_id="decision-a",
        candidate_id="candidate-a",
        environment="staging",
        actor_id="operator-1",
        target_candidate_id=None,
        reason="reviewed",
        signature_ref="signature-ref",
        signature_algorithm="external",
        created_at=NOW,
    )


@pytest.mark.asyncio
async def test_production_release_runtime_derives_human_actor_from_identity() -> None:
    identity_port = _IdentityPort(
        OperatorIdentity(
            operator_id="operator-1",
            environment="staging",
            authorization_ref="auth-ref",
            scopes=("ai.release.deploy",),
        )
    )
    deployment_port = _DeploymentPort()
    runtime = build_production_release_runtime(
        environment="staging",
        identity_port=identity_port,
        deployment_port=deployment_port,
        receipt_store=InMemoryDeploymentReceiptStore(),
    )

    receipt = await runtime.apply(
        _candidate(),
        _control(),
        phase=DeploymentPhase.CANARY,
        rollout_percent=10,
        idempotency_key="deploy:a",
    )

    assert receipt.actor_id == "operator-1"
    assert identity_port.environments == ["staging"]
    assert deployment_port.calls == 1


@pytest.mark.asyncio
async def test_production_release_runtime_requires_deploy_scope_before_port_call() -> None:
    identity_port = _IdentityPort(
        OperatorIdentity(
            operator_id="operator-1",
            environment="staging",
            authorization_ref="auth-ref",
            scopes=("ai.release.read",),
        )
    )
    deployment_port = _DeploymentPort()
    runtime = build_production_release_runtime(
        environment="staging",
        identity_port=identity_port,
        deployment_port=deployment_port,
        receipt_store=InMemoryDeploymentReceiptStore(),
    )

    with pytest.raises(OperatorIdentityError, match="SCOPE_MISSING"):
        await runtime.apply(
            _candidate(),
            _control(),
            phase=DeploymentPhase.CANARY,
            rollout_percent=10,
            idempotency_key="deploy:scope",
        )
    assert deployment_port.calls == 0


@pytest.mark.asyncio
async def test_http_production_release_factory_keeps_identity_and_deployment_paths_equal() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1/operator/identity":
            return httpx.Response(
                200,
                json={
                    "operator_id": "operator-1",
                    "environment": "staging",
                    "authorization_ref": "auth-ref",
                    "scopes": ["ai.release.deploy"],
                },
            )
        if request.url.path == "/v1/operator/tokens":
            return httpx.Response(200, json={"access_token": "short-lived"})
        return httpx.Response(200, json={"external_ref": "platform-deploy-a"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        runtime = build_http_production_release_runtime(
            environment="staging",
            identity_base_url="https://identity.example",
            deployment_base_url="https://deploy.example",
            bootstrap_token_provider=lambda: "bootstrap",
            audience="deployment-platform",
            receipt_store=InMemoryDeploymentReceiptStore(),
            identity_client=client,
            deployment_client=client,
        )
        receipt = await runtime.apply(
            _candidate(),
            _control(),
            phase=DeploymentPhase.CANARY,
            rollout_percent=10,
            idempotency_key="deploy:http",
        )

    assert receipt.actor_id == "operator-1"
    assert [request.url.path for request in requests] == [
        "/v1/operator/identity",
        "/v1/operator/identity",
        "/v1/operator/tokens",
        "/v1/releases/candidate-a/deployments",
    ]
    assert requests[-1].headers["idempotency-key"] == "deploy:http"


def test_production_release_runtime_rejects_non_production_environment() -> None:
    with pytest.raises(ProductionReleaseWiringError, match="STAGING_OR_PRODUCTION"):
        build_production_release_runtime(
            environment="test",
            identity_port=_IdentityPort(
                OperatorIdentity("operator-1", "test", "auth", ("ai.release.deploy",))
            ),
            deployment_port=_DeploymentPort(),
            receipt_store=InMemoryDeploymentReceiptStore(),
        )
