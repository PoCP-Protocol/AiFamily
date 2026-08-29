"""FastAPI application factory for the family_api process.

Wave 1 scope: a runnable app with `/health` and `/ready`. No domain routers
are mounted yet — those arrive with Batch 1 (Assessment) per
governance/MIGRATION_PLAN_V2.md section 4.
"""

from __future__ import annotations

from fastapi import FastAPI

from backend.apps.family_api.routes import router
from backend.domains.assessment.api import install_state
from backend.domains.membership.api.routes import router as membership_router


def create_app() -> FastAPI:
    application = FastAPI(title="AiFamily family_api", version="0.1.0")
    application.include_router(router)
    install_state(application)
    # Mounting membership does NOT make it callable in production: its
    # get_repository / get_action_context / get_actor_context dependencies raise
    # by design (no session factory, and the Account → TenantMembership → Family
    # binding chain that answers "which family is this caller acting for" is a
    # later capability). So its endpoints fail closed at the dependency rather
    # than fail open by inventing a tenant/family. Mounting buys route
    # registration and OpenAPI visibility, not availability — see
    # governance/DOMAIN_REGISTRY.yaml → membership.known_gaps.
    application.include_router(membership_router)
    return application


app = create_app()
