"""FastAPI application factory for the family_api process.

Wave 1 scope: a runnable app with `/health` and `/ready`. No domain routers
are mounted yet — those arrive with Batch 1 (Assessment) per
governance/MIGRATION_PLAN_V2.md section 4.
"""

from __future__ import annotations

from fastapi import FastAPI

from backend.apps.family_api.routes import router
from backend.domains.assessment.api import (
    register_exception_handlers as register_assessment_exception_handlers,
)
from backend.domains.assessment.api import router as assessment_router
from backend.domains.assessment.api.dev_auth import router as dev_auth_router
from backend.domains.membership.api.routes import router as membership_router
from backend.domains.service.api.routes import router as service_router


def create_app() -> FastAPI:
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
    # Dev-only session issuance. Mounted without a prefix because the mobile
    # client calls `/auth/*` at the root. These four endpoints are the only way
    # the app obtains a bearer token, so every one of the 34 UI screens depends
    # on them — they were dropped by the four-layer refactor and restored here.
    # Their placement in the assessment domain is a recorded architectural debt,
    # not a design choice: see ADR-0010.
    application.include_router(dev_auth_router)
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
    return application


app = create_app()
