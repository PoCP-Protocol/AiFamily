"""Composition root for the FamilyExperienceSignal HTTP dependency seam.

Mirrors ``improvement_candidate_wiring.py``: dev/test installs the in-memory
repository (owned by ``apps/family_api/dev_wiring.py``); this module adds the
production branch — a PostgreSQL-backed repository, installed only when an
explicit PostgreSQL URL exists.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from ..api.family_experience_signal_routes import configure_family_experience_signal_repository
from .family_experience_signal_postgres_repository import SqlAlchemyFamilyExperienceSignalRepository


class _ConnectionScopedFamilyExperienceSignalRepository:
    """Opens one connection per call, mirroring the module-singleton shape
    `configure_family_experience_signal_repository` expects, while still
    giving each request its own transaction — same approach as
    `improvement_candidate_wiring._ConnectionScopedImprovementCandidateRepository`.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def save_family_experience_signal(self, signal) -> None:  # noqa: ANN001
        async with self._engine.begin() as connection:
            await SqlAlchemyFamilyExperienceSignalRepository(
                connection
            ).save_family_experience_signal(signal)

    async def list_family_experience_signals(self):
        async with self._engine.begin() as connection:
            return await SqlAlchemyFamilyExperienceSignalRepository(
                connection
            ).list_family_experience_signals()

    async def summarize_by_component(self, *, category):
        async with self._engine.begin() as connection:
            return await SqlAlchemyFamilyExperienceSignalRepository(
                connection
            ).summarize_by_component(category=category)


def install_family_experience_signal_production_wiring(*, engine: AsyncEngine) -> None:
    """Install a PostgreSQL-backed `FamilyExperienceSignal` repository."""

    configure_family_experience_signal_repository(
        _ConnectionScopedFamilyExperienceSignalRepository(engine)
    )


__all__ = ["install_family_experience_signal_production_wiring"]
