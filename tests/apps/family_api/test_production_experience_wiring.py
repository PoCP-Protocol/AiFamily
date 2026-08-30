from __future__ import annotations

from dataclasses import replace

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.apps.family_api.production_experience_wiring import (
    ProductionExperienceRuntimeResolver,
)
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.context_engine.store import ContextBroker
from backend.intelligence.experience.api import get_multimodal_draft_runtime_resolver, router
from backend.intelligence.experience.multimodal_routing import (
    QWEN_MULTIMODAL_CANDIDATE,
    MultimodalRouter,
)
from backend.intelligence.experience.run_store import ExperienceRunPersistenceBase
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provenance import ModelDraftRegistryBase
from backend.intelligence.model_gateway.provider_registry import (
    ProviderRecord,
    ProviderRegistry,
)
from backend.intelligence.model_gateway.providers.fake import FakeProvider


@pytest.fixture
async def production_runtime():
    environment = "development"
    provider_id = "fake-production-contract"
    provider = FakeProvider(
        {"family-image-summary": {"headline": "已生成", "next_step": "请确认"}},
        provider_id=provider_id,
    )
    provider_record = ProviderRecord(
        provider_id=provider_id,
        vendor="internal-contract-test",
        model="fake-production-contract",
        model_version="1.0.0",
        status="INTERNAL_APPROVED",
        approved_environments=(environment,),
        sub_delegates=False,
        security_assessment_ref="in-process",
        processing_agreement_ref="in-process",
        deletion_on_termination_committed=True,
    )
    gateway = ModelGateway(
        {provider_id: provider},
        environment=environment,
        registry=ProviderRegistry((provider_record,)),
    )
    profile = replace(
        QWEN_MULTIMODAL_CANDIDATE,
        provider_id=provider_id,
        vendor="internal-contract-test",
        model="fake-production-contract",
        model_version="1.0.0",
        status="INTERNAL_APPROVED",
        approved_environments=(environment,),
        approved_data_classes=frozenset({"OPERATIONAL_TEXT"}),
        sub_delegates=False,
        security_assessment_ref="in-process",
        processing_agreement_ref="in-process",
        deletion_on_termination_committed=True,
    )
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(ExperienceRunPersistenceBase.metadata.create_all)
        await connection.run_sync(ModelDraftRegistryBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    scope = ContextScope(
        tenant_id="tenant-production",
        region_id="CN",
        family_id="family-production",
        subject_ids=("guardian-production",),
        purpose="family-image-summary",
        consent_version="consent.v1",
        consent_granted=True,
        data_class=DataClass.OPERATIONAL_TEXT,
        locale="zh-CN",
        deletion_ref="delete:production",
        correlation_id="corr:production",
        causation_id="cause:production",
    )
    resolver = ProductionExperienceRuntimeResolver(
        scope_resolver=lambda family_id: scope if family_id == scope.family_id else scope,
        session_factory=session_factory,
        gateway=gateway,
        router=MultimodalRouter((profile,)),
        context_broker=ContextBroker(),
        environment=environment,
    )
    try:
        yield resolver, provider, scope
    finally:
        await engine.dispose()


def _body(run_id: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "prompt_version": "experience.v1",
        "schema_version": "experience.v1",
        "payload": {"expression": "今天我们一起看这张图片。"},
        "output_schema": {
            "type": "object",
            "required": ["headline", "next_step"],
            "properties": {
                "headline": {"type": "string"},
                "next_step": {"type": "string"},
            },
        },
        "modalities": ["TEXT", "IMAGE"],
        "estimated_input_tokens": 64,
        "media_inputs": [
            {
                "media_type": "IMAGE",
                "uri": "media:fixture:family-image-1",
                "mime_type": "image/jpeg",
                "sha256": "a" * 64,
            }
        ],
    }


@pytest.mark.asyncio
async def test_production_resolver_commits_draft_and_replays_without_provider_call(
    production_runtime,
) -> None:
    resolver, provider, scope = production_runtime
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_multimodal_draft_runtime_resolver] = lambda: resolver

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            f"/families/{scope.family_id}/experience/multimodal/drafts",
            json=_body("run-production-1"),
            headers={"Idempotency-Key": "production-create-1"},
        )
        replay = await client.post(
            f"/families/{scope.family_id}/experience/multimodal/drafts",
            json=_body("run-production-1"),
            headers={"Idempotency-Key": "production-create-1"},
        )
        snapshot = await client.get(
            f"/families/{scope.family_id}/experience/multimodal/runs/run-production-1/replay"
        )

    assert first.status_code == 200, first.text
    assert first.json()["draft_id"] == "draft:run-production-1"
    assert first.json()["provenance_ref"] == "model-draft:run-production-1"
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    assert snapshot.status_code == 200, snapshot.text
    assert snapshot.json()["status"] == "DRAFT"
    assert snapshot.json()["deletion_state"] == "active"
    assert len(provider.invocations) == 1


def test_production_resolver_rejects_test_environment() -> None:
    with pytest.raises(ValueError, match="test environment"):
        ProductionExperienceRuntimeResolver(
            scope_resolver=lambda _: None,  # type: ignore[return-value]
            session_factory=object(),  # type: ignore[arg-type]
            gateway=object(),  # type: ignore[arg-type]
            router=object(),  # type: ignore[arg-type]
            context_broker=object(),  # type: ignore[arg-type]
            environment="test",
        )
