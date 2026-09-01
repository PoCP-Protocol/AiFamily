"""FastAPI application factory for the family_api process.

Wave 1 scope: a runnable app with `/health` and `/ready`. No domain routers
are mounted yet — those arrive with Batch 1 (Assessment) per
governance/MIGRATION_PLAN_V2.md section 4.
"""

from __future__ import annotations

from fastapi import FastAPI

from backend.apps.family_api.dev_wiring import install_dev_wiring, is_dev_environment
from backend.apps.family_api.production_growth_wiring import ProductionGrowthConfirmationWiring
from backend.apps.family_api.routes import router
from backend.domains.assessment.api import (
    register_exception_handlers as register_assessment_exception_handlers,
)
from backend.domains.assessment.api import router as assessment_router
from backend.domains.assessment.api.dev_auth import router as dev_auth_router
from backend.domains.membership.api.routes import router as membership_router
from backend.domains.service.api.routes import router as service_router
from backend.intelligence.family_understanding.api import (
    AuthorizedContextResolver,
    create_family_understanding_router,
)
from backend.intelligence.family_understanding.application import FamilyUnderstandingApplication


def create_app(
    *,
    growth_confirmation_wiring: ProductionGrowthConfirmationWiring | None = None,
    family_understanding_application: FamilyUnderstandingApplication | None = None,
    authorized_contexts: AuthorizedContextResolver | None = None,
) -> FastAPI:
    application = FastAPI(title="AiFamily family_api", version="0.1.0")
    application.include_router(router)
    # Assessment carries the only end-to-end usable business chain (UI-02 →
    # UI-03). Its router paths are relative, so the `/families` prefix is
    # supplied here rather than baked into every decorator.
    #
    # `register_exception_handlers` is not optional: without it an
    # AssessmentDomainError surfaces as a 500 instead of the 404/409 the domain
    # intends. Mounting the router alone would look correct until the first
    # not-found.
    application.include_router(assessment_router, prefix="/families")
    register_assessment_exception_handlers(application)
    # Mounting membership does NOT make it callable in production: its
    # get_repository / get_action_context / get_actor_context dependencies raise
    # by design (no session factory, and the Account → TenantMembership → Family
    # binding chain that answers "which family is this caller acting for" is a
    # later capability). So its endpoints fail closed at the dependency rather
    # than fail open by inventing a tenant/family. Mounting buys route
    # registration and OpenAPI visibility, not availability — see
    # governance/DOMAIN_REGISTRY.yaml → membership.known_gaps.
    application.include_router(membership_router)
    # Same fail-closed situation as membership, and for the same reason: the
    # service router's get_repository / get_consent_query / get_action_context /
    # get_actor_context dependencies all raise by design. Mounting registers the
    # six SERVICE endpoints in the OpenAPI schema and makes them testable via
    # `dependency_overrides`; it does not make them available in production, and
    # a caller reaching one without those overrides gets a 500 from the
    # dependency rather than a booking made on behalf of an invented family.
    # See governance/DOMAIN_REGISTRY.yaml → service_booking.known_gaps.
    application.include_router(service_router)
    # In a dev environment, supply the four service dependencies that raise by
    # design, so the six mounted SERVICE endpoints are actually callable instead
    # of returning 500 to every caller. The domain code is untouched and still
    # fails closed — the overrides live on the app object, which is the mechanism
    # `service/api/dependencies.py` names as intended.
    #
    # Outside dev this block does nothing, so a production app keeps exactly the
    # fail-closed behaviour described above. `install_dev_wiring` additionally
    # refuses if called directly outside dev/test: the app decides based on
    # environment, and the function defends itself against being forced.
    #
    # See backend/apps/family_api/dev_wiring.py — it synthesises consent grants
    # and uses an in-memory repository (R5: must never be reachable in production).
    if is_dev_environment():
        # Dev-only session issuance is part of the synthetic wiring boundary,
        # not merely a dependency override. Keeping these routes out of the
        # production OpenAPI prevents process-local tokens from looking like a
        # supported authentication capability when AIFAMILY_ENV is absent,
        # blank, invalid, or explicitly production.
        application.include_router(dev_auth_router)
        install_dev_wiring(application)
    if growth_confirmation_wiring is not None:
        growth_confirmation_wiring.install(application)
    if (family_understanding_application is None) != (authorized_contexts is None):
        raise ValueError(
            "family understanding application and authorized contexts must be configured together"
        )
    if family_understanding_application is not None and authorized_contexts is not None:
        application.include_router(
            create_family_understanding_router(
                family_understanding_application,
                authorized_contexts,
            )
        )
    return application


app = create_app()
