"""Composition root for the Course Content HTTP dependency seam.

Mirrors ``backend/domains/family_need/infrastructure/wiring.py``: dev/test
installs the in-memory repository (unchanged, owned by
``apps/family_api/dev_wiring.py``); this module only adds the production
branch — a PostgreSQL-backed repository, installed only when an explicit
PostgreSQL URL exists.

The Human Gate dependency (``configure_course_content_gate``) is out of
scope here: no PostgreSQL-backed Human Gate adapter exists yet anywhere in
this repository (`InMemoryHumanGate` is the only implementation), so this
module does not attempt to wire one. `install_course_content_production_wiring`
installs only the repository; the gate keeps its existing 503 fail-closed
default in production, same posture `install_family_need_production_wiring`
documents for its own missing policy adapter.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from ..api.course_routes import configure_course_content_repository
from .course_content_postgres_repository import SqlAlchemyCourseContentRepository


class _ConnectionScopedCourseContentRepository:
    """Opens one connection per call, mirroring the module-singleton shape
    `configure_course_content_repository` expects (a single object with
    `save_course_content`/`load_course_content`/`list_published_course_content`),
    while still giving each request its own transaction — the same
    per-call-connection approach used where no request-scoped session
    middleware exists yet for this domain.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def save_course_content(self, course) -> None:  # noqa: ANN001
        async with self._engine.begin() as connection:
            await SqlAlchemyCourseContentRepository(connection).save_course_content(course)

    async def load_course_content(self, course_id: str, tenant_scope: str):
        async with self._engine.begin() as connection:
            return await SqlAlchemyCourseContentRepository(connection).load_course_content(
                course_id, tenant_scope
            )

    async def list_published_course_content(self, tenant_scope: str):
        async with self._engine.begin() as connection:
            return await SqlAlchemyCourseContentRepository(
                connection
            ).list_published_course_content(tenant_scope)


def install_course_content_production_wiring(*, engine: AsyncEngine) -> None:
    """Install a PostgreSQL-backed `CourseContent` repository.

    Does not touch the Human Gate wiring — see module docstring.
    """

    configure_course_content_repository(_ConnectionScopedCourseContentRepository(engine))


__all__ = [
    "install_course_content_production_wiring",
]
