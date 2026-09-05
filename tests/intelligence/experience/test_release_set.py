from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.experience.multimodal_routing import (
    MultimodalRouter,
    ProviderCapabilityProfile,
)
from backend.intelligence.experience.release_bundle import FamilyExperienceReleaseBundle
from backend.intelligence.experience.release_set import (
    FamilyExperienceReleaseSetError,
    build_family_experience_release_set,
    validate_release_set_runtime,
)
from backend.intelligence.experience.release_set_persistence import (
    FamilyExperienceReleaseSetBase,
    SessionPerCallFamilyExperienceReleaseSetReader,
    SqlAlchemyFamilyExperienceReleaseSetStore,
)
from backend.intelligence.model_gateway.budget import (
    InMemoryModelBudgetStore,
    ModelBudgetPolicy,
    ModelBudgetRuntime,
    ModelRate,
    ModelRateCard,
)
from backend.intelligence.safety.runtime import SafetyRuntime

NOW = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


def _bundle(provider_id: str, model: str, marker: str) -> FamilyExperienceReleaseBundle:
    return FamilyExperienceReleaseBundle(
        bundle_id=marker * 64,
        candidate_id=f"candidate:{provider_id}",
        environment="staging",
        use_case="family_assistant_conversation",
        agent_id="parent_advisor",
        provider_id=provider_id,
        model=model,
        model_version="2026-09",
        prompt_ref="prompt:family",
        prompt_version="prompt.v1",
        schema_ref="schema:family",
        schema_version="schema.v1",
        safety_policy_version="safety.v1",
        routing_policy_version="routing.v1",
        rate_card_version="rates.v1",
        budget_policy_version="budget.v1",
        knowledge_refs=("knowledge:family",),
        data_class="OPERATIONAL_TEXT",
        report_ref=f"benchmark:{provider_id}",
        decision_id=marker * 64,
        control_id=marker.upper() * 64,
        approval_signature_ref=(marker + "s") * 32,
        approval_signature_algorithm="external-kms-v1",
        approved_by="operator:release",
        approved_at=NOW,
        asset_digest="a" * 64,
        human_gate_rule="REVIEW_REQUIRED",
    )


def _profile(provider_id: str, model: str, *, cost: int) -> ProviderCapabilityProfile:
    return ProviderCapabilityProfile(
        provider_id=provider_id,
        vendor=f"vendor:{provider_id}",
        model=model,
        model_version="2026-09",
        modalities=frozenset({"TEXT", "IMAGE"}),
        status="INTERNAL_APPROVED",
        approved_environments=("staging",),
        approved_data_classes=frozenset({"OPERATIONAL_TEXT"}),
        sub_delegates=False,
        supports_structured_output=True,
        estimated_input_cost_microusd_per_1k_tokens=cost,
        estimated_latency_ms_p50=100,
    )


def _runtime(
    *, route_cost: int = 1, request_limit: int = 100
) -> tuple[MultimodalRouter, ModelBudgetRuntime]:
    router = MultimodalRouter(
        (
            _profile("provider-a", "model-a", cost=route_cost),
            _profile("provider-b", "model-b", cost=2),
        ),
        policy_version="routing.v1",
    )
    rate_card = ModelRateCard(
        version="rates.v1",
        rates=(
            ModelRate("provider-a", "model-a", 1, 1),
            ModelRate("provider-b", "model-b", 2, 2),
        ),
        effective_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=1),
    )
    policy = ModelBudgetPolicy(
        version="budget.v1",
        rate_card_version=rate_card.version,
        per_request_limit_microusd=request_limit,
        period_limit_microusd=1_000,
        max_completion_tokens=100,
    )
    return router, ModelBudgetRuntime(
        InMemoryModelBudgetStore(),
        rate_card,
        policy,
        environment="staging",
        clock=lambda: NOW,
    )


def test_release_set_atomically_binds_primary_fallback_and_full_config() -> None:
    router, budget = _runtime()
    bundles = (
        _bundle("provider-a", "model-a", "a"),
        _bundle("provider-b", "model-b", "b"),
    )
    release_set = build_family_experience_release_set(
        bundles=bundles,
        router=router,
        budget_runtime=budget,
        safety_runtime=SafetyRuntime(policy_version="safety.v1"),
    )
    replay = build_family_experience_release_set(
        bundles=tuple(reversed(bundles)),
        router=router,
        budget_runtime=budget,
        safety_runtime=SafetyRuntime(policy_version="safety.v1"),
    )
    assert release_set == replay
    assert release_set.provider_ids == router.provider_ids
    assert release_set.route_config_digest == router.configuration_digest
    assert release_set.rate_card_digest == budget.rate_card.configuration_digest
    assert release_set.budget_policy_digest == budget.policy.configuration_digest


def test_release_set_detects_same_version_content_drift_and_partial_fallback() -> None:
    router, budget = _runtime()
    bundles = (
        _bundle("provider-a", "model-a", "a"),
        _bundle("provider-b", "model-b", "b"),
    )
    release_set = build_family_experience_release_set(
        bundles=bundles,
        router=router,
        budget_runtime=budget,
        safety_runtime=SafetyRuntime(policy_version="safety.v1"),
    )
    changed_router, _ = _runtime(route_cost=99)
    with pytest.raises(FamilyExperienceReleaseSetError, match="RUNTIME_CONFIG_DRIFT"):
        validate_release_set_runtime(
            release_set,
            router=changed_router,
            budget_runtime=budget,
            safety_runtime=SafetyRuntime(policy_version="safety.v1"),
        )
    _, changed_budget = _runtime(request_limit=101)
    with pytest.raises(FamilyExperienceReleaseSetError, match="RUNTIME_CONFIG_DRIFT"):
        validate_release_set_runtime(
            release_set,
            router=router,
            budget_runtime=changed_budget,
            safety_runtime=SafetyRuntime(policy_version="safety.v1"),
        )
    with pytest.raises(FamilyExperienceReleaseSetError, match="ROUTE_CATALOG_MISMATCH"):
        build_family_experience_release_set(
            bundles=(bundles[0],),
            router=router,
            budget_runtime=budget,
            safety_runtime=SafetyRuntime(policy_version="safety.v1"),
        )


@pytest.mark.asyncio
async def test_release_set_sql_round_trip_is_immutable() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(FamilyExperienceReleaseSetBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    router, budget = _runtime()
    release_set = build_family_experience_release_set(
        bundles=(
            _bundle("provider-a", "model-a", "a"),
            _bundle("provider-b", "model-b", "b"),
        ),
        router=router,
        budget_runtime=budget,
        safety_runtime=SafetyRuntime(policy_version="safety.v1"),
    )
    async with session_factory() as session, session.begin():
        await SqlAlchemyFamilyExperienceReleaseSetStore(session).append(release_set)
    reader = SessionPerCallFamilyExperienceReleaseSetReader(session_factory)
    assert await reader.get(release_set.release_set_id) == release_set
    async with session_factory() as session, session.begin():
        with pytest.raises(FamilyExperienceReleaseSetError, match="ID_CONFLICT"):
            await SqlAlchemyFamilyExperienceReleaseSetStore(session).append(
                replace(release_set, asset_digest="f" * 64)
            )
    await engine.dispose()
