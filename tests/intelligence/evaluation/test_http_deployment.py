from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from backend.intelligence.evaluation.deployment import DeploymentPhase
from backend.intelligence.evaluation.http_deployment import HttpDeploymentPort
from backend.intelligence.evaluation.release_catalog import (
    ReleaseCandidate,
    ReleaseCandidateStatus,
)
from backend.intelligence.evaluation.release_control import ReleaseControlEvent
from backend.platform.security.mtls import MtlsClientConfig


def _candidate() -> ReleaseCandidate:
    now = datetime(2026, 8, 30, tzinfo=UTC)
    return ReleaseCandidate(
        candidate_id="candidate-a",
        environment="staging",
        decision_id="decision-a",
        provider_id="provider-a",
        model="model-a",
        model_version="v1",
        report_ref="benchmark:a",
        status=ReleaseCandidateStatus.APPROVED,
        last_control_id="control-a",
        rollback_target_candidate_id=None,
        registered_at=now,
        updated_at=now,
    )


def _control(*, kind: str = "APPROVAL") -> ReleaseControlEvent:
    return ReleaseControlEvent(
        control_id="control-a",
        kind=kind,  # type: ignore[arg-type]
        idempotency_key="control-key",
        decision_id="decision-a",
        candidate_id="candidate-a",
        environment="staging",
        actor_id="operator-1",
        target_candidate_id="candidate-previous" if kind == "ROLLBACK" else None,
        reason="reviewed",
        signature_ref="signature-ref",
        signature_algorithm="external",
        created_at=datetime(2026, 8, 30, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_http_deployment_port_sends_governed_headers_and_payload() -> None:
    seen: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["json"] = request.read()
        return httpx.Response(202, json={"external_ref": "platform:deploy-1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        port = HttpDeploymentPort(
            base_url="https://deploy.example",
            token_provider=lambda: "token-1",
            client=client,
        )
        result = await port.apply(
            _candidate(),
            _control(),
            phase=DeploymentPhase.CANARY,
            rollout_percent=10,
            idempotency_key="deploy-key",
        )

    assert result.external_ref == "platform:deploy-1"
    assert seen["method"] == "POST"
    assert seen["url"] == "https://deploy.example/v1/releases/candidate-a/deployments"
    headers = seen["headers"]
    assert isinstance(headers, dict)
    assert headers["idempotency-key"] == "deploy-key"
    assert headers["x-ai-control-id"] == "control-a"
    assert headers["authorization"] == "Bearer token-1"


@pytest.mark.asyncio
async def test_http_deployment_port_maps_platform_and_response_errors() -> None:
    async def error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "offline"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(error_handler)) as client:
        port = HttpDeploymentPort(
            base_url="https://deploy.example",
            token_provider=lambda: "token-1",
            client=client,
        )
        with pytest.raises(ValueError, match="PLATFORM_5XX"):
            await port.rollback(
                _candidate(),
                _control(kind="ROLLBACK"),
                idempotency_key="rollback-key",
            )

    async def malformed_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"accepted": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(malformed_handler)) as client:
        port = HttpDeploymentPort(
            base_url="https://deploy.example",
            token_provider=lambda: "token-1",
            client=client,
        )
        with pytest.raises(ValueError, match="EXTERNAL_REF_REQUIRED"):
            await port.apply(
                _candidate(),
                _control(),
                phase=DeploymentPhase.ACTIVE,
                rollout_percent=100,
                idempotency_key="deploy-malformed",
            )


@pytest.mark.asyncio
async def test_http_deployment_port_rejects_redirects_and_token_failures() -> None:
    async def redirect_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://other.example"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(redirect_handler)) as client:
        port = HttpDeploymentPort(
            base_url="https://deploy.example",
            token_provider=lambda: "token-1",
            client=client,
        )
        with pytest.raises(ValueError, match="UNEXPECTED_STATUS"):
            await port.apply(
                _candidate(),
                _control(),
                phase=DeploymentPhase.CANARY,
                rollout_percent=10,
                idempotency_key="deploy-redirect",
            )

    async def unavailable_token() -> str:
        raise RuntimeError("secret should not be persisted")

    port = HttpDeploymentPort(
        base_url="https://deploy.example",
        token_provider=unavailable_token,
    )
    with pytest.raises(ValueError, match="TOKEN_UNAVAILABLE"):
        await port.rollback(
            _candidate(),
            _control(kind="ROLLBACK"),
            idempotency_key="rollback-token-error",
        )


@pytest.mark.asyncio
async def test_http_deployment_port_validates_timeout_and_encodes_candidate_id() -> None:
    with pytest.raises(ValueError, match="TIMEOUT_INVALID"):
        HttpDeploymentPort(
            base_url="https://deploy.example",
            token_provider=lambda: "token-1",
            timeout_seconds=0,
        )

    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"external_ref": "platform:encoded"})

    candidate = replace(_candidate(), candidate_id="candidate/a")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        port = HttpDeploymentPort(
            base_url="https://deploy.example",
            token_provider=lambda: "token-1",
            client=client,
        )
        await port.apply(
            candidate,
            _control(),
            phase=DeploymentPhase.CANARY,
            rollout_percent=10,
            idempotency_key="deploy-encoded",
        )
    assert seen == ["https://deploy.example/v1/releases/candidate%2Fa/deployments"]


def test_http_deployment_port_rejects_client_and_mtls_config_together(tmp_path: Path) -> None:
    cert_paths = []
    for name in ("ca.pem", "client.pem", "client.key"):
        path = tmp_path / name
        path.write_text("placeholder", encoding="utf-8")
        cert_paths.append(str(path))

    client = httpx.AsyncClient()
    try:
        with pytest.raises(ValueError, match="MTLS_CLIENT_CONFLICT"):
            HttpDeploymentPort(
                base_url="https://deploy.example",
                token_provider=lambda: "token-1",
                client=client,
                client_config=MtlsClientConfig(*cert_paths),
            )
    finally:
        asyncio.run(client.aclose())
