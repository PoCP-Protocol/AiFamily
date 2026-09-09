"""Contract tests for the single production AI composition root."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.apps.family_api.assessment_ai_wiring import AssessmentAiAssets
from backend.apps.family_api.growth_plan_ai_wiring import GrowthPlanAiAssets
from backend.apps.family_api.main import create_app
from backend.apps.family_api.production_ai_platform_wiring import (
    ProductionAiPlatformWiring,
    build_production_ai_platform_wiring,
)
from backend.intelligence.context_engine.sql_store import AsyncSqlContextBroker
from backend.intelligence.model_gateway.attempt_persistence import SqlAlchemyAttemptSink
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import ProviderRecord, ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.intelligence.observability import SqlAlchemyTelemetrySink
from backend.intelligence.prompt_registry.contracts import PromptBundle
from backend.intelligence.prompt_registry.registry import PromptRegistry
from backend.intelligence.safety.persistence import SqlAlchemySafetyDecisionSink
from backend.intelligence.safety.runtime import SafetyRuntime
from backend.intelligence.schema_registry.contracts import SchemaDefinition
from backend.intelligence.schema_registry.registry import SchemaRegistry


def _wiring():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    return engine, ProductionAiPlatformWiring(
        engine=engine,
        session_factory=sessions,
        assessment_identity_resolver=lambda *_args: None,
        assessment_composition_resolver=lambda *_args: None,
        growth_plan_composition_resolver=lambda *_args: None,
        clock=lambda: datetime.now(UTC),
    )


def test_single_entry_point_mounts_the_complete_ai_surface() -> None:
    engine, wiring = _wiring()
    try:
        app = FastAPI()
        wiring.install(app)
        assert (
            "/families/{family_id}/growth/onboardings/{onboarding_id}/ai-plan-drafts"
            in app.openapi()["paths"]
        )
        assert (
            "/families/{family_id}/growth/human-tasks/{task_id}/decisions" in app.openapi()["paths"]
        )
    finally:
        import asyncio

        asyncio.run(engine.dispose())


def test_create_app_rejects_mixed_ai_composition_hooks() -> None:
    engine, wiring = _wiring()
    try:
        with pytest.raises(ValueError, match="cannot be combined"):
            create_app(
                production_ai_platform_wiring=wiring,
                assessment_production_ai_wiring=lambda _app: None,
            )
    finally:
        import asyncio

        asyncio.run(engine.dispose())


def test_builder_requires_governed_runtime_and_builds_both_resolvers() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    provider = FakeProvider(provider_id="approved-test-provider")
    registry = ProviderRegistry(
        (
            ProviderRecord(
                provider_id=provider.provider_id,
                vendor="aifamily-test",
                model="fake",
                model_version="1",
                status="INTERNAL_APPROVED",
                approved_environments=("staging",),
                sub_delegates=False,
                minor_data_allowed=True,
                security_assessment_ref="test",
                processing_agreement_ref="test",
                deletion_on_termination_committed=True,
            ),
        )
    )
    gateway = ModelGateway(
        {provider.provider_id: provider},
        environment="test",
        registry=registry,
        safety_runtime=SafetyRuntime(),
    )
    prompt = PromptBundle(
        prompt_ref="p",
        version="1",
        use_case="assessment_interpretation",
        agent_id="parent_advisor",
        template="draft",
        system_policy_ref="safety",
        knowledge_refs=(),
        input_contract_ref="input",
        output_schema_ref="s",
        safety_policy_version="1",
        locale="zh-CN",
        author="test",
        reviewer="test",
        status="PUBLISHED",
        effective_at=datetime.now(UTC),
    )
    schema = SchemaDefinition(
        schema_ref="s",
        version="1",
        use_case="assessment_interpretation",
        agent_id="parent_advisor",
        object_type="Draft",
        json_schema={"type": "object"},
        status="PUBLISHED",
        effective_at=datetime.now(UTC),
        reviewer="test",
    )
    try:
        wiring = build_production_ai_platform_wiring(
            engine=engine,
            session_factory=sessions,
            gateway=gateway,
            provider_id=provider.provider_id,
            registry_path="governance/AI_USE_CASE_REGISTRY.yaml",
            context_broker=AsyncSqlContextBroker(sessions),
            assessment_assets=AssessmentAiAssets(
                prompt_ref="p",
                prompt_version="1",
                schema_ref="s",
                schema_version="1",
                reviewed_construct_refs=frozenset({"PARENT_CHILD_COMMUNICATION"}),
            ),
            growth_plan_assets=GrowthPlanAiAssets(
                prompt_ref="gp",
                prompt_version="1",
                schema_ref="gps",
                schema_version="1",
                journey_template_ref="family-growth-90d",
                journey_template_version="1",
                release_set_ref="release",
                runtime_config_digest="digest",
            ),
            attempt_sink_factory=SqlAlchemyAttemptSink,
            safety_sink_factory=SqlAlchemySafetyDecisionSink,
            telemetry_sink_factory=SqlAlchemyTelemetrySink,
            environment="staging",
            clock=lambda: datetime.now(UTC),
            prompt_registry=PromptRegistry(bundles=(prompt,)),
            schema_registry=SchemaRegistry(definitions=(schema,)),
        )
        assert isinstance(wiring, ProductionAiPlatformWiring)
        assert callable(wiring.assessment_composition_resolver)
        assert callable(wiring.growth_plan_composition_resolver)
    finally:
        import asyncio

        asyncio.run(engine.dispose())


def test_platform_wiring_can_own_the_vertical_composition() -> None:
    engine, wiring = _wiring()
    try:
        assert wiring.vertical_family_growth_composition is None
        app = FastAPI()
        wiring.install(app)
        assert not hasattr(app.state, "vertical_family_growth_runtime")
    finally:
        import asyncio

        asyncio.run(engine.dispose())


def test_create_app_rejects_a_second_vertical_composition_root() -> None:
    engine, wiring = _wiring()
    try:
        with pytest.raises(ValueError, match="owns vertical family-growth"):
            create_app(
                production_ai_platform_wiring=wiring,
                production_vertical_family_growth_composition=object(),  # type: ignore[arg-type]
            )
    finally:
        import asyncio

        asyncio.run(engine.dispose())
