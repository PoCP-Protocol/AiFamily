from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.experience.contract_binding import (
    MultimodalContractBindingError,
    MultimodalContractRegistryBinding,
)
from backend.intelligence.experience.execution_materials import (
    ExecutionMaterialBase,
    SqlAlchemyExecutionMaterialRegistry,
)
from backend.intelligence.experience.sql_contract_binding import (
    build_sql_family_experience_contract_binding,
)
from backend.intelligence.experience.standard_asset_registration import (
    FamilyExperienceAssetRegistrationError,
    register_family_experience_assets,
)
from backend.intelligence.experience.standard_assets import (
    FAMILY_EXPERIENCE_PROMPT_VERSION,
    FAMILY_EXPERIENCE_SCHEMA_VERSION,
    build_family_experience_assets,
)
from backend.intelligence.experience.standard_contracts import (
    FAMILY_EXPERIENCE_AGENT_ID,
    FAMILY_EXPERIENCE_PROMPT_REF,
    FAMILY_EXPERIENCE_SCHEMA_REF,
    FAMILY_EXPERIENCE_USE_CASE,
)
from backend.intelligence.prompt_registry import (
    PromptPersistenceBase,
    SqlAlchemyPromptRegistry,
)
from backend.intelligence.schema_registry import (
    SchemaPersistenceBase,
    SqlAlchemySchemaRegistry,
)


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(PromptPersistenceBase.metadata.create_all)
        await connection.run_sync(SchemaPersistenceBase.metadata.create_all)
        await connection.run_sync(ExecutionMaterialBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sql_registration_commits_and_resolves_as_one_pair(session_factory) -> None:
    assets = build_family_experience_assets(
        status="PUBLISHED",
        reviewer="reviewer-1",
        effective_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    async with session_factory() as session, session.begin():
        registered = await register_family_experience_assets(
            assets=assets,
            prompt_registry=SqlAlchemyPromptRegistry(session),
            schema_registry=SqlAlchemySchemaRegistry(session),
            material_registry=SqlAlchemyExecutionMaterialRegistry(session),
        )

    async with session_factory() as session:
        binding = MultimodalContractRegistryBinding(
            prompt_registry=SqlAlchemyPromptRegistry(session),
            schema_registry=SqlAlchemySchemaRegistry(session),
            agent_id=FAMILY_EXPERIENCE_AGENT_ID,
            prompt_ref=FAMILY_EXPERIENCE_PROMPT_REF,
            schema_ref=FAMILY_EXPERIENCE_SCHEMA_REF,
        )
        resolved = await binding.resolve(
            use_case=FAMILY_EXPERIENCE_USE_CASE,
            prompt_version=FAMILY_EXPERIENCE_PROMPT_VERSION,
            schema_version=FAMILY_EXPERIENCE_SCHEMA_VERSION,
            output_schema=dict(assets.schema.json_schema),
        )

    assert registered.prompt_ref == FAMILY_EXPERIENCE_PROMPT_REF
    assert registered.schema_ref == FAMILY_EXPERIENCE_SCHEMA_REF
    assert resolved.prompt_version == FAMILY_EXPERIENCE_PROMPT_VERSION
    assert resolved.schema_version == FAMILY_EXPERIENCE_SCHEMA_VERSION


@pytest.mark.asyncio
async def test_sql_registration_rejects_duplicate_pair_before_mutation(session_factory) -> None:
    assets = build_family_experience_assets(
        status="PUBLISHED",
        reviewer="reviewer-1",
        effective_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    async with session_factory() as session, session.begin():
        prompt_registry = SqlAlchemyPromptRegistry(session)
        schema_registry = SqlAlchemySchemaRegistry(session)
        await register_family_experience_assets(
            assets=assets,
            prompt_registry=prompt_registry,
            schema_registry=schema_registry,
            material_registry=SqlAlchemyExecutionMaterialRegistry(session),
        )
        with pytest.raises(FamilyExperienceAssetRegistrationError, match="already registered"):
            await register_family_experience_assets(
                assets=assets,
                prompt_registry=prompt_registry,
                schema_registry=schema_registry,
                material_registry=SqlAlchemyExecutionMaterialRegistry(session),
            )


@pytest.mark.asyncio
async def test_session_per_call_sql_binding_resolves_committed_assets(session_factory) -> None:
    assets = build_family_experience_assets(
        status="PUBLISHED",
        reviewer="reviewer-1",
        effective_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    async with session_factory() as session, session.begin():
        await register_family_experience_assets(
            assets=assets,
            prompt_registry=SqlAlchemyPromptRegistry(session),
            schema_registry=SqlAlchemySchemaRegistry(session),
            material_registry=SqlAlchemyExecutionMaterialRegistry(session),
        )

    binding = build_sql_family_experience_contract_binding(
        session_factory=session_factory
    )
    resolved = await binding.resolve(
        use_case=FAMILY_EXPERIENCE_USE_CASE,
        prompt_version=FAMILY_EXPERIENCE_PROMPT_VERSION,
        schema_version=FAMILY_EXPERIENCE_SCHEMA_VERSION,
        output_schema=dict(assets.schema.json_schema),
    )

    assert resolved.prompt_ref == FAMILY_EXPERIENCE_PROMPT_REF
    assert resolved.schema_ref == FAMILY_EXPERIENCE_SCHEMA_REF


@pytest.mark.asyncio
async def test_session_per_call_sql_binding_fails_closed_when_assets_are_missing(
    session_factory,
) -> None:
    binding = build_sql_family_experience_contract_binding(
        session_factory=session_factory
    )
    draft = build_family_experience_assets()

    with pytest.raises(MultimodalContractBindingError, match="PROMPT_OR_SCHEMA_NOT_FOUND"):
        await binding.resolve(
            use_case=FAMILY_EXPERIENCE_USE_CASE,
            prompt_version=FAMILY_EXPERIENCE_PROMPT_VERSION,
            schema_version=FAMILY_EXPERIENCE_SCHEMA_VERSION,
            output_schema=dict(draft.schema.json_schema),
        )
