from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from backend.intelligence.evaluation.deployment import (
    DeploymentOperation,
    DeploymentPhase,
    DeploymentReceipt,
)
from backend.intelligence.evaluation.release_catalog import (
    ReleaseCandidate,
    ReleaseCandidateStatus,
)
from backend.intelligence.experience.canary_supervision import CanarySupervisionError
from backend.intelligence.experience.http_canary_observation import (
    HttpCanaryObservationPort,
)

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


def _candidate() -> ReleaseCandidate:
    return ReleaseCandidate(
        candidate_id="family-experience:candidate-a",
        environment="test",
        decision_id="decision-a",
        provider_id="provider-a",
        model="multimodal-a",
        model_version="2026-08",
        report_ref="benchmark:a",
        status=ReleaseCandidateStatus.APPROVED,
        last_control_id="approval-a",
        rollback_target_candidate_id=None,
        registered_at=NOW,
        updated_at=NOW,
    )


def _receipt() -> DeploymentReceipt:
    return DeploymentReceipt(
        receipt_id="receipt-a",
        operation=DeploymentOperation.APPLY,
        phase=DeploymentPhase.CANARY,
        idempotency_key="deploy:a",
        candidate_id=_candidate().candidate_id,
        environment="test",
        control_id="approval-a",
        actor_id="operator-1",
        rollout_percent=5,
        external_ref="external:a",
        created_at=NOW,
    )


@pytest.mark.asyncio
async def test_http_observation_uses_metadata_only_contract() -> None:
    captured: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "observation_id": "observation-a",
                "receipt_id": "receipt-a",
                "candidate_id": _candidate().candidate_id,
                "environment": "test",
                "observed_at": "2026-08-31T12:05:00Z",
                "window_seconds": 300,
                "request_count": 200,
                "error_rate": 0.01,
                "p95_latency_ms": 800,
                "safety_violation_count": 0,
                "minor_safety_violation_count": 0,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        observation = await HttpCanaryObservationPort(
            base_url="https://deployment.example",
            token_provider=lambda: "short-lived",
            client=client,
        ).observe(_candidate(), _receipt(), idempotency_key="observe:a")

    payload = json.loads(captured[0].content)
    assert observation.request_count == 200
    assert observation.observed_at.tzinfo is not None
    assert captured[0].url.raw_path == (
        b"/v1/releases/family-experience%3Acandidate-a/canary-observations"
    )
    assert captured[0].headers["idempotency-key"] == "observe:a"
    assert payload == {
        "candidate_id": _candidate().candidate_id,
        "environment": "test",
        "receipt_id": "receipt-a",
        "deployment_ref": "external:a",
    }
    assert "family_id" not in captured[0].content.decode()
    assert "short-lived" not in captured[0].content.decode()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(503), "PLATFORM_5XX"),
        (httpx.Response(200, text="not-json"), "INVALID_JSON"),
        (httpx.Response(200, json={"observation_id": "partial"}), "RESPONSE_INVALID"),
    ],
)
async def test_http_observation_fails_closed_on_platform_or_schema_errors(
    response: httpx.Response, error: str
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: response)
    ) as client:
        port = HttpCanaryObservationPort(
            base_url="https://deployment.example",
            token_provider=lambda: "short-lived",
            client=client,
        )
        with pytest.raises(CanarySupervisionError, match=error):
            await port.observe(_candidate(), _receipt(), idempotency_key="observe:bad")


@pytest.mark.asyncio
async def test_http_observation_rejects_missing_token_before_network() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        port = HttpCanaryObservationPort(
            base_url="https://deployment.example",
            token_provider=lambda: "",
            client=client,
        )
        with pytest.raises(CanarySupervisionError, match="TOKEN_REQUIRED"):
            await port.observe(_candidate(), _receipt(), idempotency_key="observe:no-token")
    assert calls == 0
