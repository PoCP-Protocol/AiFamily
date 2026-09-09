"""Single composition-root entry point for the governed family AI surface.

The assessment and growth-plan seams are intentionally implemented in separate
modules because they own different domain contracts.  Deployment must still
install them as one platform, otherwise a process can expose UI-03 without
UI-04 (or the reverse) and silently run with different Context/identity
authorities.  This module is the one application-level installer.

This is wiring only: it never selects a provider, creates credentials, or
installs a synthetic runtime.  A deployment must supply already-admitted
composition resolvers and the same database engine/session factory.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.apps.family_api.production_ai_growth_surface_wiring import (
    install_production_ai_growth_surface,
)
from backend.apps.family_api.production_assessment_http_wiring import (
    CompositionResolver as AssessmentCompositionResolver,
)
from backend.apps.family_api.production_assessment_http_wiring import (
    IdentityResolver as AssessmentIdentityResolver,
)
from backend.apps.family_api.production_assessment_http_wiring import (
    install_production_assessment_http_wiring,
)
from backend.apps.family_api.production_growth_plan_http_wiring import (
    CompositionResolver as GrowthPlanCompositionResolver,
)
from backend.domains.assessment.application.ports import AssessmentRepositoryPort


@dataclass(frozen=True, slots=True)
class ProductionAiPlatformWiring:
    """Validated inputs required to mount the complete family AI platform."""

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    assessment_identity_resolver: AssessmentIdentityResolver
    assessment_composition_resolver: AssessmentCompositionResolver
    growth_plan_composition_resolver: GrowthPlanCompositionResolver
    clock: Callable[[], datetime]
    assessment_repository_factory: Callable[[object], AssessmentRepositoryPort] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.engine, AsyncEngine):
            raise TypeError("production AI platform engine is required")
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("production AI platform session_factory is required")
        if not all(
            callable(value)
            for value in (
                self.assessment_identity_resolver,
                self.assessment_composition_resolver,
                self.growth_plan_composition_resolver,
                self.clock,
            )
        ):
            raise TypeError("production AI platform resolvers and clock must be callable")
        if self.assessment_repository_factory is not None and not callable(
            self.assessment_repository_factory
        ):
            raise TypeError("assessment_repository_factory must be callable")

    def install(self, app: FastAPI) -> None:
        """Mount assessment, plan review, daily action and feedback routes once."""

        if not isinstance(app, FastAPI):
            raise TypeError("app must be a FastAPI instance")
        install_production_assessment_http_wiring(
            app,
            engine=self.engine,
            identity_resolver=self.assessment_identity_resolver,
            composition_resolver=self.assessment_composition_resolver,
            **(
                {"repository_factory": self.assessment_repository_factory}
                if self.assessment_repository_factory is not None
                else {}
            ),
        )
        install_production_ai_growth_surface(
            app,
            engine=self.engine,
            session_factory=self.session_factory,
            growth_plan_composition_resolver=self.growth_plan_composition_resolver,
            clock=self.clock,
        )


__all__ = ["ProductionAiPlatformWiring"]
