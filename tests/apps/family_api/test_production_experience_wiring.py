from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.apps.family_api.production_experience_wiring import (
    ProductionExperienceRuntimeResolver,
    install_sql_experience_runtime_wiring,
)
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.context_engine.sql_store import SqlContextBrokerFactory
from backend.intelligence.context_engine.store import ContextBroker
from backend.intelligence.experience.api import get_multimodal_draft_runtime_resolver, router
from backend.intelligence.experience.asset_digest import (
    family_experience_contract_asset_digest,
)
from backend.intelligence.experience.execution_materials import (
    ExecutionMaterialBase,
    SqlAlchemyExecutionMaterialRegistry,
)
from backend.intelligence.experience.multimodal_routing import (
    QWEN_MULTIMODAL_CANDIDATE,
    MultimodalRouter,
)
from backend.intelligence.experience.release_bundle import FamilyExperienceReleaseBundle
from backend.intelligence.experience.release_bundle_persistence import (
    FamilyExperienceReleaseBundleBase,
    SqlAlchemyFamilyExperienceReleaseBundleStore,
)
from backend.intelligence.experience.release_set import (
    FamilyExperienceReleaseSet,
    build_family_experience_release_set,
)
from backend.intelligence.experience.release_set_deployment import (
    ReleaseSetDeploymentBase,
    ReleaseSetDeploymentReceipt,
    SqlAlchemyReleaseSetDeploymentStore,
)
from backend.intelligence.experience.release_set_persistence import (
    FamilyExperienceReleaseSetBase,
    SqlAlchemyFamilyExperienceReleaseSetStore,
)
from backend.intelligence.experience.run_store import ExperienceRunPersistenceBase
from backend.intelligence.experience.runtime_release_binding import (
    ActiveFamilyExperienceRuntimeBinding,
    StaticActiveFamilyExperienceReleaseResolver,
)
from backend.intelligence.experience.sql_contract_binding import (
    build_sql_family_experience_contract_binding,
)
from backend.intelligence.experience.standard_asset_registration import (
    register_family_experience_assets,
)
from backend.intelligence.experience.standard_assets import build_family_experience_assets
from backend.intelligence.model_gateway.attempt_persistence import (
    AttemptPersistenceBase,
    SessionPerCallAttemptSink,
    SqlAlchemyAttemptSink,
)
from backend.intelligence.model_gateway.budget import (
    ModelBudgetBase,
    ModelBudgetPolicy,
    ModelBudgetReservationRow,
    ModelBudgetRuntime,
    ModelRate,
    ModelRateCard,
    SqlAlchemyModelBudgetStore,
    build_budget_account,
)
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provenance import ModelDraftRegistryBase, ModelDraftRow
from backend.intelligence.model_gateway.provider_registry import (
    ProviderRecord,
    ProviderRegistry,
)
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.intelligence.observability import (
    SessionPerCallTelemetrySink,
    SqlAlchemyTelemetrySink,
    TelemetryPersistenceBase,
)
from backend.intelligence.prompt_registry import (
    PromptPersistenceBase,
    SqlAlchemyPromptRegistry,
)
from backend.intelligence.safety.persistence import (
    SafetyDecisionPersistenceBase,
    SessionPerCallSafetyDecisionSink,
    SqlAlchemySafetyDecisionSink,
)
from backend.intelligence.safety.runtime import SafetyRuntime
from backend.intelligence.schema_registry import (
    SchemaPersistenceBase,
    SqlAlchemySchemaRegistry,
)


class _DurableTestContextBroker(ContextBroker):
    """Explicitly marked test double for the production composition contract."""

    durability_mode = "DURABLE"


def _active_release_receipt(
    release_set: FamilyExperienceReleaseSet,
    marker: str,
) -> ReleaseSetDeploymentReceipt:
    return ReleaseSetDeploymentReceipt(
        sequence=0,
        receipt_id=f"receipt:{marker}",
        idempotency_key=f"deploy:{marker}",
        release_set_id=release_set.release_set_id,
        target_release_set_id=None,
        environment=release_set.environment,
        use_case=release_set.use_case,
        data_class=release_set.data_class,
        operation="APPLY",
        phase="ACTIVE",
        rollout_percent=100,
        control_id=f"control:{marker}",
        actor_id="operator:release",
        applied_config_digest=release_set.runtime_config_digest,
        acknowledged_release_set_id=release_set.release_set_id,
        external_ref=f"deployment:{marker}",
        created_at=datetime.now(UTC),
    )


@pytest.fixture
async def production_runtime():
    environment = "staging"
    provider_id = "fake-production-contract"
    provider = FakeProvider(
        {
            "family_assistant_conversation": {
                "understanding": "已生成",
                "next_step": "请确认",
                "limitations": ["仍需人工判断"],
            }
        },
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
        await connection.run_sync(AttemptPersistenceBase.metadata.create_all)
        await connection.run_sync(SafetyDecisionPersistenceBase.metadata.create_all)
        await connection.run_sync(TelemetryPersistenceBase.metadata.create_all)
        await connection.run_sync(PromptPersistenceBase.metadata.create_all)
        await connection.run_sync(SchemaPersistenceBase.metadata.create_all)
        await connection.run_sync(ExecutionMaterialBase.metadata.create_all)
        await connection.run_sync(ModelBudgetBase.metadata.create_all)
        await connection.run_sync(FamilyExperienceReleaseBundleBase.metadata.create_all)
        await connection.run_sync(FamilyExperienceReleaseSetBase.metadata.create_all)
        await connection.run_sync(ReleaseSetDeploymentBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    budget_policy = ModelBudgetPolicy(
        version="production-test-budget.v1",
        rate_card_version="production-test-rate.v1",
        per_request_limit_microusd=1_000_000,
        period_limit_microusd=100_000_000,
        max_completion_tokens=8_192,
    )
    budget_store = SqlAlchemyModelBudgetStore(session_factory)
    budget_now = datetime.now(UTC)
    await budget_store.provision_account(
        build_budget_account(
            tenant_id="tenant-production",
            environment=environment,
            policy=budget_policy,
            now=budget_now,
        )
    )
    budget_runtime = ModelBudgetRuntime(
        store=budget_store,
        rate_card=ModelRateCard(
            version="production-test-rate.v1",
            rates=(
                ModelRate(
                    provider_id=provider_id,
                    model="fake-production-contract",
                    prompt_microusd_per_1k=1,
                    completion_microusd_per_1k=1,
                    media_item_microusd=1,
                ),
                ModelRate(
                    provider_id="fake-production-fallback",
                    model="fake-production-fallback",
                    prompt_microusd_per_1k=1,
                    completion_microusd_per_1k=1,
                    media_item_microusd=1,
                ),
            ),
            effective_at=budget_now - timedelta(days=1),
            expires_at=budget_now + timedelta(days=365),
        ),
        policy=budget_policy,
        environment=environment,
        clock=lambda: budget_now,
    )
    safety_runtime = SafetyRuntime()
    gateway = ModelGateway(
        {provider_id: provider},
        environment=environment,
        registry=ProviderRegistry((provider_record,)),
        safety_runtime=safety_runtime,
        budget_runtime=budget_runtime,
    )
    scope = ContextScope(
        tenant_id="tenant-production",
        region_id="CN",
        family_id="family-production",
        subject_ids=("guardian-production",),
        purpose="family_assistant_conversation",
        consent_version="consent.v1",
        consent_granted=True,
        data_class=DataClass.OPERATIONAL_TEXT,
        locale="zh-CN",
        deletion_ref="delete:production",
        correlation_id="corr:production",
        causation_id="cause:production",
    )
    assets = build_family_experience_assets(
        status="PUBLISHED",
        reviewer="synthetic-reviewer",
        effective_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    async with session_factory() as session, session.begin():
        await register_family_experience_assets(
            assets=assets,
            prompt_registry=SqlAlchemyPromptRegistry(session),
            schema_registry=SqlAlchemySchemaRegistry(session),
            material_registry=SqlAlchemyExecutionMaterialRegistry(session),
        )
    contract_binding = build_sql_family_experience_contract_binding(
        session_factory=session_factory
    )
    multimodal_router = MultimodalRouter((profile,))
    release_bundle = FamilyExperienceReleaseBundle(
        bundle_id="b" * 64,
        candidate_id="candidate:fake-production-contract",
        environment=environment,
        use_case=scope.purpose,
        agent_id="parent_advisor",
        provider_id=provider.provider_id,
        model=profile.model,
        model_version=profile.model_version,
        prompt_ref=assets.prompt.prompt_ref,
        prompt_version=assets.prompt.version,
        schema_ref=assets.schema.schema_ref,
        schema_version=assets.schema.version,
        safety_policy_version=assets.prompt.safety_policy_version,
        routing_policy_version=multimodal_router.policy_version,
        rate_card_version=budget_runtime.rate_card.version,
        budget_policy_version=budget_runtime.policy.version,
        knowledge_refs=assets.prompt.knowledge_refs,
        data_class="OPERATIONAL_TEXT",
        report_ref="benchmark:production-contract",
        decision_id="d" * 64,
        control_id="c" * 64,
        approval_signature_ref="s" * 64,
        approval_signature_algorithm="external-kms-v1",
        approved_by="operator:release",
        approved_at=datetime.now(UTC),
        asset_digest=family_experience_contract_asset_digest(
            prompt=assets.prompt,
            schema=assets.schema,
            system_policy=assets.system_policy,
            knowledge=assets.knowledge,
        ),
        human_gate_rule="REVIEW_REQUIRED",
    )
    release_set = build_family_experience_release_set(
        bundles=(release_bundle,),
        router=multimodal_router,
        budget_runtime=budget_runtime,
        safety_runtime=safety_runtime,
    )
    async with session_factory() as session, session.begin():
        await SqlAlchemyFamilyExperienceReleaseBundleStore(session).append(release_bundle)
        await SqlAlchemyFamilyExperienceReleaseSetStore(session).append(release_set)
        await SqlAlchemyReleaseSetDeploymentStore(session).append(
            _active_release_receipt(release_set, "initial")
        )
    resolver = ProductionExperienceRuntimeResolver(
        scope_resolver=lambda family_id: scope if family_id == scope.family_id else scope,
        session_factory=session_factory,
        gateway=gateway,
        router=multimodal_router,
        context_broker=_DurableTestContextBroker(),
        environment=environment,
        attempt_sink_factory=SessionPerCallAttemptSink,
        safety_sink_factory=SessionPerCallSafetyDecisionSink,
        telemetry_sink_factory=SessionPerCallTelemetrySink,
        contract_binding=contract_binding,
    )
    try:
        yield resolver, provider, scope
    finally:
        await engine.dispose()


def _body(run_id: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "prompt_version": "family-companion.v1",
        "schema_version": "family-experience-draft.v1",
        "payload": {"expression": "今天我们一起看这张图片。"},
        "output_schema": {
            "type": "object",
            "required": ["understanding", "next_step", "limitations"],
            "properties": {
                "understanding": {"type": "string", "minLength": 1},
                "next_step": {"type": "string", "minLength": 1},
                "limitations": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string", "minLength": 1},
                },
            },
            "additionalProperties": False,
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
    async with resolver.session_factory() as session:
        attempts = await SqlAlchemyAttemptSink(session).list_attempts(
            request_id="run-production-1"
        )
        safety_decisions = await SqlAlchemySafetyDecisionSink(session).list_decisions(
            request_id="run-production-1"
        )
        telemetry_spans = await SqlAlchemyTelemetrySink(session).list_spans(
            trace_id="run-production-1"
        )
        budget_rows = tuple(
            await session.scalars(select(ModelBudgetReservationRow))
        )
        draft_rows = tuple(await session.scalars(select(ModelDraftRow)))

    assert first.status_code == 200, first.text
    assert first.json()["draft_id"] == "draft:run-production-1"
    assert first.json()["provenance_ref"] == "model-draft:run-production-1"
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    assert snapshot.status_code == 200, snapshot.text
    assert snapshot.json()["status"] == "DRAFT"
    assert snapshot.json()["deletion_state"] == "active"
    assert len(provider.invocations) == 1
    assert len(attempts) == 1
    assert attempts[0].status == "SUCCESS"
    assert [item.stage for item in safety_decisions] == ["input", "output"]
    assert len(telemetry_spans) == 1
    assert telemetry_spans[0].status == "OK"
    active_binding = await resolver.active_release_resolver.resolve(
        environment=resolver.environment,
        use_case=scope.purpose,
        data_class=scope.data_class.value,
    )
    release_set = active_binding.release_set
    assert attempts[0].release_set_id == release_set.release_set_id
    assert attempts[0].bundle_id == release_set.bundle_ids[0]
    assert attempts[0].deployment_receipt_id == active_binding.deployment_receipt.receipt_id
    assert budget_rows[0].release_set_id == release_set.release_set_id
    assert budget_rows[0].bundle_id == release_set.bundle_ids[0]
    assert budget_rows[0].deployment_receipt_id == active_binding.deployment_receipt.receipt_id
    assert draft_rows[0].provenance_payload["release_set_id"] == release_set.release_set_id
    assert draft_rows[0].provenance_payload["bundle_id"] == release_set.bundle_ids[0]


@pytest.mark.asyncio
async def test_production_path_uses_independently_admitted_fallback_on_5xx_only(
    production_runtime,
) -> None:
    resolver, primary, scope = production_runtime
    fallback = FakeProvider(
        {
            "family_assistant_conversation": {
                "understanding": "备用模型已完成",
                "next_step": "请确认",
                "limitations": ["仍需人工判断"],
            }
        },
        provider_id="fake-production-fallback",
        model="fake-production-fallback",
    )
    primary_record = resolver.gateway.registry.get(primary.provider_id)
    fallback_record = ProviderRecord(
        provider_id=fallback.provider_id,
        vendor="internal-contract-fallback",
        model="fake-production-fallback",
        model_version="1.0.0",
        status="INTERNAL_APPROVED",
        approved_environments=(resolver.environment,),
        sub_delegates=False,
        security_assessment_ref="in-process-fallback",
        processing_agreement_ref="in-process-fallback",
        deletion_on_termination_committed=True,
    )
    gateway = ModelGateway(
        {primary.provider_id: primary, fallback.provider_id: fallback},
        environment=resolver.environment,
        registry=ProviderRegistry((primary_record, fallback_record)),
        safety_runtime=SafetyRuntime(),
        budget_runtime=resolver.gateway.budget_runtime,
    )
    primary_profile = replace(
        resolver.router.profile(primary.provider_id),
        estimated_input_cost_microusd_per_1k_tokens=1,
    )
    fallback_profile = replace(
        primary_profile,
        provider_id=fallback.provider_id,
        vendor="internal-contract-fallback",
        model="fake-production-fallback",
        estimated_input_cost_microusd_per_1k_tokens=2,
    )
    active_binding = await resolver.active_release_resolver.resolve(
        environment=resolver.environment,
        use_case=scope.purpose,
        data_class=scope.data_class.value,
    )
    async with resolver.session_factory() as session:
        primary_bundle = await SqlAlchemyFamilyExperienceReleaseBundleStore(session).get(
            active_binding.release_set.bundle_ids[0]
        )
    assert primary_bundle is not None
    fallback_bundle = replace(
        primary_bundle,
        bundle_id="f" * 64,
        candidate_id="candidate:fake-production-fallback",
        provider_id=fallback.provider_id,
        model=fallback_profile.model,
        model_version=fallback_profile.model_version,
    )
    failover_router = MultimodalRouter((primary_profile, fallback_profile))
    failover_release_set = build_family_experience_release_set(
        bundles=(primary_bundle, fallback_bundle),
        router=failover_router,
        budget_runtime=gateway.budget_runtime,
        safety_runtime=gateway.safety_runtime,
    )
    async with resolver.session_factory() as session, session.begin():
        await SqlAlchemyFamilyExperienceReleaseBundleStore(session).append(fallback_bundle)
        await SqlAlchemyFamilyExperienceReleaseSetStore(session).append(
            failover_release_set
        )
        await SqlAlchemyReleaseSetDeploymentStore(session).append(
            _active_release_receipt(failover_release_set, "failover")
        )
    failover_resolver = replace(
        resolver,
        gateway=gateway,
        router=failover_router,
    )
    primary._fail_with = "PROVIDER_5XX"  # type: ignore[assignment]
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_multimodal_draft_runtime_resolver] = (
        lambda: failover_resolver
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/families/{scope.family_id}/experience/multimodal/drafts",
            json=_body("run-production-failover"),
            headers={"Idempotency-Key": "production-failover-1"},
        )

    async with resolver.session_factory() as session:
        attempts = await SqlAlchemyAttemptSink(session).list_attempts(
            request_id="run-production-failover"
        )
    assert response.status_code == 200, response.text
    assert response.json()["route"]["provider_id"] == primary.provider_id
    assert response.json()["provenance"]["provider_id"] == fallback.provider_id
    assert response.json()["requires_human_confirmation"] is True
    assert [(item.provider_id, item.route_sequence, item.status) for item in attempts] == [
        (primary.provider_id, 0, "FAILURE"),
        (fallback.provider_id, 1, "SUCCESS"),
    ]


@pytest.mark.asyncio
async def test_production_path_fails_closed_without_active_release(
    production_runtime,
) -> None:
    resolver, provider, scope = production_runtime

    class MissingDurableReleaseResolver:
        durability_mode = "DURABLE"

        async def resolve(self, **_kwargs):  # type: ignore[no-untyped-def]
            raise ValueError("ACTIVE_RELEASE_SET_NOT_FOUND")

    inactive = replace(
        resolver,
        active_release_resolver=MissingDurableReleaseResolver(),
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_multimodal_draft_runtime_resolver] = lambda: inactive
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/families/{scope.family_id}/experience/multimodal/drafts",
            json=_body("run-no-active-release"),
            headers={"Idempotency-Key": "no-active-release"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "multimodal_experience_runtime_unavailable"
    assert provider.invocations == []


@pytest.mark.asyncio
async def test_production_resolver_rejects_in_memory_active_release_source(
    production_runtime,
) -> None:
    resolver, _provider, scope = production_runtime

    binding = await resolver.active_release_resolver.resolve(
        environment=resolver.environment,
        use_case=scope.purpose,
        data_class=scope.data_class.value,
    )
    with pytest.raises(ValueError, match="active_release_resolver must be durable"):
        replace(
            resolver,
            active_release_resolver=StaticActiveFamilyExperienceReleaseResolver(binding),
        )


@pytest.mark.asyncio
async def test_release_change_between_resolution_and_generation_blocks_external_call(
    production_runtime,
) -> None:
    resolver, provider, scope = production_runtime
    initial = await resolver.active_release_resolver.resolve(
        environment=resolver.environment,
        use_case=scope.purpose,
        data_class=scope.data_class.value,
    )
    changed = ActiveFamilyExperienceRuntimeBinding(
        initial.release_set,
        replace(
            initial.deployment_receipt,
            sequence=initial.deployment_receipt.sequence + 1,
            receipt_id="receipt:changed-during-request",
        ),
    )

    class ChangingDurableResolver:
        durability_mode = "DURABLE"

        def __init__(self) -> None:
            self.calls = 0

        async def resolve(self, **_kwargs):  # type: ignore[no-untyped-def]
            self.calls += 1
            return initial if self.calls == 1 else changed

    changing = replace(
        resolver,
        active_release_resolver=ChangingDurableResolver(),
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_multimodal_draft_runtime_resolver] = lambda: changing
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/families/{scope.family_id}/experience/multimodal/drafts",
            json=_body("run-release-changed"),
            headers={"Idempotency-Key": "release-changed"},
        )

    assert response.status_code == 422
    assert "ACTIVE_RELEASE_CHANGED_DURING_REQUEST" in response.text
    assert provider.invocations == []


@pytest.mark.asyncio
async def test_provider_failure_releases_preflight_for_same_key_retry(
    production_runtime,
) -> None:
    resolver, provider, scope = production_runtime
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_multimodal_draft_runtime_resolver] = lambda: resolver
    provider._fail_with = "NETWORK_ERROR"  # type: ignore[assignment]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        failed = await client.post(
            f"/families/{scope.family_id}/experience/multimodal/drafts",
            json=_body("run-production-retry"),
            headers={"Idempotency-Key": "production-retry-1"},
        )
        provider._fail_with = None
        retried = await client.post(
            f"/families/{scope.family_id}/experience/multimodal/drafts",
            json=_body("run-production-retry"),
            headers={"Idempotency-Key": "production-retry-1"},
        )

    assert failed.status_code == 503, failed.text
    assert retried.status_code == 200, retried.text
    assert retried.json()["draft_id"] == "draft:run-production-retry"
    assert len(provider.invocations) == 2


@pytest.mark.asyncio
async def test_scope_mismatch_is_forbidden_before_gateway_invocation(production_runtime) -> None:
    resolver, provider, scope = production_runtime
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_multimodal_draft_runtime_resolver] = lambda: replace(
        resolver,
        scope_resolver=lambda _: scope,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/families/another-family/experience/multimodal/drafts",
            json=_body("run-production-scope-mismatch"),
            headers={"Idempotency-Key": "production-scope-mismatch"},
        )

    assert response.status_code == 403
    assert len(provider.invocations) == 0


def test_production_resolver_rejects_gateway_without_safety_runtime(production_runtime) -> None:
    resolver, provider, _scope = production_runtime
    unsafe_gateway = ModelGateway(
        {provider.provider_id: provider},
        environment=resolver.environment,
        registry=resolver.gateway.registry,
    )

    with pytest.raises(ValueError, match="requires SafetyRuntime"):
        ProductionExperienceRuntimeResolver(
            scope_resolver=resolver.scope_resolver,
            session_factory=resolver.session_factory,
            gateway=unsafe_gateway,
            router=resolver.router,
            context_broker=resolver.context_broker,
            environment=resolver.environment,
        )


def test_production_resolver_rejects_missing_durable_attempt_sink(production_runtime) -> None:
    resolver, _provider, _scope = production_runtime

    with pytest.raises(ValueError, match="durable attempt_sink_factory"):
        ProductionExperienceRuntimeResolver(
            scope_resolver=resolver.scope_resolver,
            session_factory=resolver.session_factory,
            gateway=resolver.gateway,
            router=resolver.router,
            context_broker=resolver.context_broker,
            environment=resolver.environment,
        )


def test_production_resolver_rejects_route_catalog_without_gateway_adapter(
    production_runtime,
) -> None:
    resolver, _provider, _scope = production_runtime
    profile = replace(
        resolver.router.profile(resolver.router.provider_ids[0]), provider_id="not-wired"
    )
    with pytest.raises(ValueError, match="has no Model Gateway adapter"):
        ProductionExperienceRuntimeResolver(
            scope_resolver=resolver.scope_resolver,
            session_factory=resolver.session_factory,
            gateway=resolver.gateway,
            router=MultimodalRouter((profile,)),
            context_broker=resolver.context_broker,
            environment=resolver.environment,
            attempt_sink_factory=resolver.attempt_sink_factory,
            safety_sink_factory=resolver.safety_sink_factory,
            telemetry_sink_factory=resolver.telemetry_sink_factory,
        )


def test_production_resolver_rejects_route_registry_model_drift(production_runtime) -> None:
    resolver, _provider, _scope = production_runtime
    profile = replace(
        resolver.router.profile(resolver.router.provider_ids[0]),
        model="different-model",
    )
    with pytest.raises(ValueError, match="model identity differs"):
        ProductionExperienceRuntimeResolver(
            scope_resolver=resolver.scope_resolver,
            session_factory=resolver.session_factory,
            gateway=resolver.gateway,
            router=MultimodalRouter((profile,)),
            context_broker=resolver.context_broker,
            environment=resolver.environment,
            attempt_sink_factory=resolver.attempt_sink_factory,
            safety_sink_factory=resolver.safety_sink_factory,
            telemetry_sink_factory=resolver.telemetry_sink_factory,
        )


def test_production_resolver_rejects_route_modality_overclaim(production_runtime) -> None:
    resolver, provider, _scope = production_runtime
    provider.supported_modalities = frozenset({"TEXT", "IMAGE"})
    profile = replace(
        resolver.router.profile(resolver.router.provider_ids[0]),
        modalities=frozenset({"TEXT", "AUDIO"}),
    )
    with pytest.raises(ValueError, match="unsupported modalities"):
        ProductionExperienceRuntimeResolver(
            scope_resolver=resolver.scope_resolver,
            session_factory=resolver.session_factory,
            gateway=resolver.gateway,
            router=MultimodalRouter((profile,)),
            context_broker=resolver.context_broker,
            environment=resolver.environment,
            attempt_sink_factory=resolver.attempt_sink_factory,
            safety_sink_factory=resolver.safety_sink_factory,
            telemetry_sink_factory=resolver.telemetry_sink_factory,
        )


@pytest.mark.asyncio
async def test_sql_experience_http_wiring_resolves_request_auth_before_database_query(
    production_runtime,
) -> None:
    resolver, _provider, scope = production_runtime
    app = FastAPI()
    app.include_router(router)
    engine = resolver.session_factory.kw["bind"]
    install_sql_experience_runtime_wiring(
        app,
        engine=engine,
        session_factory=resolver.session_factory,
        gateway=resolver.gateway,
        router=resolver.router,
        context_broker=resolver.context_broker,
        environment=resolver.environment,
        attempt_sink_factory=resolver.attempt_sink_factory,
        safety_sink_factory=resolver.safety_sink_factory,
        telemetry_sink_factory=resolver.telemetry_sink_factory,
        contract_binding=resolver.contract_binding,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/families/{scope.family_id}/experience/multimodal/drafts",
            json=_body("run-http-wiring-auth"),
            headers={"Idempotency-Key": "http-wiring-auth"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication_required"


@pytest.mark.asyncio
async def test_sql_experience_http_wiring_can_build_durable_context_broker_from_factory(
    production_runtime,
) -> None:
    resolver, _provider, scope = production_runtime
    app = FastAPI()
    app.include_router(router)
    engine = resolver.session_factory.kw["bind"]
    install_sql_experience_runtime_wiring(
        app,
        engine=engine,
        session_factory=resolver.session_factory,
        gateway=resolver.gateway,
        router=resolver.router,
        environment=resolver.environment,
        attempt_sink_factory=resolver.attempt_sink_factory,
        safety_sink_factory=resolver.safety_sink_factory,
        telemetry_sink_factory=resolver.telemetry_sink_factory,
        contract_binding=resolver.contract_binding,
        context_broker_factory=SqlContextBrokerFactory(resolver.session_factory),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/families/{scope.family_id}/experience/multimodal/drafts",
            json=_body("run-http-wiring-factory"),
            headers={"Idempotency-Key": "http-wiring-factory"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication_required"


def test_sql_experience_http_wiring_rejects_ambiguous_context_broker_sources(
    production_runtime,
) -> None:
    resolver, _provider, _scope = production_runtime
    with pytest.raises(ValueError, match="either context_broker"):
        install_sql_experience_runtime_wiring(
            FastAPI(),
            engine=resolver.session_factory.kw["bind"],
            session_factory=resolver.session_factory,
            gateway=resolver.gateway,
            router=resolver.router,
            context_broker=resolver.context_broker,
            context_broker_factory=SqlContextBrokerFactory(resolver.session_factory),
            environment=resolver.environment,
            attempt_sink_factory=resolver.attempt_sink_factory,
            safety_sink_factory=resolver.safety_sink_factory,
            telemetry_sink_factory=resolver.telemetry_sink_factory,
        )


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


def test_production_resolver_rejects_missing_contract_binding(production_runtime) -> None:
    resolver, _provider, _scope = production_runtime

    with pytest.raises(ValueError, match="requires a published contract_binding"):
        replace(resolver, contract_binding=None)


def test_sql_experience_wiring_rejects_missing_contract_binding(production_runtime) -> None:
    resolver, _provider, _scope = production_runtime

    with pytest.raises(ValueError, match="requires a published contract_binding"):
        install_sql_experience_runtime_wiring(
            FastAPI(),
            engine=resolver.session_factory.kw["bind"],
            session_factory=resolver.session_factory,
            gateway=resolver.gateway,
            router=resolver.router,
            context_broker=resolver.context_broker,
            environment=resolver.environment,
            attempt_sink_factory=resolver.attempt_sink_factory,
            safety_sink_factory=resolver.safety_sink_factory,
            telemetry_sink_factory=resolver.telemetry_sink_factory,
        )


@pytest.mark.asyncio
async def test_production_resolver_rejects_in_memory_context_broker(production_runtime) -> None:
    resolver, _, _ = production_runtime
    with pytest.raises(ValueError, match="durable ContextBroker"):
        replace(resolver, context_broker=ContextBroker()).__post_init__()
