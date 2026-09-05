from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.domains.product_intelligence.domain.entities import (
    EducationProductSpec,
    ProductDefinition,
)
from backend.domains.product_intelligence.infrastructure.sqlalchemy_models import (
    Base,
    ProductDefinitionRow,
)
from backend.domains.product_intelligence.infrastructure.sqlalchemy_repository import (
    SqlAlchemyProductIntelligenceRepository,
)


def test_product_definition_orm_carries_education_design_and_provenance_fields() -> None:
    names = {column.name for column in ProductDefinitionRow.__table__.columns}
    assert {
        "product_kind",
        "duration_days",
        "zone",
        "primary_contradiction",
        "demand_ref",
        "market_insight_refs",
        "education_spec",
        "generated_by",
        "model_ref",
        "prompt_use_case_version",
        "confidence",
    } <= names


def test_product_definition_revision_follows_operations_audit() -> None:
    path = Path("database/migrations/versions/0038_product_definition_education_fields.py")
    spec = importlib.util.spec_from_file_location("product_definition_revision", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "0038_product_definition"
    assert module.down_revision == "0037_ops_audit"


@pytest.mark.asyncio
async def test_sqlalchemy_repository_round_trips_education_definition() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        sqlalchemy_repo = SqlAlchemyProductIntelligenceRepository(session)
        now = datetime.now(UTC)
        spec = EducationProductSpec(
            product_kind="MICRO_CAMP",
            duration_days=21,
            zone="ADVANTAGE",
            primary_contradiction="理解与行动之间存在断点",
            component_ids=["component:understand"],
            skill_ids=["skill:coach"],
            success_metric_ids=["metric:adoption"],
            guardrail_ids=["guardrail:consent"],
            stop_conditions=["stop:safety"],
            pause_policy="家长可随时暂停",
            human_gate_policy="敏感建议需人工复核",
        )
        definition = ProductDefinition(
            id="definition:schema-test",
            created_at=now,
            updated_at=now,
            created_by="human:pm",
            tenant_scope="tenant-a",
            concept_id="concept:one",
            component_ids=["component:understand"],
            product_kind="MICRO_CAMP",
            duration_days=21,
            zone="ADVANTAGE",
            primary_contradiction="理解与行动之间存在断点",
            demand_ref="demand:one",
            market_insight_refs=["insight:one"],
            education_spec=spec,
        )
        await sqlalchemy_repo.save_product_definition(definition)
        await sqlalchemy_repo._session.commit()
        loaded = await sqlalchemy_repo._session.get(ProductDefinitionRow, definition.id)
        assert loaded is not None
        assert loaded.product_kind == "MICRO_CAMP"
        assert loaded.education_spec["duration_days"] == 21
        assert loaded.market_insight_refs == ["insight:one"]
    await engine.dispose()
