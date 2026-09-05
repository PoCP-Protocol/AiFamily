"""FastAPI application factory for the family_api process.

The process exposes health/readiness plus the currently wired vertical slices.
Every domain keeps its production dependency seam fail-closed; development and
test install explicit synthetic adapters without changing routes, state
machines, errors or governance gates.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable

from fastapi import FastAPI

from backend.apps.family_api.dev_operator_query_wiring import install_dev_operator_query_wiring
from backend.apps.family_api.dev_wiring import install_dev_wiring, is_dev_environment
from backend.apps.family_api.evaluation_query_api import router as evaluation_query_router
from backend.apps.family_api.evaluation_query_wiring import install_evaluation_query_service
from backend.apps.family_api.experience_operations_query_api import (
    router as experience_operations_query_router,
)
from backend.apps.family_api.experience_operations_query_wiring import (
    install_experience_operations_query,
)
from backend.apps.family_api.experience_wiring import (
    install_engagement_runtime_resolver,
    install_experience_runtime_resolver,
    install_feedback_runtime_resolver,
    mount_experience_router,
)
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
from backend.domains.commerce.api.routes import router as commerce_router
from backend.domains.family_need.api.routes import (
    register_exception_handlers as register_family_need_exception_handlers,
)
from backend.domains.family_need.api.routes import router as family_need_router
from backend.domains.family_need.infrastructure.wiring import (
    install_family_need_production_wiring,
)
from backend.domains.journey.api.growth_onboarding_routes import (
    router as growth_onboarding_router,
)
from backend.domains.journey.api.growth_plan_adoption_routes import (
    GrowthPlanAdoptionHttpDependencies,
    build_growth_plan_adoption_router,
)
from backend.domains.journey.api.routes import (
    register_exception_handlers as register_journey_exception_handlers,
)
from backend.domains.journey.api.routes import router as journey_router
from backend.domains.membership.api.routes import router as membership_router
from backend.domains.product_intelligence.api.course_routes import (
    configure_course_content_gate,
    configure_course_content_repository,
)
from backend.domains.product_intelligence.api.course_routes import (
    router as course_content_router,
)
from backend.domains.product_intelligence.api.dependencies import (
    configure_actor_resolver as configure_product_intelligence_actor_resolver,
)
from backend.domains.product_intelligence.api.family_experience_signal_routes import (
    configure_family_experience_signal_repository,
)
from backend.domains.product_intelligence.api.family_experience_signal_routes import (
    router as family_experience_signal_router,
)
from backend.domains.product_intelligence.api.improvement_candidate_routes import (
    configure_improvement_candidate_repository,
)
from backend.domains.product_intelligence.api.improvement_candidate_routes import (
    router as improvement_candidate_router,
)
from backend.domains.product_intelligence.application.context import (
    ActorContext as ProductIntelligenceActorContext,
)
from backend.domains.product_intelligence.infrastructure.course_content_repository import (
    InMemoryCourseContentRepository,
)
from backend.domains.product_intelligence.infrastructure.course_content_wiring import (
    install_course_content_production_wiring,
)
from backend.domains.product_intelligence.infrastructure.family_experience_signal_wiring import (
    install_family_experience_signal_production_wiring,
)
from backend.domains.product_intelligence.infrastructure.improvement_candidate_wiring import (
    install_improvement_candidate_production_wiring,
)
from backend.domains.service.api.routes import router as service_router
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
from backend.intelligence.evaluation.query import AuthorizedEvaluationQueryService
from backend.intelligence.experience.api import MultimodalDraftRuntimeResolver
from backend.intelligence.experience.engagement_api import EngagementDraftRuntimeResolver
from backend.intelligence.experience.feedback_api import AchievementFeedbackRuntimeResolver
from backend.intelligence.experience.operations_query import (
    AuthorizedExperienceOperationsQueryService,
    HmacExperienceOperationsCursorSigner,
)
from backend.intelligence.human_gate.gate import InMemoryHumanGate
from backend.platform.persistence.session import (
    DATABASE_URL_ENV_VAR,
    get_engine,
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


def _mount_family_need(application: FastAPI, *, database_url: str | None = None) -> None:
    """Mount Family Need once, selecting only an explicit environment seam.

    Dev/test's fake actor/service overrides are installed by
    `install_dev_wiring` (they share process-local state with the mobile
    SERVICE journey's teacher/offering master data, which is what lets a
    Family Need solution draft resolve a real supply reference). This
    function only adds the branch `install_dev_wiring` does not own:
    production gets the PostgreSQL installer when an explicit PostgreSQL URL
    exists; without one, or without a real policy adapter, the route stays
    discoverable but keeps its 503 fail-closed defaults — see
    `install_family_need_production_wiring`'s own docstring for why it
    currently always raises.
    """

    application.include_router(family_need_router)
    register_family_need_exception_handlers(application)

    if is_dev_environment():
        # `install_dev_wiring` (called later in `create_app`) installs the
        # fake actor/service overrides for this router; nothing else to do
        # here.
        return

    configured_url = database_url or _runtime_database_url()
    if configured_url is not None and is_postgres_url(configured_url):
        with contextlib.suppress(RuntimeError):
            # No real FamilyNeedPolicyPort adapter exists yet (see the
            # installer's docstring). Keep the route mounted with its 503
            # fail-closed defaults rather than crash the whole process for a
            # documented, in-progress gap.
            install_family_need_production_wiring(
                application,
                database_url=configured_url,
                engine=get_engine(configured_url),
            )


def _mount_growth_plan_adoption(application: FastAPI) -> None:
    """Mount the generative growth-plan adoption slice (UI-04 adopt/read).

    Unlike the other domain routers here, this one is built by a factory
    (`build_growth_plan_adoption_router`) rather than pre-wired as a module
    singleton with `app.dependency_overrides`, so there is no
    always-mounted-with-503-defaults form to fall back on: without an actor
    resolver and a service, there is no router to build. Dev/test therefore
    builds the router immediately with the in-memory, dev-bearer-token-backed
    adapters from `growth_plan_adoption_dev_wiring` (mirroring the posture of
    `install_dev_wiring`'s other overrides — same route, errors and Named
    Action gate as production would use, backed by process-local state that
    must never be reachable outside dev/test).

    No production adapter exists yet for either a durable validated-draft
    reader or a durable idempotent adoption repository (see
    `growth_plan_adoption_dev_wiring`'s module docstring), so outside
    dev/test the route is intentionally left unmounted rather than mounted
    with adapters that do not exist — the same fail-closed posture as every
    other domain here, just expressed as "not yet mounted" instead of "503".
    """

    if not is_dev_environment():
        return

    from backend.apps.family_api import dev_wiring as _dev_wiring
    from backend.domains.journey.infrastructure.growth_plan_adoption_dev_wiring import (
        build_dev_actor_resolver,
        build_dev_growth_plan_adoption_service,
    )

    service = build_dev_growth_plan_adoption_service(
        _dev_wiring.growth_plan_draft_store,
        _dev_wiring.growth_plan_adoption_repository,
    )
    resolve_actor = build_dev_actor_resolver(_dev_wiring._identity)
    application.include_router(
        build_growth_plan_adoption_router(
            GrowthPlanAdoptionHttpDependencies(resolve_actor, service)
        )
    )


def _mount_course_content(application: FastAPI, *, database_url: str | None = None) -> None:
    """Mount only the Course Content endpoints of `product_intelligence`.

    The rest of `product_intelligence`'s router (`api/routes.py`) stays
    unmounted — that gap is tracked separately in
    `governance/DOMAIN_REGISTRY.yaml`. This function fixes it for exactly the
    course-authoring/publication slice: dev/test installs an in-memory
    repository and Human Gate plus a synthetic OPERATOR actor resolver so the
    draft -> review -> published chain is actually callable; outside dev,
    production installs a PostgreSQL-backed repository when an explicit
    PostgreSQL URL exists (see `course_content_wiring.py`). The Human Gate
    and actor resolver have no production adapter yet, so those two
    dependencies keep their fail-closed `RuntimeError` defaults regardless —
    a caller still gets a fail-closed error rather than a silently invented
    tenant/actor or a synthesized review decision.
    """

    application.include_router(course_content_router)
    if not is_dev_environment():
        configured_url = database_url or _runtime_database_url()
        if configured_url is not None and is_postgres_url(configured_url):
            install_course_content_production_wiring(engine=get_engine(configured_url))
        return

    configure_course_content_repository(InMemoryCourseContentRepository())
    configure_course_content_gate(InMemoryHumanGate())

    def _dev_product_intelligence_actor(request) -> ProductIntelligenceActorContext:  # noqa: ANN001
        tenant_scope = request.headers.get("x-tenant-scope", "dev-tenant")
        actor_id = request.headers.get("x-actor-id", "dev-operator")
        return ProductIntelligenceActorContext(
            actor_id=actor_id,
            actor_type="HUMAN",
            tenant_scope=tenant_scope,
            permissions=frozenset(
                {
                    "product_intelligence.course_content.author",
                    "product_intelligence.course_content.review",
                }
            ),
        )

    configure_product_intelligence_actor_resolver(_dev_product_intelligence_actor)


def _mount_improvement_candidates(application: FastAPI, *, database_url: str | None = None) -> None:
    """Mount the cross-family, de-identified N8 product-improvement query.

    Mirrors `_mount_course_content`'s dev/production split: dev/test installs
    an in-memory repository so `confirm_family_outcome`'s DID_NOT_HELP write
    and this query are visible in the same process; production installs a
    PostgreSQL-backed repository only when an explicit PostgreSQL URL exists.
    No actor/tenant dependency is wired here — this router carries no
    family-scoped data by design (see
    `backend.domains.product_intelligence.domain.improvement_candidate`).
    """

    application.include_router(improvement_candidate_router)
    if is_dev_environment():
        # Reuse `dev_wiring`'s own singleton (already wired into
        # `FulfillmentDeps.improvement_candidate_repository` by
        # `_dev_fulfillment_deps`) rather than a second, disconnected
        # instance — otherwise `confirm_family_outcome`'s DID_NOT_HELP write
        # would go to one repository while this query reads from another.
        from backend.apps.family_api import dev_wiring as _dev_wiring

        configure_improvement_candidate_repository(_dev_wiring._improvement_candidate_repository)
        return

    configured_url = database_url or _runtime_database_url()
    if configured_url is not None and is_postgres_url(configured_url):
        install_improvement_candidate_production_wiring(engine=get_engine(configured_url))


def _mount_family_experience_signals(
    application: FastAPI, *, database_url: str | None = None
) -> None:
    """Mount the cross-family, de-identified "did this help a family like
    mine" experience-pool query — the "小红书-style" similar-problem search.

    Mirrors `_mount_improvement_candidates`'s dev/production split. No
    actor/tenant dependency is wired here — this router carries no
    family-scoped data by design (see
    `backend.domains.product_intelligence.domain.family_experience_signal`).
    """

    application.include_router(family_experience_signal_router)
    if is_dev_environment():
        # Reuse `dev_wiring`'s own singleton (already wired into
        # `FulfillmentDeps.family_experience_signal_repository` by
        # `_dev_fulfillment_deps`) rather than a second, disconnected
        # instance — otherwise `confirm_family_outcome`'s write would go to
        # one repository while this query reads from another.
        from backend.apps.family_api import dev_wiring as _dev_wiring

        configure_family_experience_signal_repository(
            _dev_wiring._family_experience_signal_repository
        )
        return

    configured_url = database_url or _runtime_database_url()
    if configured_url is not None and is_postgres_url(configured_url):
        install_family_experience_signal_production_wiring(engine=get_engine(configured_url))


def create_app(
    *,
    experience_runtime_resolver: MultimodalDraftRuntimeResolver | None = None,
    experience_runtime_wiring: Callable[[FastAPI], None] | None = None,
    engagement_runtime_resolver: EngagementDraftRuntimeResolver | None = None,
    engagement_runtime_wiring: Callable[[FastAPI], None] | None = None,
    feedback_runtime_resolver: AchievementFeedbackRuntimeResolver | None = None,
    growth_onboarding_runtime: FakeGrowthOnboardingRuntime | None = None,
    growth_onboarding_actor_resolver: InMemoryGrowthOnboardingActorResolver | None = None,
    growth_onboarding_database_url: str | None = None,
    evaluation_query_service: AuthorizedEvaluationQueryService | None = None,
    experience_operations_query_service: AuthorizedExperienceOperationsQueryService | None = None,
    experience_operations_cursor_signer: HmacExperienceOperationsCursorSigner | None = None,
    experience_operations_query_wiring: Callable[[FastAPI], None] | None = None,
) -> FastAPI:
    _configure_fgcn_persistence()
    application = FastAPI(title="AiFamily family_api", version="0.1.0")
    # Operator-only evaluation evidence is mounted in every environment for
    # contract parity; without an explicitly composed identity-bound service,
    # the routes remain fail-closed with 503.
    application.include_router(evaluation_query_router)
    # Operator-only Experience delivery metadata is mounted for contract
    # parity; without explicit service and cursor signer it remains fail-closed.
    application.include_router(experience_operations_query_router)
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
    # Product catalogue read. Development/test use fixture data and sandbox
    # adapters; the route and business contract remain identical to production.
    application.include_router(commerce_router)
    # Family Need closes the first platform-level vertical slice: an explicit
    # family expression becomes an N1 need aggregate, is clarified, profiled
    # and matched against a real Product/Service supply reference. The default
    # actor and application dependencies fail closed; dev/test installs
    # synthetic adapters with the same route, errors and gates as production.
    _mount_family_need(application)
    # Course Content: the first fix for product_intelligence's "route never
    # mounted" gap (governance/DOMAIN_REGISTRY.yaml). Only the course
    # draft -> Human Gate review -> published slice is mounted; the rest of
    # product_intelligence's router stays deliberately unmounted.
    _mount_course_content(application)
    # N8 (product side): cross-family, de-identified "did not help" signal
    # query for product/content teams. See `_mount_improvement_candidates`.
    _mount_improvement_candidates(application)
    # Experience pool (parent-facing): cross-family, de-identified "did this
    # help a family like mine" signal query, for every decision. See
    # `_mount_family_experience_signals`.
    _mount_family_experience_signals(application)
    # FGCN's AI draft -> Human Gate -> Named Action control plane. Its default
    # identity/session/worker dependencies fail closed; no client can inject
    # actor or scope fields into these routes.
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
        # Dev/test use the same operator API contracts with synthetic records;
        # this module refuses installation outside the explicit allow-list.
        install_dev_operator_query_wiring(application)
    # Growth plan adoption (UI-04): dev/test only, see `_mount_growth_plan_adoption`.
    _mount_growth_plan_adoption(application)
    if engagement_runtime_resolver is not None and engagement_runtime_wiring is not None:
        raise ValueError(
            "engagement_runtime_resolver and engagement_runtime_wiring are mutually exclusive"
        )
    if experience_runtime_resolver is not None and experience_runtime_wiring is not None:
        raise ValueError(
            "experience_runtime_resolver and experience_runtime_wiring are mutually exclusive"
        )
    # An explicitly supplied resolver is the composition root's authority.
    # Install it after dev wiring so a caller cannot accidentally have its
    # durable/production resolver replaced by the synthetic test override.
    if experience_runtime_resolver is not None:
        install_experience_runtime_resolver(application, experience_runtime_resolver)
    if experience_runtime_wiring is not None:
        if not callable(experience_runtime_wiring):
            raise TypeError("experience_runtime_wiring must be callable")
        experience_runtime_wiring(application)
    if engagement_runtime_resolver is not None:
        install_engagement_runtime_resolver(application, engagement_runtime_resolver)
    if engagement_runtime_wiring is not None:
        if not callable(engagement_runtime_wiring):
            raise TypeError("engagement_runtime_wiring must be callable")
        engagement_runtime_wiring(application)
    if feedback_runtime_resolver is not None:
        install_feedback_runtime_resolver(application, feedback_runtime_resolver)
    if evaluation_query_service is not None:
        install_evaluation_query_service(application, evaluation_query_service)
    if experience_operations_query_wiring is not None and (
        experience_operations_query_service is not None
        or experience_operations_cursor_signer is not None
    ):
        raise ValueError(
            "experience operations query wiring and explicit dependencies are mutually exclusive"
        )
    if experience_operations_query_wiring is not None:
        if not callable(experience_operations_query_wiring):
            raise TypeError("experience_operations_query_wiring must be callable")
        experience_operations_query_wiring(application)
    elif (
        experience_operations_query_service is not None
        or experience_operations_cursor_signer is not None
    ):
        if (
            experience_operations_query_service is None
            or experience_operations_cursor_signer is None
        ):
            raise TypeError(
                "experience operations service and cursor signer must be provided together"
            )
        install_experience_operations_query(
            application,
            experience_operations_query_service,
            experience_operations_cursor_signer,
        )
    return application


app = create_app()
