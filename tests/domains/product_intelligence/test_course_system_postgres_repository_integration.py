from __future__ import annotations

import importlib

import pytest

from backend.domains.product_intelligence.domain.course_system import (
    CourseSystem,
    CourseSystemStage,
)
from backend.domains.product_intelligence.domain.errors import ProductIntelligenceNotFoundError
from backend.domains.product_intelligence.infrastructure.course_system_postgres_repository import (
    SqlAlchemyCourseSystemRepository,
)
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url


def _system(tenant_scope: str = "tenant-a") -> CourseSystem:
    return CourseSystem(
        system_id="course-system:family-growth", version=1, tenant_scope=tenant_scope,
        product_package_version_ref="product-package:family-growth@v1",
        stages=tuple(
            CourseSystemStage(
                stage_id=f"S{i}", title=f"阶段{i}", lesson_start=(i - 1) * 4 + 1,
                lesson_end=i * 4, outcome=f"产出{i}"
            ) for i in range(1, 7)
        ),
    )


async def _apply_migration(engine) -> None:
    migration = importlib.import_module(
        "database.migrations.versions.0074_course_system"
    )
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync: _upgrade(sync, migration, MigrationContext, Operations)
        )


def _upgrade(sync, migration, migration_context, operations) -> None:
    context = migration_context.configure(sync, opts={"target_metadata": None})
    with operations.context(context):
        migration.upgrade()


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_course_system_postgres_round_trip_and_tenant_isolation() -> None:
    from sqlalchemy import MetaData

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_migration(engine)
        async with engine.begin() as connection:
            repository = SqlAlchemyCourseSystemRepository(connection)
            system = _system()
            await repository.save_course_system(system)
            loaded = await repository.load_course_system(system.system_id, "tenant-a")
            assert loaded.stages[-1].lesson_end == 24
            with pytest.raises(ProductIntelligenceNotFoundError):
                await repository.load_course_system(system.system_id, "tenant-b")


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_course_system_older_version_cannot_overwrite_newer_version() -> None:
    from sqlalchemy import MetaData

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_migration(engine)
        async with engine.begin() as connection:
            repository = SqlAlchemyCourseSystemRepository(connection)
            current = _system().model_copy(update={"version": 2})
            older = _system().model_copy(
                update={"version": 1, "product_package_version_ref": "package:old@v1"}
            )
            await repository.save_course_system(current)
            await repository.save_course_system(older)
            loaded = await repository.load_course_system(current.system_id, current.tenant_scope)
            assert loaded.version == 2
            assert loaded.product_package_version_ref == current.product_package_version_ref
