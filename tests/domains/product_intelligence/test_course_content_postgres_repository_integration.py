"""Real-Postgres tests for :class:`SqlAlchemyCourseContentRepository`.

Follows the opt-in gated pattern from
``tests/domains/family_need/test_postgres_repository_integration.py``: every
test is skipped unless ``AIFAMILY_TEST_DATABASE_URL`` is set (see
``tests/support/postgres.py``). This module was authored and syntax/type
checked in an environment with no local PostgreSQL/Docker available, so it
has **not** been run against a real database yet — a developer with the
dev-compose Postgres running must execute it once to confirm the migration's
schema and this adapter's SQL agree.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.domains.product_intelligence.domain.course_content import (
    CourseContent,
    CourseLesson,
)
from backend.domains.product_intelligence.domain.errors import (
    ProductIntelligenceNotFoundError,
)
from backend.domains.product_intelligence.infrastructure.course_content_postgres_repository import (
    SqlAlchemyCourseContentRepository,
)
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url


def _course(**overrides) -> CourseContent:
    now = datetime.now(UTC)
    values = {
        "id": "course-1",
        "version": 1,
        "status": "DRAFT",
        "tenant_scope": "tenant-1",
        "created_by": "operator-1",
        "created_at": now,
        "updated_at": now,
        "title": "告别作业磨蹭",
        "problem_statement": "孩子写作业总拖延",
        "assessment_criteria": ("能在约定时间内开始作业",),
        "learning_goal": "建立一个可持续的小行动",
        "lessons": (
            CourseLesson(
                lesson_id="lesson-1",
                sequence=1,
                title="第一课",
                knowledge_point="番茄钟法",
                action_task="今晚试一次十分钟专注",
            ),
        ),
        "review_cadence": "每周复盘一次",
        "outcome_metrics": ("连续三天按时开始作业",),
        "content_accuracy_claim_refs": ("claim-1",),
    }
    values.update(overrides)
    return CourseContent(**values)


async def _apply_course_content_migration(engine) -> None:
    """Replay the 0056 migration's `upgrade()` directly against the
    schema-scoped engine, matching how the family_need integration test
    applies its own migration to a per-test disposable schema.
    """

    import importlib

    course_content_migration = importlib.import_module(
        "database.migrations.versions.0056_course_content"
    )

    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_conn: _run_upgrade(sync_conn, course_content_migration)
        )


def _run_upgrade(sync_connection, migration_module) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    context = MigrationContext.configure(sync_connection, opts={"target_metadata": None})
    with Operations.context(context):
        migration_module.upgrade()


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_save_and_load_course_content_round_trips_through_real_postgres() -> None:
    from sqlalchemy import MetaData

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_course_content_migration(engine)
        async with engine.begin() as connection:
            repository = SqlAlchemyCourseContentRepository(connection)
            course = _course()
            await repository.save_course_content(course)
            loaded = await repository.load_course_content(course.id, course.tenant_scope)
            assert loaded == course


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_load_course_content_raises_not_found_for_wrong_tenant_scope() -> None:
    from sqlalchemy import MetaData

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_course_content_migration(engine)
        async with engine.begin() as connection:
            repository = SqlAlchemyCourseContentRepository(connection)
            course = _course()
            await repository.save_course_content(course)

            with pytest.raises(ProductIntelligenceNotFoundError):
                await repository.load_course_content(course.id, "other-tenant")


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_list_published_course_content_only_returns_published_rows() -> None:
    from sqlalchemy import MetaData

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_course_content_migration(engine)
        async with engine.begin() as connection:
            repository = SqlAlchemyCourseContentRepository(connection)
            draft = _course(id="course-draft")
            published = _course(id="course-published", status="PUBLISHED")
            await repository.save_course_content(draft)
            await repository.save_course_content(published)

            results = await repository.list_published_course_content("tenant-1")
            assert [c.id for c in results] == ["course-published"]


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_save_course_content_upserts_lessons_and_status_on_update() -> None:
    from sqlalchemy import MetaData

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_course_content_migration(engine)
        async with engine.begin() as connection:
            repository = SqlAlchemyCourseContentRepository(connection)
            course = _course()
            await repository.save_course_content(course)

            updated = course.submit_for_review()
            await repository.save_course_content(updated)

            loaded = await repository.load_course_content(course.id, course.tenant_scope)
            assert loaded.status == "UNDER_REVIEW"
            assert loaded.version == 2
