from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.experience.api import (
    MultimodalDraftRuntime,
    get_multimodal_draft_runtime,
    router,
)
from backend.intelligence.model_gateway.errors import ModelGatewayError


def _scope() -> ContextScope:
    return ContextScope(
        tenant_id="tenant-errors",
        region_id="CN",
        family_id="family-errors",
        subject_ids=("guardian-errors",),
        purpose="family-image-summary",
        consent_version="consent-errors-v1",
        consent_granted=True,
        data_class=DataClass.SYNTHETIC,
        locale="zh-CN",
        deletion_ref="delete:errors",
        correlation_id="corr:errors",
        causation_id="cause:errors",
    )


class _GatewayFailureApplication:
    async def generate_draft(self, _command: object) -> object:
        raise ModelGatewayError("NETWORK_ERROR", "provider secret must not leak")


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_multimodal_draft_runtime] = lambda: MultimodalDraftRuntime(
        scope=_scope(), application=_GatewayFailureApplication(), environment="test"
    )
    return TestClient(app)


def test_gateway_failure_is_mapped_to_stable_error_without_provider_text() -> None:
    with _client() as client:
        response = client.post(
            "/families/family-errors/experience/multimodal/drafts",
            json={
                "run_id": "run-errors",
                "prompt_version": "prompt.v1",
                "schema_version": "schema.v1",
                "payload": {"expression": "test"},
                "output_schema": {"type": "object", "properties": {"headline": {"type": "string"}}},
                "modalities": ["TEXT"],
                "estimated_input_tokens": 8,
            },
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "NETWORK_ERROR"}
    assert "provider secret" not in response.text


@pytest.mark.parametrize(
    ("kind", "expected_status"),
    [("TIMEOUT", 504), ("POLICY_REJECTED", 503)],
)
def test_gateway_error_status_preserves_retry_semantics(kind: str, expected_status: int) -> None:
    class FailureApplication:
        async def generate_draft(self, _command: object) -> object:
            raise ModelGatewayError(kind, "safe message")  # type: ignore[arg-type]

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_multimodal_draft_runtime] = lambda: MultimodalDraftRuntime(
        scope=_scope(), application=FailureApplication(), environment="test"
    )
    with TestClient(app) as client:
        response = client.post(
            "/families/family-errors/experience/multimodal/drafts",
            json={
                "run_id": f"run-{kind.lower()}",
                "prompt_version": "prompt.v1",
                "schema_version": "schema.v1",
                "payload": {"expression": "test"},
                "output_schema": {"type": "object"},
                "modalities": ["TEXT"],
                "estimated_input_tokens": 8,
            },
        )

    assert response.status_code == expected_status
    assert response.json() == {"detail": kind}
