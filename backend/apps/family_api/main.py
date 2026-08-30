"""FastAPI application factory for the family_api process.

The process exposes health/readiness plus the currently wired vertical slices.
Every domain keeps its production dependency seam fail-closed; development and
test install explicit synthetic adapters without changing routes, state
machines, errors or governance gates.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, status

from backend.apps.family_api.dev_wiring import install_dev_wiring, is_dev_environment

if TYPE_CHECKING:
    from backend.intelligence.experience.api import MultimodalDraftRuntimeResolver

# The experience runtime is an optional composition-root capability.  The
# route remains owned by its domain; this guard only keeps a clean base
# importable while the reviewed provenance foundation is absent.  Do not turn
# an arbitrary import failure into a silent route omission: only the exact
# known missing foundation is accepted here.
try:
    from backend.apps.family_api.experience_wiring import (
        install_experience_runtime_resolver,
        mount_experience_router,
    )
except ModuleNotFoundError as error:
    if error.name != "backend.intelligence.model_gateway.provenance":
        raise
    install_experience_runtime_resolver = None
    mount_experience_router = None
    _EXPERIENCE_IMPORT_ERROR = f"missing dependency: {error.name}"
else:
    _EXPERIENCE_IMPORT_ERROR = None

from backend.apps.family_api.growth_onboarding_wiring import (
    FakeGrowthOnboardingRuntime,
    InMemoryGrowthOnboardingActorResolver,
    build_fake_growth_onboarding_runtime,
    install_growth_onboarding_dev_wiring,
    install_growth_onboarding_production_wiring,
)
from backend.apps.family_api.routes import router
from backend.domains.assessment.api import (
    register_exception_handlers as register_assessment_exception_handlers,
)
from backend.domains.assessment.api import router as assessment_router
from backend.domains.assessment.api.dev_auth import router as dev_auth_router

# Commerce is a future production-shaped capability, not a reason to fake a
# catalogue in this process.  Its package is absent from this clean base, so
# keep the import contract explicit and leave the capability unavailable.
try:
    from backend.domains.commerce.api.routes import router as commerce_router
except ModuleNotFoundError as error:
    if error.name not in {
        "backend.domains.commerce",
        "backend.domains.commerce.api",
        "backend.domains.commerce.api.routes",
    }:
        raise
    commerce_router = None
    _COMMERCE_IMPORT_ERROR = f"missing dependency: {error.name}"
else:
    _COMMERCE_IMPORT_ERROR = None

from backend.domains.family_need.api.routes import (
    register_exception_handlers as register_family_need_exception_handlers,
)
from backend.domains.family_need.api.routes import router as family_need_router
from backend.domains.journey.api.growth_onboarding_routes import (
    router as growth_onboarding_router,
)

# This legacy Journey router is not part of the clean base.  The canonical
# GrowthIntent -> Onboarding router above remains mounted independently; do not
# synthesize a second Journey implementation just to close this import.
try:
    from backend.domains.journey.api.routes import (
        register_exception_handlers as register_journey_exception_handlers,
    )
    from backend.domains.journey.api.routes import router as journey_router
except ModuleNotFoundError as error:
    if error.name != "backend.domains.journey.api.routes":
        raise
    register_journey_exception_handlers = None
    journey_router = None
    _JOURNEY_IMPORT_ERROR = f"missing dependency: {error.name}"
else:
    _JOURNEY_IMPORT_ERROR = None

from backend.domains.membership.api.routes import router as membership_router
from backend.domains.service.api.routes import router as service_router

# FGCN currently shares the same absent provenance foundation as the
# experience runtime.  Keep its production routes unadvertised until that
# reviewed dependency is present; never replace it with a fake/NOOP adapter.
try:
    from backend.domains.service.fgcn.api.dependencies import (
        clear_session_factory as clear_fgcn_session_factory,
    )
    from backend.domains.service.fgcn.api.dependencies import (
        configure_session_factory as configure_fgcn_session_factory,
    )
    from backend.domains.service.fgcn.api.routes import (
        register_exception_handlers as register_fgcn_exception_handlers,
    )
    from backend.domains.service.fgcn.api.routes import router as fgcn_router
except ModuleNotFoundError as error:
    if error.name != "backend.intelligence.model_gateway.provenance":
        raise
    clear_fgcn_session_factory = None
    configure_fgcn_session_factory = None
    register_fgcn_exception_handlers = None
    fgcn_router = None
    _FGCN_IMPORT_ERROR = f"missing dependency: {error.name}"
else:
    _FGCN_IMPORT_ERROR = None

from backend.platform.persistence.session import (
    DATABASE_URL_ENV_VAR,
    get_sessionmaker,
    is_postgres_url,
)


def _runtime_database_url() -> str | None:
    """Return an explicitly configured, driver-ready runtime database URL.

    The persistence module intentionally has a SQLite fallback for local
    kernel tests.  An API process must not use that fallback as an accidental
    production database, so this wiring only accepts an explicit environment
    value.  Bare PostgreSQL URLs are normalized to the async driver that the
    project ships.
    """

    configured = os.environ.get(DATABASE_URL_ENV_VAR, "").strip()
    if not configured:
        return None
    if not is_postgres_url(configured):
        return configured if is_dev_environment() else None
    for bare_prefix in ("postgresql://", "postgres://"):
        if configured.startswith(bare_prefix):
            return "postgresql+asyncpg://" + configured[len(bare_prefix) :]
    return configured


def _configure_fgcn_persistence() -> None:
    """Bind FGCN to the explicit process database, or deliberately unbind it."""

    if (
        clear_fgcn_session_factory is None
        or configure_fgcn_session_factory is None
    ):
        return
    database_url = _runtime_database_url()
    if database_url is None:
        clear_fgcn_session_factory()
        return
    configure_fgcn_session_factory(get_sessionmaker(database_url))


def _mount_growth_onboarding(
    application: FastAPI,
    *,
    runtime: FakeGrowthOnboardingRuntime | None = None,
    actor_resolver: InMemoryGrowthOnboardingActorResolver | None = None,
    database_url: str | None = None,
) -> None:
    """Mount GrowthOnboarding once, selecting only an explicit environment seam.

    Dev/test gets the production-shaped fake installer so tests can provide a
    concrete runtime and actor resolver without changing the route. Production
    gets the PostgreSQL installer only when an explicit PostgreSQL URL exists;
    otherwise the route is still discoverable but retains its 503 defaults.
    This keeps an absent production dependency fail-closed without silently
    installing synthetic adapters.
    """

    if is_dev_environment():
        install_growth_onboarding_dev_wiring(
            application,
            runtime=runtime or build_fake_growth_onboarding_runtime(),
            actor_resolver=actor_resolver or InMemoryGrowthOnboardingActorResolver(),
        )
        return

    configured_url = database_url or _runtime_database_url()
    if configured_url is not None and is_postgres_url(configured_url):
        install_growth_onboarding_production_wiring(
            application,
            database_url=configured_url,
        )
        return

    # Keep the endpoint in OpenAPI while leaving both trusted dependencies at
    # their explicit 503 fail-closed implementations.
    application.include_router(growth_onboarding_router)


def _record_dependency_status(application: FastAPI) -> None:
    """Expose composition gaps without advertising unavailable endpoints.

    ``app.state`` is intentionally operational metadata, not a fallback data
    source.  A missing optional dependency therefore remains observable and
    fail-closed: no synthetic route, repository, or NOOP implementation is
    installed to make the process look healthy.
    """

    application.state.composition_dependencies = {
        "commerce": {
            "available": commerce_router is not None,
            "failure_mode": "fail_closed",
            "reason": _COMMERCE_IMPORT_ERROR,
        },
        "experience": {
            "available": mount_experience_router is not None,
            "failure_mode": "fail_closed",
            "reason": _EXPERIENCE_IMPORT_ERROR,
        },
        "fgcn": {
            "available": fgcn_router is not None,
            "failure_mode": "fail_closed",
            "reason": _FGCN_IMPORT_ERROR,
        },
        "journey_legacy": {
            "available": journey_router is not None,
            "failure_mode": "fail_closed",
            "reason": _JOURNEY_IMPORT_ERROR,
        },
    }

    async def capability_readiness(capability_name: str) -> dict[str, str]:
        """Return an explicit readiness result for an optional capability.

        This is a composition-root health seam, not a substitute API for the
        missing domain.  In particular, it must never return synthetic data
        or a successful NOOP when the capability's reviewed dependency is not
        in the checkout.
        """

        capability = application.state.composition_dependencies.get(capability_name)
        if capability is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="capability_not_found",
            )
        if not capability["available"]:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="capability_unavailable",
            )
        return {"status": "ready"}

    application.add_api_route(
        "/capabilities/{capability_name}/ready",
        capability_readiness,
        methods=["GET"],
        tags=["readiness"],
        responses={
            status.HTTP_503_SERVICE_UNAVAILABLE: {
                "description": "Capability dependency is not configured"
            }
        },
    )


def create_app(
    *,
    experience_runtime_resolver: MultimodalDraftRuntimeResolver | None = None,
    growth_onboarding_runtime: FakeGrowthOnboardingRuntime | None = None,
    growth_onboarding_actor_resolver: InMemoryGrowthOnboardingActorResolver | None = None,
    growth_onboarding_database_url: str | None = None,
) -> FastAPI:
    _configure_fgcn_persistence()
    application = FastAPI(title="AiFamily family_api", version="0.1.0")
    _record_dependency_status(application)
    if mount_experience_router is not None:
        mount_experience_router(application)
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
    # Dev/test-only session issuance. Mounted without a prefix because the
    # synthetic mobile client calls `/auth/*` at the root. These endpoints are
    # deliberately absent from a production app: `dev_auth` exchanges an
    # arbitrary external_ref for a process-local bearer token and therefore is
    # not an authentication capability. Keeping the guard at the composition
    # root also removes the routes from production OpenAPI, rather than merely
    # making them fail after they have been advertised. Their placement in the
    # assessment domain is a recorded architectural debt, not a design choice:
    # see ADR-0010.
    if is_dev_environment():
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
    # Product catalogue read.  Do not mount anything when the reviewed
    # Commerce package is absent: a 404/unadvertised endpoint is safer than a
    # fake catalogue, and the dependency status above makes the gap explicit.
    if commerce_router is not None:
        application.include_router(commerce_router)
    # Family Need closes the first platform-level vertical slice: an explicit
    # family expression becomes an N1 need aggregate. The default actor and
    # application dependencies fail closed; dev/test installs synthetic
    # adapters with the same route, errors and gates as production.
    application.include_router(family_need_router)
    register_family_need_exception_handlers(application)
    # FGCN's AI draft -> Human Gate -> Named Action control plane. Its default
    # identity/session/worker dependencies fail closed; no client can inject
    # actor or scope fields into these routes. If its provenance foundation is
    # not present on this base, leave the capability unmounted and observable.
    if fgcn_router is not None:
        application.include_router(fgcn_router)
        register_fgcn_exception_handlers(application)
    _mount_growth_onboarding(
        application,
        runtime=growth_onboarding_runtime,
        actor_resolver=growth_onboarding_actor_resolver,
        database_url=growth_onboarding_database_url,
    )
    # The service dependency is currently being completed; this is a temporary
    # wiring gap, not an intentional environment-specific feature difference.
    # Same fail-closed situation as membership, and for the same reason: the
    # service router's get_repository / get_consent_query / get_action_context /
    # get_actor_context dependencies all raise by design. Mounting registers the
    # six SERVICE endpoints in the OpenAPI schema and makes them testable via
    # `dependency_overrides`; it does not make them available in production, and
    # a caller reaching one without those overrides gets a 500 from the
    # dependency rather than a booking made on behalf of an invented family.
    # See governance/DOMAIN_REGISTRY.yaml → service_booking.known_gaps.
    # Journey uses PostgreSQL-backed identity, policy and persistence in the
    # default dependency path; deployments without PostgreSQL fail closed.
    if journey_router is not None:
        application.include_router(journey_router)
        register_journey_exception_handlers(application)
    # Service declares a legacy route with the same UI-05 path. Mount Journey
    # first so FastAPI selects the canonical private process projection while
    # the remaining service routes (including check-in drafts) stay available.
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
        install_dev_wiring(application)
    # An explicitly supplied resolver is the composition root's authority.
    # Install it after dev wiring so a caller cannot accidentally have its
    # durable/production resolver replaced by the synthetic test override.
    if experience_runtime_resolver is not None:
        if install_experience_runtime_resolver is None:
            raise RuntimeError(
                "experience_runtime_unavailable: "
                f"{_EXPERIENCE_IMPORT_ERROR}"
            )
        install_experience_runtime_resolver(application, experience_runtime_resolver)
    return application


app = create_app()
