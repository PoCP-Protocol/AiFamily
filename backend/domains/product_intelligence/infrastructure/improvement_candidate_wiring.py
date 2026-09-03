"""Composition root for the ImprovementCandidate HTTP dependency seam.

Mirrors ``course_content_wiring.py``: dev/test installs the in-memory
repository (owned by ``apps/family_api/dev_wiring.py``); this module adds the
production branch — a PostgreSQL-backed repository, installed only when an
explicit PostgreSQL URL exists.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from ..api.improvement_candidate_routes import configure_improvement_candidate_repository
from .improvement_candidate_postgres_repository import SqlAlchemyImprovementCandidateRepository


class _ConnectionScopedImprovementCandidateRepository:
    """Opens one connection per call, mirroring the module-singleton shape
    `configure_improvement_candidate_repository` expects, while still giving
    each request its own transaction — same approach as
    `course_content_wiring._ConnectionScopedCourseContentRepository`.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def save_improvement_candidate(self, candidate) -> None:  # noqa: ANN001
        async with self._engine.begin() as connection:
            await SqlAlchemyImprovementCandidateRepository(connection).save_improvement_candidate(
                candidate
            )

    async def list_improvement_candidates(self):
        async with self._engine.begin() as connection:
            return await SqlAlchemyImprovementCandidateRepository(
                connection
            ).list_improvement_candidates()


def install_improvement_candidate_production_wiring(*, engine: AsyncEngine) -> None:
    """Install a PostgreSQL-backed `ImprovementCandidate` repository."""

    configure_improvement_candidate_repository(
        _ConnectionScopedImprovementCandidateRepository(engine)
    )


__all__ = ["install_improvement_candidate_production_wiring"]
