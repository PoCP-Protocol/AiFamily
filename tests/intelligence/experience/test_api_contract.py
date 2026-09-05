from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.context_engine.store import ContextBroker
from backend.intelligence.experience.api import (
    MediaInputBody,
    MultimodalDraftRuntime,
    get_multimodal_draft_runtime,
    get_multimodal_draft_runtime_resolver,
    router,
)
from backend.intelligence.experience.multimodal_application import (
    RoutedMultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_context_application import (
    ContextBoundMultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_generation import MultimodalExperienceService
from backend.intelligence.experience.multimodal_routing import (
    QWEN_MULTIMODAL_CANDIDATE,
    MultimodalRouter,
)
from backend.intelligence.experience.standard_assets import (
    FAMILY_EXPERIENCE_PROMPT_VERSION,
    FAMILY_EXPERIENCE_SCHEMA_VERSION,
    family_experience_output_schema,
)
from backend.intelligence.experience.synthetic_runtime import SyntheticRuntimeResolver
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from tests.intelligence.model_gateway.test_fail_closed import build


def _scope(*, family_id: str = "family-api") -> ContextScope:
    return ContextScope(
        tenant_id="tenant-api",
        region_id="CN",
        family_id=family_id,
        subject_ids=("guardian-api", "child-api"),
        purpose="family-image-summary",
        consent_version="consent-api-v1",
        consent_granted=True,
        data_class=DataClass.SYNTHETIC,
        locale="zh-CN",
        deletion_ref="delete:family-api",
        correlation_id="corr:api-001",
        causation_id="cause:api-001",
    )


def _body(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "run_id": "run-api-001",
        "prompt_version": "prompt.v1",
        "schema_version": "schema.v1",
        "payload": {"media_ref": "fixture:image-001"},
        "output_schema": {
            "type": "object",
            "required": ["headline"],
            "properties": {"headline": {"type": "string"}},
        },
        "modalities": ["TEXT", "IMAGE"],
        "estimated_input_tokens": 500,
        "media_inputs": [
            {
                "media_type": "IMAGE",
                "uri": "media:fixture:image-001",
                "mime_type": "image/jpeg",
                "sha256": "a" * 64,
            }
        ],
    }
    value.update(overrides)
    return value


def _runtime(*, family_id: str = "family-api") -> MultimodalDraftRuntime:
    provider = FakeProvider({"family-image-summary": {"headline": "一条可执行的小步骤"}})
    profile = replace(
        QWEN_MULTIMODAL_CANDIDATE,
        provider_id="fake-deterministic",
        status="INTERNAL_APPROVED",
        approved_environments=("test",),
        approved_data_classes=frozenset({"SYNTHETIC"}),
        sub_delegates=False,
    )
    routed = RoutedMultimodalExperienceService(
        router=MultimodalRouter((profile,)),
        generation=MultimodalExperienceService(build(provider)),
    )
    application = ContextBoundMultimodalExperienceService(context=ContextBroker(), routed=routed)
    return MultimodalDraftRuntime(
        scope=_scope(family_id=family_id), application=application, environment="test"
    )


def _client(
    runtime: MultimodalDraftRuntime | None = None,
    resolver: object | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    if runtime is not None:
        app.dependency_overrides[get_multimodal_draft_runtime] = lambda: runtime
    if resolver is not None:
        app.dependency_overrides[get_multimodal_draft_runtime_resolver] = lambda: resolver
    return TestClient(app)


def test_default_runtime_fails_closed_until_scope_and_gateway_are_wired() -> None:
    response = _client().post("/families/family-api/experience/multimodal/drafts", json=_body())

    assert response.status_code == 503
    assert response.json()["detail"] == "multimodal_experience_runtime_not_configured"


def test_request_level_resolver_receives_path_family_not_body_scope() -> None:
    calls: list[str] = []

    class Resolver:
        async def resolve(self, family_id: str) -> MultimodalDraftRuntime:
            calls.append(family_id)
            return _runtime(family_id=family_id)

    with _client(resolver=Resolver()) as client:
        response = client.post(
            "/families/family-resolved/experience/multimodal/drafts", json=_body()
        )

    assert response.status_code == 200
    assert calls == ["family-resolved"]
    assert response.json()["scope"]["family_id"] == "family-resolved"


def test_resolver_cannot_be_overridden_by_body_scope_fields() -> None:
    calls: list[str] = []

    class Resolver:
        async def resolve(self, family_id: str) -> MultimodalDraftRuntime:
            calls.append(family_id)
            return _runtime(family_id=family_id)

    with _client(resolver=Resolver()) as client:
        response = client.post(
            "/families/family-resolved/experience/multimodal/drafts",
            json=_body(
                tenant_id="forged-tenant",
                family_id="forged-family",
                subject_ids=["forged-child"],
                purpose="forged-purpose",
                consent_version="forged-consent",
                context_snapshot_ref="forged-snapshot",
            ),
        )

    assert response.status_code == 422
    assert "extra_forbidden" in response.text
    assert calls == []


def test_real_synthetic_resolver_serves_each_family_path_independently() -> None:
    resolver = SyntheticRuntimeResolver(
        tenant_id="tenant-api",
        subject_ids=("guardian-api", "child-api"),
    )

    with _client(resolver=resolver) as client:
        first = client.post(
            "/families/family-resolved-a/experience/multimodal/drafts",
            json=_body(
                run_id="run-api-family-a",
                prompt_version=FAMILY_EXPERIENCE_PROMPT_VERSION,
                schema_version=FAMILY_EXPERIENCE_SCHEMA_VERSION,
                output_schema=family_experience_output_schema(),
            ),
        )
        second = client.post(
            "/families/family-resolved-b/experience/multimodal/drafts",
            json=_body(
                run_id="run-api-family-b",
                prompt_version=FAMILY_EXPERIENCE_PROMPT_VERSION,
                schema_version=FAMILY_EXPERIENCE_SCHEMA_VERSION,
                output_schema=family_experience_output_schema(),
            ),
        )

    assert first.status_code == 200
    assert second.status_code == 200
    for response, family_id in (
        (first, "family-resolved-a"),
        (second, "family-resolved-b"),
    ):
        value = response.json()
        assert value["scope"]["family_id"] == family_id
        assert value["status"] == "DRAFT"
        assert value["requires_human_confirmation"] is True


def test_client_cannot_supply_scope_snapshot_or_provider_configuration() -> None:
    response = _client(_runtime()).post(
        "/families/family-api/experience/multimodal/drafts",
        json=_body(
            tenant_id="forged-tenant",
            context_snapshot_ref="forged-snapshot",
            provider_id="vendor-secret",
            api_key="do-not-accept",
        ),
    )

    assert response.status_code == 422
    assert "extra_forbidden" in response.text


def test_client_token_hint_does_not_control_route_cost_estimate() -> None:
    with _client(_runtime()) as client:
        low = client.post(
            "/families/family-api/experience/multimodal/drafts",
            json=_body(run_id="run-low-hint", estimated_input_tokens=1),
        )
        high = client.post(
            "/families/family-api/experience/multimodal/drafts",
            json=_body(run_id="run-high-hint", estimated_input_tokens=2_000_000),
        )

    assert low.status_code == high.status_code == 200
    assert (
        low.json()["route"]["estimated_cost_microusd"]
        == high.json()["route"]["estimated_cost_microusd"]
    )


def test_nested_provider_or_scope_controls_are_rejected_from_payload() -> None:
    response = _client(_runtime()).post(
        "/families/family-api/experience/multimodal/drafts",
        json=_body(payload={"nested": {"provider_id": "forged-vendor"}}),
    )

    assert response.status_code == 422
    assert "controlled by the server" in response.text


def test_media_input_accepts_references_but_rejects_inline_payloads() -> None:
    assert MediaInputBody(
        media_type="IMAGE",
        uri="https://media.example.invalid/asset.jpg?signature=short-lived",
        mime_type="image/jpeg",
        sha256="a" * 64,
    ).uri.startswith("https://")
    assert (
        MediaInputBody(
            media_type="IMAGE",
            uri="media:sha256:abc123",
            mime_type="image/jpeg",
            sha256="b" * 64,
        ).uri
        == "media:sha256:abc123"
    )

    for uri in (
        "data:image/png;base64," + "A" * 64,
        "opaque:" + "A" * 300,
        "A" * 300,
        "http://media.example.invalid/asset.jpg",
        "https://user:password@media.example.invalid/asset.jpg",
    ):
        with pytest.raises(ValidationError, match="media uri|inline base64|opaque"):
            MediaInputBody(
                media_type="IMAGE",
                uri=uri,
                mime_type="image/jpeg",
                sha256="c" * 64,
            )


def test_client_modalities_must_match_actual_media_inputs() -> None:
    hidden_image = _client(_runtime()).post(
        "/families/family-api/experience/multimodal/drafts",
        json=_body(modalities=["TEXT"]),
    )
    invented_audio = _client(_runtime()).post(
        "/families/family-api/experience/multimodal/drafts",
        json=_body(modalities=["TEXT", "IMAGE", "AUDIO"]),
    )

    assert hidden_image.status_code == 422
    assert invented_audio.status_code == 422
    assert "server-derived" in hidden_image.text


def test_scope_and_context_snapshot_are_resolved_by_runtime_application() -> None:
    with _client(_runtime()) as client:
        response = client.post("/families/family-api/experience/multimodal/drafts", json=_body())

    assert response.status_code == 200
    value = response.json()
    assert value["status"] == "DRAFT"
    assert value["requires_human_confirmation"] is True
    assert value["scope"] == {
        "tenant_id": "tenant-api",
        "region_id": "CN",
        "family_id": "family-api",
        "subject_ids": ["guardian-api", "child-api"],
        "purpose": "family-image-summary",
        "consent_version": "consent-api-v1",
        "consent_granted": True,
        "data_class": "SYNTHETIC",
        "locale": "zh-CN",
    }
    assert value["context_snapshot_ref"].startswith("context:tenant-api:family-api:")
    assert value["provenance"]["context_snapshot_ref"] == value["context_snapshot_ref"]
    assert value["route"]["provider_id"] == "fake-deterministic"


def test_path_family_must_match_injected_scope() -> None:
    with _client(_runtime(family_id="family-api")) as client:
        response = client.post(
            "/families/another-family/experience/multimodal/drafts", json=_body()
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "family_access_denied"
