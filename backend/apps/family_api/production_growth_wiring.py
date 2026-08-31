"""Request-scoped production composition for Assessment-to-Growth confirmation."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.domains.assessment.api import dependencies as assessment_dependencies
from backend.domains.assessment.application.growth_hypothesis_commands import (
    GrowthHypothesisCommandHandler,
)
from backend.domains.assessment.application.growth_intent_handoff import (
    ViewedUnderstandingSignalReaderPort,
)
from backend.domains.assessment.infrastructure.sqlalchemy_repository import (
    SqlAlchemyAssessmentRepository,
)
from backend.domains.growth.infrastructure.sqlalchemy_growth_intent_confirmation import (
    SqlAlchemyGrowthIntentConfirmationAdapter,
)
from backend.platform.persistence import SqlAlchemyUnitOfWork


class ProductionGrowthConfirmationWiring:
    """Compose the canonical handler on one caller-owned database transaction.

    Identity and the reviewed-signal ledger remain separately owned FastAPI
    dependencies.  This object owns only the transaction boundary: the
    Assessment repository, Growth adapter, Audit, Outbox, and both durable
    receipts all use the same request-scoped ``AsyncSession``.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        viewed_signals: ViewedUnderstandingSignalReaderPort,
    ) -> None:
        self._session_factory = session_factory
        self._viewed_signals = viewed_signals

    async def handler(self) -> AsyncIterator[GrowthHypothesisCommandHandler]:
        async with SqlAlchemyUnitOfWork(self._session_factory) as unit_of_work:
            session = unit_of_work.session
            assert session is not None
            connection = await session.connection()
            yield GrowthHypothesisCommandHandler(
                SqlAlchemyAssessmentRepository(connection),
                self._viewed_signals,
                SqlAlchemyGrowthIntentConfirmationAdapter(session),
            )
            await unit_of_work.commit()

    def install(self, app: FastAPI) -> None:
        """Install only the Growth confirmation dependency on ``app``."""
        app.dependency_overrides[assessment_dependencies.get_growth_hypothesis_handler] = (
            self.handler
        )


__all__ = ["ProductionGrowthConfirmationWiring"]
