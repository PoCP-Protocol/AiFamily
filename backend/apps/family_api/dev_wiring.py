"""Dev-only wiring that makes mounted vertical routes callable.

## The problem this solves

`backend/domains/service/api/dependencies.py` has four dependencies that raise
by design — `get_repository`, `get_consent_query`, `get_action_context`,
`get_actor_context`. That design is correct and this module does not change it:
a "sensible default" inside those functions would be an authorization hole that
fails *open*, and its own docstring says so.

But the consequence today is that mounted SERVICE and Family Need endpoints are
otherwise unavailable without process wiring:
the six Batch 2 SERVICE endpoints are mounted,
appear in OpenAPI, and return 500 to every caller. `main.py` states it plainly:
"Mounting buys route registration and OpenAPI visibility, not availability."

The missing piece is not thirty endpoints. It is one thing: resolving *who is
calling and which family they are acting for* from a request. And a working
version of exactly that already exists — `domains/assessment/api/dev_auth.py`
issues bearer tokens carrying `{account_id, family_id}`, and the whole UI-02 →
UI-03 assessment chain runs on it. This module connects that existing identity
to the routes that were waiting for it.

## Why overrides rather than editing the dependencies

`dependencies.py` names the intended mechanism itself:

    Tests supply them via `app.dependency_overrides`; that is the intended
    mechanism, and it is why production code must not grow test-friendly
    defaults.

So the production code path is untouched and still fails closed. Everything
here is installed on the app object, only for dev, and is absent from a
production app by construction rather than by a flag inside the domain.

## What this is NOT — read before assuming it is a feature

* **Not authentication.** It inherits `dev_auth`'s properties: `external_ref` is
  exchanged for a token directly, tokens live in a process dict and vanish on
  restart, `expires_at` is a hardcoded sentinel. See that module's own
  "What this is NOT".
* **Not consent.** `_DevConsentQuery` below **synthesises a GRANTED grant**. That
  is a real consent bypass — it is the single most dangerous thing in this file,
  which is why `install_dev_wiring` refuses to run outside dev/test rather than
  merely warning. There is no consent storage in this repository yet
  (`backend/platform/consent` holds the gate and the value objects, not a store).
* **Not persistence.** It uses `FakeServiceRepository`, so state is process-local
  and lost on restart. No database, no Alembic dependency.
* **Not a step toward production.** The production wiring is a different thing
  entirely: a real session factory, a real consent store, and the
  Account → TenantMembership → Family binding chain that `main.py` names.
  Per ADR-0017 this module belongs to `development` / `test` only, where
  `data_class` is `SYNTHETIC`; the seven promotion preconditions in that ADR are
  what gates the real thing.

R5 is the rule this file is most at risk of violating (synthetic data must not
masquerade as a business capability, and must not be reachable on a production
route). The env guard in `install_dev_wiring` is what keeps it on the right side.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.apps.family_api.ai_coach_wiring import build_dev_ai_coach_gateway
from backend.apps.family_api.orchestration.need_fulfillment_flow import fulfil_confirmed_draft
from backend.domains.assessment.api import dependencies as assessment_deps
from backend.domains.assessment.api.dev_auth import get_state as get_dev_auth_state
from backend.domains.assessment.application.commands import AssessmentCommandHandler
from backend.domains.assessment.application.growth_hypothesis_commands import (
    GrowthHypothesisCommandHandler,
)
from backend.domains.assessment.application.queries import AssessmentQueryHandler
from backend.domains.assessment.infrastructure.deterministic_interpretation import (
    DeterministicInterpretationAdapter,
)
from backend.domains.assessment.infrastructure.fake_repository import FakeAssessmentRepository
from backend.domains.commerce.api import dependencies as commerce_deps
from backend.domains.commerce.application.master_data import ensure_mobile_product_master_data
from backend.domains.commerce.infrastructure.fake_repository import FakeCommerceRepository
from backend.domains.family_need.api import ai_coach_dependencies as family_need_ai_coach_deps
from backend.domains.family_need.api import dependencies as family_need_deps
from backend.domains.family_need.api import fulfillment_dependencies as family_need_fulfillment_deps
from backend.domains.family_need.application.service import FamilyNeedApplicationService
from backend.domains.family_need.domain.value_objects import ActorType as FamilyNeedActorType
from backend.domains.family_need.infrastructure.commerce_supply_adapter import (
    CommerceSupplyAdapter,
)
from backend.domains.family_need.infrastructure.course_supply_adapter import (
    CourseSupplyAdapter,
)
from backend.domains.family_need.infrastructure.fake_repository import (
    FakeFamilyNeedPolicy,
)
from backend.domains.family_need.infrastructure.postgres_repository import (
    SqlAlchemyFamilyNeedRepository,
)
from backend.domains.family_need.infrastructure.service_supply_adapter import (
    ServiceSupplyAdapter,
)
from backend.domains.family_need.infrastructure.wiring import CompositeSupplyAdapter
from backend.domains.journey.application.outcome_loop import GrowthOutcomeLoop
from backend.domains.product_intelligence.application.context import (
    ActorContext as CourseActorContext,
)
from backend.domains.product_intelligence.application.course_publication import (
    create_course_content_draft,
    decide_course_content_review,
    submit_course_content_for_review,
)
from backend.domains.product_intelligence.domain.course_content import CourseLesson
from backend.domains.product_intelligence.domain.errors import ProductIntelligenceNotFoundError
from backend.domains.product_intelligence.infrastructure.course_content_postgres_repository import (
    SqlAlchemyCourseContentRepository,
)
from backend.domains.product_intelligence.infrastructure.family_experience_signal_postgres_repository import (  # noqa: E501
    SqlAlchemyFamilyExperienceSignalRepository,
)
from backend.domains.product_intelligence.infrastructure.improvement_candidate_postgres_repository import (  # noqa: E501
    SqlAlchemyImprovementCandidateRepository,
)
from backend.domains.service.api import dependencies as service_deps
from backend.domains.service.application.context import ActionContext
from backend.domains.service.application.master_data import ensure_mobile_master_data
from backend.domains.service.infrastructure.fake_repository import FakeServiceRepository
from backend.intelligence.context_engine.store import ContextBroker
from backend.intelligence.experience.api import get_multimodal_draft_runtime_resolver
from backend.intelligence.experience.engagement_api import (
    get_engagement_draft_runtime_resolver,
)
from backend.intelligence.experience.family_ai_coach import CoachMemoryStore
from backend.intelligence.experience.run_http import InMemoryExperienceRunLedger
from backend.intelligence.experience.synthetic_engagement_runtime import (
    SyntheticEngagementRuntimeResolver,
)
from backend.intelligence.experience.synthetic_runtime import SyntheticRuntimeResolver
from backend.intelligence.human_gate.gate import InMemoryHumanGate
from backend.intelligence.memory.store import SqlAlchemyMemoryStore
from backend.intelligence.model_gateway.provenance import InMemoryModelDraftRegistry
from backend.platform.audit.recorder import AuditRecorder
from backend.platform.consent.models import (
    ConsentGrant,
    ConsentPurpose,
    ConsentStatus,
    GuardianRelation,
    SubjectAge,
)
from backend.platform.identity.context import ActorContext, ActorType, TenantStatus
from backend.platform.identity.directory import InMemoryTenantDirectory

ENV_VAR = "AIFAMILY_ENV"
DEV_ENVIRONMENTS = frozenset({"development", "dev", "test", "local"})
"""Environments this wiring may be installed in.

Deliberately a positive list, not "anything except production": a typo in the
env var (`AIFAMILY_ENV=prod-eu`) must fall on the refusing side, not the
installing side.
"""


def current_environment() -> str:
    # No sensible default here: an unset `AIFAMILY_ENV` must fall on the
    # refusing side, not the installing side (see module docstring above).
    # Defaulting to "development" would make an operator's failure to set
    # the env var silently install dev-only auth wiring in production.
    return os.environ.get(ENV_VAR, "").strip().lower()


def is_dev_environment() -> bool:
    return current_environment() in DEV_ENVIRONMENTS


class DevWiringNotPermittedError(RuntimeError):
    """Raised when dev wiring is asked to install outside a dev environment."""


DEV_DEFAULT_DATABASE_URL = (
    "postgresql+asyncpg://aifamily:aifamily@localhost:55442/aifamily_dev_claude"
)
"""Fallback dev/test PostgreSQL URL — same `aifamily-dev-postgres` container
`docker-compose.dev.yml` starts, but a **separate database**
(`aifamily_dev_claude`), not `aifamily_test`.

`aifamily_test` is shared, long-lived state other gated integration tests
(and other concurrent development work against this same repository/
container) read and write. This module's `reset_dev_state()` truncates its
tables on every test's setup — pointing that at `aifamily_test` would
periodically wipe out unrelated concurrent work sharing the same Postgres
container. `aifamily_dev_claude` is created once
(``CREATE DATABASE aifamily_dev_claude``) and migrated
(``DATABASE_URL=...aifamily_dev_claude uv run alembic upgrade head``) so this
module's truncate-on-reset semantics stay confined to state only this dev
wiring owns.

Dev/test for the five domains this module wires (family_need, course_content,
improvement_candidate, family_experience_signal, and the FGCN provider
admission read) is a real-database requirement, not an optional one: this
constant exists only as the *default value* of an explicit configuration,
never as a silent fallback to sqlite or an in-memory store. See
`_dev_database_url`'s docstring for the fail-closed contract.
"""


def _dev_database_url() -> str:
    """Return the PostgreSQL URL dev/test wiring must use.

    Prefers `DATABASE_URL` from the environment; falls back to
    `DEV_DEFAULT_DATABASE_URL` (the local `aifamily-dev-postgres` container)
    when unset. Deliberately does **not** fall back to sqlite or an in-memory
    engine — a dev environment with no reachable PostgreSQL must fail loudly
    at the point a connection is actually opened, not silently downgrade to a
    different persistence technology than production uses.
    """

    configured = os.environ.get("DATABASE_URL", "").strip()
    return configured or DEV_DEFAULT_DATABASE_URL


def _get_dev_engine() -> AsyncEngine:
    """Create a brand-new `AsyncEngine`, with pooling disabled (`NullPool`).

    Starlette's `TestClient` opens a **new anyio blocking portal — a new
    event loop — for every `.request()` call** it makes, not once per
    `TestClient` instance (`starlette.testclient.TestClient._portal_factory`
    only reuses a portal inside a `with client:` lifespan context, which the
    tests this module supports do not use). An asyncpg connection is bound
    to the loop that opened it; handing a *pooled* connection opened on one
    request's loop to the next request's (different) loop is exactly the
    "Event loop is closed" / "'NoneType' object has no attribute 'send'"
    failure this construction avoids. `NullPool` means every checkout opens
    a fresh driver connection and every checkin closes it. This trades a
    little latency (irrelevant for dev/test traffic) for correctness across
    the request-per-loop test harness. Callers must dispose the engine when
    done — `_dev_connection` below is the usual way to get that for free.
    """

    return create_async_engine(
        _dev_database_url(),
        poolclass=NullPool,
        connect_args={"statement_cache_size": 0},
    )


@contextlib.asynccontextmanager
async def _dev_connection():
    """Open one transactional connection on a fresh, disposable engine.

    Every connection-scoped repository method in this module uses this
    instead of holding a shared engine, for the reason `_get_dev_engine`
    documents: a shared engine would be bound to whichever event loop
    created it, and the next `TestClient` request runs on a different loop.
    """

    engine = _get_dev_engine()
    try:
        async with engine.begin() as connection:
            yield connection
    finally:
        await engine.dispose()


@contextlib.asynccontextmanager
async def _dev_fgcn_session():
    """Open one `AsyncSession` (not a bare `Connection`) on a fresh,
    disposable engine — the durable FGCN authorization path needs ORM
    session semantics (`SqlAlchemyFGCNRepository`/`SqlAlchemyProviderAdmissionQuery`
    both take a `Session`), same reasoning as `_dev_connection` for why the
    engine is created fresh per call rather than shared. Unlike
    `_ConnectionScopedCoachMemoryStoreForDev`, no `session.begin()` wrapper
    here — `authorize_real_teacher_assignment_durable` calls
    `repo.commit()` itself at the points that need it, matching the real
    Postgres integration test's own usage (`test_family_need_durable_
    assignment_postgres.py`: `async with session_factory() as session: ...`,
    no explicit `begin()`).
    """

    engine = _get_dev_engine()
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


class _ConnectionScopedFamilyNeedRepository:
    """Opens one connection (as a transaction) per call, mirroring the
    module-singleton shape the Family Need application service and dev
    routes expect (a single object exposing every `FamilyNeedRepositoryPort`
    method), while still giving each call its own PostgreSQL transaction —
    the same per-call-connection approach
    `course_content_wiring._ConnectionScopedCourseContentRepository` and
    `improvement_candidate_wiring._ConnectionScopedImprovementCandidateRepository`
    use in production wiring.
    """

    async def save_signal(self, signal) -> None:  # noqa: ANN001
        async with _dev_connection() as connection:
            await SqlAlchemyFamilyNeedRepository(connection).save_signal(signal)

    async def get_signal(self, *, tenant_id: str, family_id: str, signal_id: str):
        async with _dev_connection() as connection:
            return await SqlAlchemyFamilyNeedRepository(connection).get_signal(
                tenant_id=tenant_id, family_id=family_id, signal_id=signal_id
            )

    async def save_need(self, need) -> None:  # noqa: ANN001
        async with _dev_connection() as connection:
            await SqlAlchemyFamilyNeedRepository(connection).save_need(need)

    async def get_need(self, *, tenant_id: str, family_id: str, need_id: str):
        async with _dev_connection() as connection:
            return await SqlAlchemyFamilyNeedRepository(connection).get_need(
                tenant_id=tenant_id, family_id=family_id, need_id=need_id
            )

    async def save_profile(self, profile) -> None:  # noqa: ANN001
        async with _dev_connection() as connection:
            await SqlAlchemyFamilyNeedRepository(connection).save_profile(profile)

    async def get_profile(self, *, tenant_id: str, family_id: str, profile_id: str):
        async with _dev_connection() as connection:
            return await SqlAlchemyFamilyNeedRepository(connection).get_profile(
                tenant_id=tenant_id, family_id=family_id, profile_id=profile_id
            )

    async def save_solution_draft(self, draft) -> None:  # noqa: ANN001
        async with _dev_connection() as connection:
            await SqlAlchemyFamilyNeedRepository(connection).save_solution_draft(draft)

    async def get_solution_draft(self, *, tenant_id: str, family_id: str, draft_id: str):
        async with _dev_connection() as connection:
            return await SqlAlchemyFamilyNeedRepository(connection).get_solution_draft(
                tenant_id=tenant_id, family_id=family_id, draft_id=draft_id
            )

    async def save_assignment_plan(self, plan) -> None:  # noqa: ANN001
        async with _dev_connection() as connection:
            await SqlAlchemyFamilyNeedRepository(connection).save_assignment_plan(plan)

    async def get_assignment_plan(self, *, tenant_id: str, family_id: str, plan_id: str):
        async with _dev_connection() as connection:
            return await SqlAlchemyFamilyNeedRepository(connection).get_assignment_plan(
                tenant_id=tenant_id, family_id=family_id, plan_id=plan_id
            )

    async def save_outcome(self, outcome) -> None:  # noqa: ANN001
        async with _dev_connection() as connection:
            await SqlAlchemyFamilyNeedRepository(connection).save_outcome(outcome)

    async def get_outcomes_for_need(self, *, tenant_id: str, family_id: str, need_id: str):
        async with _dev_connection() as connection:
            return await SqlAlchemyFamilyNeedRepository(connection).get_outcomes_for_need(
                tenant_id=tenant_id, family_id=family_id, need_id=need_id
            )

    async def append_event(self, event) -> None:  # noqa: ANN001
        async with _dev_connection() as connection:
            await SqlAlchemyFamilyNeedRepository(connection).append_event(event)

    async def find_by_idempotency_key(
        self, *, tenant_id: str, family_id: str, idempotency_key: str
    ):
        async with _dev_connection() as connection:
            return await SqlAlchemyFamilyNeedRepository(connection).find_by_idempotency_key(
                tenant_id=tenant_id, family_id=family_id, idempotency_key=idempotency_key
            )


class _ConnectionScopedCourseContentRepositoryForDev:
    """Same per-call-connection wrapper `course_content_wiring` uses in
    production, kept as a separate class here (rather than importing that
    module's private one) because it composes with `_get_dev_engine` and
    exists for the reset lifecycle `reset_dev_state` owns."""

    async def save_course_content(self, course) -> None:  # noqa: ANN001
        async with _dev_connection() as connection:
            await SqlAlchemyCourseContentRepository(connection).save_course_content(course)

    async def load_course_content(self, course_id: str, tenant_scope: str):
        async with _dev_connection() as connection:
            return await SqlAlchemyCourseContentRepository(connection).load_course_content(
                course_id, tenant_scope
            )

    async def list_published_course_content(self, tenant_scope: str):
        async with _dev_connection() as connection:
            return await SqlAlchemyCourseContentRepository(
                connection
            ).list_published_course_content(tenant_scope)


class _ConnectionScopedImprovementCandidateRepositoryForDev:
    async def save_improvement_candidate(self, candidate) -> None:  # noqa: ANN001
        async with _dev_connection() as connection:
            await SqlAlchemyImprovementCandidateRepository(connection).save_improvement_candidate(
                candidate
            )

    async def list_improvement_candidates(self):
        async with _dev_connection() as connection:
            return await SqlAlchemyImprovementCandidateRepository(
                connection
            ).list_improvement_candidates()


class _ConnectionScopedFamilyExperienceSignalRepositoryForDev:
    async def save_family_experience_signal(self, signal) -> None:  # noqa: ANN001
        async with _dev_connection() as connection:
            await SqlAlchemyFamilyExperienceSignalRepository(
                connection
            ).save_family_experience_signal(signal)

    async def list_family_experience_signals(self):
        async with _dev_connection() as connection:
            return await SqlAlchemyFamilyExperienceSignalRepository(
                connection
            ).list_family_experience_signals()

    async def summarize_by_component(self, *, category):
        async with _dev_connection() as connection:
            return await SqlAlchemyFamilyExperienceSignalRepository(
                connection
            ).summarize_by_component(category=category)


class _ConnectionScopedCoachMemoryStoreForDev:
    """Opens one `AsyncSession` per call, same reasoning as `_dev_connection`
    (a session is bound to the event loop that opened it, and a fresh
    `TestClient.request()` call may run on a different loop).

    `SqlAlchemyMemoryStore` needs an ORM `AsyncSession` (it uses
    `Session.get`/`Session.add`), not a bare `Connection` the other
    connection-scoped wrappers in this module use — hence its own
    `async_sessionmaker`-backed helper instead of reusing `_dev_connection`.
    """

    async def put(self, memory):  # noqa: ANN001
        engine = _get_dev_engine()
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session, session.begin():
                return await SqlAlchemyMemoryStore(session).put(memory)
        finally:
            await engine.dispose()

    async def list_recent_by_source_prefix(
        self, source_ref_prefix, scope, *, purpose, limit=3, moment=None
    ):  # noqa: ANN001
        engine = _get_dev_engine()
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                return await SqlAlchemyMemoryStore(session).list_recent_by_source_prefix(
                    source_ref_prefix, scope, purpose=purpose, limit=limit, moment=moment
                )
        finally:
            await engine.dispose()


_coach_memory_store: CoachMemoryStore = _ConnectionScopedCoachMemoryStoreForDev()


def _truncate_dev_tables() -> None:
    """Clear the five domains' real PostgreSQL tables between tests.

    Replaces the old "rebuild a fresh in-memory repository" reset: dev/test
    state now lives in `aifamily-dev-postgres`, so clean-slate isolation
    means truncating the tables, not discarding a Python object.
    `family_service_providers` (the FGCN provider-admission read's backing
    table) is deliberately absent from this list — see
    `_DevProviderAdmissionQuery`'s docstring; that table is `service_booking`
    master-data seeded by `ensure_mobile_master_data`, out of this task's
    scope, and reset by the `service` domain's own fixtures.

    No foreign keys exist between these tables (each migration's own
    `op.drop_table` order documents intended dependency, not an enforced
    constraint), so a single `TRUNCATE ... RESTART IDENTITY` statement is
    safe regardless of ordering.

    Runs on its own throwaway `AsyncEngine` (via `_get_dev_engine`, `NullPool`
    — see that function's docstring), which is explicitly disposed at the end
    of this function's loop rather than left for garbage collection.
    """

    async def _run() -> None:
        engine = _get_dev_engine()
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        """
                        TRUNCATE TABLE
                          family_need_events,
                          family_need_confirmed_outcomes,
                          family_need_assignment_plans,
                          solution_drafts,
                          need_profiles,
                          family_needs,
                          need_signals,
                          course_content,
                          product_improvement_candidates,
                          family_experience_signals
                        RESTART IDENTITY CASCADE
                        """
                    )
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


# One repository for the process, so a booking submitted by one request is
# visible to the next. A per-request instance would make every read return
# empty and look like a persistence bug.
#
# These four connection-scoped wrappers hold no engine reference of their
# own — each method call resolves `_get_dev_engine()` fresh (see the classes
# above) rather than capturing one at construction time. `TestClient`
# creates a new anyio/asyncio event loop per instantiation, and an
# `AsyncEngine`'s pooled asyncpg connections are bound to the loop that
# created them; capturing the engine once at module-import time (before any
# test's loop exists) would hand every later request a dead connection from
# a closed loop ("Event loop is closed"). Resolving lazily, plus
# `reset_dev_state`'s dispose-and-clear of `_dev_engine`, means each test's
# first call creates (or re-creates) the engine on whichever loop is
# actually running.
_repository = FakeServiceRepository()
_commerce_repository = FakeCommerceRepository()
_family_need_repository = _ConnectionScopedFamilyNeedRepository()
_family_need_policy = FakeFamilyNeedPolicy()
_course_content_repository = _ConnectionScopedCourseContentRepositoryForDev()
_course_human_gate = InMemoryHumanGate()
_improvement_candidate_repository = _ConnectionScopedImprovementCandidateRepositoryForDev()
_family_experience_signal_repository = _ConnectionScopedFamilyExperienceSignalRepositoryForDev()


class _DevProviderAdmissionQuery:
    """FGCN provider-admission query backed by the real dev service catalogue.

    A provider counts as admitted for FGCN purposes exactly when
    `ServiceProvider.is_bookable` already says so (real
    `status`/`qualification_status`/`admission_status` facts seeded by
    `ensure_mobile_master_data`) — no separate admission fixture is invented.

    `capability_keys`/`allowed_purposes` are read from the provider's own
    `attributes` (the same JSONB-shaped dict `ensure_mobile_master_data` seeds
    under `fgcn_capability_keys`/`fgcn_allowed_purposes`), matching exactly
    what `SqlAlchemyProviderAdmissionQuery` reads from the real
    `family_service_providers.attributes` column in production/staging. Before
    this, this method echoed the caller's own `required_capability_keys`/
    `scope.purpose` straight back into the snapshot, which meant the
    capability/purpose checks in `assert_provider_admitted` could never fail —
    admission was decided entirely by the call site, not by any fact recorded
    against the provider.
    """

    def resolve(
        self,
        *,
        provider_ref: str,
        assignee_kind: str,
        required_capability_keys: tuple[str, ...],
        scope,
    ):
        from backend.domains.service.fgcn.admission import ProviderAdmissionSnapshot

        # Read the *current* process-local `_repository` global rather than
        # one captured at construction time: `reset_dev_state()` (used by
        # every test's `_dev_env` fixture) rebinds that global to a fresh
        # `FakeServiceRepository`, and a captured reference would keep
        # querying the stale, already-discarded one.
        provider = next(
            (item for item in _repository.providers.values() if item.provider_ref == provider_ref),
            None,
        )
        if provider is None or not provider.is_bookable:
            return None
        attributes = provider.attributes if isinstance(provider.attributes, dict) else {}
        capability_keys = attributes.get("fgcn_capability_keys")
        allowed_purposes = attributes.get("fgcn_allowed_purposes")
        if not isinstance(capability_keys, (list, tuple)) or not isinstance(
            allowed_purposes, (list, tuple)
        ):
            # No FGCN admission facts recorded against this provider: refusal,
            # never an implicit allow.
            return None
        return ProviderAdmissionSnapshot(
            provider_ref=provider_ref,
            assignee_kind=assignee_kind,
            admission_status="ACTIVE",
            capability_keys=tuple(capability_keys),
            allowed_purposes=tuple(allowed_purposes),
            capacity_available=1,
        )


_dev_fgcn_provider_admission = _DevProviderAdmissionQuery()

DEV_COURSE_CATALOG_TENANT_SCOPE = "dev"
"""Tenant scope the seeded course catalog is published under (see
`_seed_dev_published_course`). Courses are a shared, cross-tenant catalog
(same simplification `CourseSupplyAdapter` makes), so this is the publishing
tenant, not any individual family's `tenant_id`."""


_COURSE_AUTHOR_CONTEXT = CourseActorContext(
    actor_id="dev-course-author",
    actor_type="HUMAN",
    tenant_scope="dev",
    permissions=frozenset({"product_intelligence.course_content.author"}),
)
_COURSE_REVIEWER_CONTEXT = CourseActorContext(
    actor_id="dev-course-reviewer",
    actor_type="HUMAN",
    tenant_scope="dev",
    permissions=frozenset({"product_intelligence.course_content.review"}),
)


@dataclass(frozen=True, slots=True)
class _DevCourseSpec:
    """One course's authoring content, before it exists as a `CourseContent`."""

    course_id: str
    system: str
    title: str
    problem_statement: str
    assessment_criteria: tuple[str, ...]
    learning_goal: str
    lessons: tuple[CourseLesson, ...]
    outcome_metrics: tuple[str, ...]


DEV_SEEDED_COURSE_ID = "course-content-dev-homework-delay"
"""Stable id for the flagship seeded course ("告别作业磨蹭", 学习成长体系) so
tests can name it without depending on UUID generation order. Kept as its own
top-level constant (rather than only living inside `DEV_COURSE_CATALOG`)
because pre-existing tests already reference it directly."""

DEV_SEEDED_COURSE_ID_PARENTING_BASICS = "course-content-dev-family-coach"
DEV_SEEDED_COURSE_ID_COMMUNICATION = "course-content-dev-listen-to-child"
DEV_SEEDED_COURSE_ID_DIGITAL_LIFE = "course-content-dev-phone-rules"
DEV_SEEDED_COURSE_ID_EMOTION = "course-content-dev-recognize-emotions"
DEV_SEEDED_COURSE_ID_ADOLESCENCE = "course-content-dev-understand-adolescence"


def _lesson(
    lesson_id: str, sequence: int, title: str, knowledge_point: str, action_task: str
) -> CourseLesson:
    return CourseLesson(
        lesson_id=lesson_id,
        sequence=sequence,
        title=title,
        knowledge_point=knowledge_point,
        action_task=action_task,
    )


# 24 core courses across the platform blueprint's six systems (4 each). The
# flagship "告别作业磨蹭" keeps its pre-existing id/content unchanged; the
# other 23 are new. Each is a `_DevCourseSpec`, not a `CourseContent` —
# `_seed_dev_course_catalog` is the only place that turns one into a real,
# governed, PUBLISHED aggregate.
DEV_COURSE_CATALOG: tuple[_DevCourseSpec, ...] = (
    # 体系一：正向养育基础
    _DevCourseSpec(
        course_id=DEV_SEEDED_COURSE_ID_PARENTING_BASICS,
        system="正向养育基础",
        title="成为更好的家庭教练",
        problem_statement="家长习惯直接下命令，孩子越来越不愿配合",
        assessment_criteria=("家长发出指令后孩子的配合意愿",),
        learning_goal="家长能用提问和引导代替命令，让孩子参与决定",
        lessons=(
            _lesson(
                "lesson-1",
                1,
                "教练式提问的基本句式",
                "开放式问题比命令更能激发配合",
                "今天用一个问句代替一个命令",
            ),
        ),
        outcome_metrics=("命令式语句使用频率",),
    ),
    _DevCourseSpec(
        course_id="course-content-dev-family-rules",
        system="正向养育基础",
        title="家庭规则怎么建立",
        problem_statement="家里没有清晰规则，事事都要临场吵一遍",
        assessment_criteria=("家庭是否有书面/口头约定的共同规则",),
        learning_goal="和孩子共同制定3条可执行的家庭规则",
        lessons=(
            _lesson(
                "lesson-1",
                1,
                "规则要少而清晰",
                "超过3条规则很难被记住和执行",
                "和孩子一起选出最重要的3条",
            ),
        ),
        outcome_metrics=("规则被遵守的次数",),
    ),
    _DevCourseSpec(
        course_id="course-content-dev-praise-and-boundaries",
        system="正向养育基础",
        title="表扬、奖励与边界",
        problem_statement="表扬和奖励用得越多，孩子反而越不主动",
        assessment_criteria=("表扬是否具体、奖励是否与内在动机冲突",),
        learning_goal="家长能区分描述性表扬与空泛表扬，减少物质奖励依赖",
        lessons=(
            _lesson(
                "lesson-1",
                1,
                "描述性表扬怎么说",
                "具体描述行为比笼统夸奖更有效",
                "今天记录一次具体的表扬",
            ),
        ),
        outcome_metrics=("具体表扬占比",),
    ),
    _DevCourseSpec(
        course_id="course-content-dev-why-wont-listen",
        system="正向养育基础",
        title="孩子为什么不听话",
        problem_statement="家长觉得孩子故意对抗，其实往往是需求没被看见",
        assessment_criteria=("对抗行为出现前是否有未被满足的需求",),
        learning_goal="家长能在对抗发生前识别孩子的潜在需求",
        lessons=(
            _lesson(
                "lesson-1",
                1,
                "行为背后的需求",
                "对抗常是求助的另一种表达",
                "记录一次对抗行为发生前的情境",
            ),
        ),
        outcome_metrics=("对抗性行为频率",),
    ),
    # 体系二：亲子沟通
    _DevCourseSpec(
        course_id=DEV_SEEDED_COURSE_ID_COMMUNICATION,
        system="亲子沟通",
        title="学会真正听孩子说话",
        problem_statement="家长边听边评判，孩子觉得说了也没用",
        assessment_criteria=("孩子主动分享的频率",),
        learning_goal="家长能先复述孩子的话再回应，减少打断评判",
        lessons=(
            _lesson(
                "lesson-1",
                1,
                "先复述，再回应",
                "复述能让孩子感到被理解",
                "今天练习一次先复述再回应",
            ),
        ),
        outcome_metrics=("孩子主动开口分享次数",),
    ),
    _DevCourseSpec(
        course_id="course-content-dev-why-child-stopped-talking",
        system="亲子沟通",
        title="孩子为什么越来越不愿意和我说话",
        problem_statement="孩子从愿意分享变成沉默，家长不知道从哪一步开始的",
        assessment_criteria=("孩子主动开口的频率变化趋势",),
        learning_goal="家长能识别让孩子闭嘴的三种常见反应模式",
        lessons=(
            _lesson(
                "lesson-1",
                1,
                "三种关闭对话的反应",
                "说教、否定、追问都会让孩子选择沉默",
                "今天避免其中一种反应",
            ),
        ),
        outcome_metrics=("对话持续时长",),
    ),
    _DevCourseSpec(
        course_id="course-content-dev-less-criticism",
        system="亲子沟通",
        title="少批评，多沟通",
        problem_statement="批评是家长最快的反应，但效果越来越差",
        assessment_criteria=("批评性语句与建设性语句的比例",),
        learning_goal="家长能用观察+感受+需要的句式替代批评",
        lessons=(
            _lesson(
                "lesson-1",
                1,
                "观察-感受-需要",
                "描述事实和感受比评判更容易被接受",
                "今天用这个句式说一次",
            ),
        ),
        outcome_metrics=("批评性语句频率",),
    ),
    _DevCourseSpec(
        course_id="course-content-dev-resolve-conflict",
        system="亲子沟通",
        title="如何处理亲子冲突",
        problem_statement="每次冲突都升级成争吵，事后双方都不愿先低头",
        assessment_criteria=("冲突升级为争吵的比例",),
        learning_goal="家长能在冲突升温时先暂停，而不是立刻还击",
        lessons=(
            _lesson(
                "lesson-1",
                1,
                "冲突中的暂停信号",
                "情绪高涨时对话无法产生共识",
                "约定一个双方都认可的暂停信号",
            ),
        ),
        outcome_metrics=("冲突升级次数",),
    ),
    # 体系三：学习成长（"告别作业磨蹭"为该体系旗舰课，内容不变，见下方 flagship）
    _DevCourseSpec(
        course_id="course-content-dev-learning-habit",
        system="学习成长",
        title="帮助孩子建立学习习惯",
        problem_statement="孩子学习全靠家长盯着，一放手就散",
        assessment_criteria=("孩子独立完成学习任务的比例",),
        learning_goal="孩子能建立一个不需要提醒的固定学习时段",
        lessons=(
            _lesson(
                "lesson-1",
                1,
                "固定时段的力量",
                "固定的时间线索能减少启动阻力",
                "和孩子一起定一个每天的学习时段",
            ),
        ),
        outcome_metrics=("独立完成学习任务次数",),
    ),
    _DevCourseSpec(
        course_id="course-content-dev-no-motivation",
        system="学习成长",
        title="孩子没有学习动力怎么办",
        problem_statement="孩子说什么都无所谓，对学习提不起兴趣",
        assessment_criteria=("孩子对学习相关话题的主动提及频率",),
        learning_goal="家长能找到孩子当下真正在意的一件事作为切入点",
        lessons=(
            _lesson(
                "lesson-1",
                1,
                "找到孩子在意的事",
                "外部动机不持久，内在兴趣才能驱动行动",
                "问孩子最近在意的一件事",
            ),
        ),
        outcome_metrics=("主动提及学习话题次数",),
    ),
    _DevCourseSpec(
        course_id="course-content-dev-after-exam",
        system="学习成长",
        title="考试之后父母应该怎么做",
        problem_statement="考完试家长第一反应是问分数,孩子觉得只有分数被关心",
        assessment_criteria=("考后对话中分数话题占比",),
        learning_goal="家长能先关心孩子的感受，再讨论具体题目",
        lessons=(
            _lesson(
                "lesson-1",
                1,
                "先问感受，再问分数",
                "先处理情绪才能进入有效复盘",
                "下次考完先问孩子感受如何",
            ),
        ),
        outcome_metrics=("考后对话中先问感受的比例",),
    ),
    # 体系四：数字生活
    _DevCourseSpec(
        course_id=DEV_SEEDED_COURSE_ID_DIGITAL_LIFE,
        system="数字生活",
        title="家庭手机规则",
        problem_statement="手机使用没有约定，每次收手机都是一场战争",
        assessment_criteria=("是否有双方共同认可的手机使用约定",),
        learning_goal="家庭建立一条可执行、双方都参与制定的手机使用规则",
        lessons=(
            _lesson(
                "lesson-1",
                1,
                "共同制定比单方规定更有效",
                "参与制定的规则更容易被遵守",
                "和孩子一起写一条手机使用约定",
            ),
        ),
        outcome_metrics=("因手机引发的冲突次数",),
    ),
    _DevCourseSpec(
        course_id="course-content-dev-cant-put-down-phone",
        system="数字生活",
        title="孩子为什么放不下手机",
        problem_statement="家长觉得孩子沉迷手机，却没想过手机在替代什么",
        assessment_criteria=("孩子使用手机时试图满足的真实需求",),
        learning_goal="家长能识别手机背后孩子在寻求的社交/放松/成就需求",
        lessons=(
            _lesson(
                "lesson-1",
                1,
                "手机在替代什么",
                "屏幕时间常是其他需求未被满足的替代品",
                "观察孩子最常用手机做什么",
            ),
        ),
        outcome_metrics=("非必要屏幕时间",),
    ),
    _DevCourseSpec(
        course_id="course-content-dev-games-not-evil",
        system="数字生活",
        title="游戏不是洪水猛兽",
        problem_statement="家长把游戏一刀切禁止，反而引发更强烈的对抗",
        assessment_criteria=("家庭对游戏话题的对话是否能理性进行",),
        learning_goal="家长能和孩子协商游戏时间而非单方面禁止",
        lessons=(
            _lesson(
                "lesson-1",
                1,
                "协商比禁止更持久",
                "单方禁止容易引发隐瞒和对抗",
                "和孩子协商一个双方接受的游戏时长",
            ),
        ),
        outcome_metrics=("因游戏引发的隐瞒行为次数",),
    ),
    _DevCourseSpec(
        course_id="course-content-dev-ai-era-learning",
        system="数字生活",
        title="AI时代孩子应该怎么学习",
        problem_statement="家长担心AI工具会让孩子失去独立思考能力",
        assessment_criteria=("孩子使用AI工具时是否先自己尝试",),
        learning_goal="孩子能把AI当作检验想法的工具，而非替代思考的捷径",
        lessons=(
            _lesson(
                "lesson-1",
                1,
                "先思考，再借助AI核对",
                "先尝试后核对能保留思考过程",
                "本周用AI核对一次自己先做的答案",
            ),
        ),
        outcome_metrics=("先自主尝试后再用AI核对的比例",),
    ),
    # 体系五：情绪与成长
    _DevCourseSpec(
        course_id=DEV_SEEDED_COURSE_ID_EMOTION,
        system="情绪与成长",
        title="帮助孩子认识情绪",
        problem_statement="孩子说不清自己怎么了，只会哭闹或沉默",
        assessment_criteria=("孩子能否用词语描述自己的情绪",),
        learning_goal="孩子能识别并说出至少三种基本情绪",
        lessons=(
            _lesson(
                "lesson-1",
                1,
                "情绪命名练习",
                "能说出情绪名称是自我调节的第一步",
                "今天和孩子一起给一种情绪命名",
            ),
        ),
        outcome_metrics=("孩子主动描述情绪的次数",),
    ),
    _DevCourseSpec(
        course_id="course-content-dev-manage-own-emotions",
        system="情绪与成长",
        title="父母如何管理自己的情绪",
        problem_statement="家长自己情绪失控，事后又后悔对孩子发火",
        assessment_criteria=("家长情绪失控后能否及时修复关系",),
        learning_goal="家长能在情绪升温时先离开现场冷静，再回来沟通",
        lessons=(
            _lesson(
                "lesson-1",
                1,
                "情绪暂停的信号",
                "识别自己的情绪信号能提前预防失控",
                "找到自己情绪升温的身体信号",
            ),
        ),
        outcome_metrics=("情绪失控后主动修复关系的次数",),
    ),
    _DevCourseSpec(
        course_id="course-content-dev-tantrum",
        system="情绪与成长",
        title="孩子发脾气怎么办",
        problem_statement="孩子发脾气时家长要么妥协要么硬压，都没有真正解决",
        assessment_criteria=("发脾气事件的持续时长与频率",),
        learning_goal="家长能在孩子发脾气时先陪伴情绪，再讨论问题",
        lessons=(
            _lesson(
                "lesson-1",
                1,
                "先陪伴，再解决问题",
                "情绪高涨时讲道理是无效的",
                "下次发脾气先安静陪伴而非立刻说理",
            ),
        ),
        outcome_metrics=("发脾气持续时长",),
    ),
    _DevCourseSpec(
        course_id="course-content-dev-facing-setback",
        system="情绪与成长",
        title="如何面对孩子的挫败",
        problem_statement="孩子遇到挫败就想放弃，家长一安慰又显得敷衍",
        assessment_criteria=("孩子遇到挫败后是否愿意再次尝试",),
        learning_goal="孩子能把一次失败看作可以调整重试的过程",
        lessons=(
            _lesson(
                "lesson-1",
                1,
                "过程性反馈的力量",
                "关注努力过程比关注结果更能鼓励再尝试",
                "这次挫败后聊聊过程中哪一步值得肯定",
            ),
        ),
        outcome_metrics=("挫败后重新尝试的比例",),
    ),
    # 体系六：青春期
    _DevCourseSpec(
        course_id=DEV_SEEDED_COURSE_ID_ADOLESCENCE,
        system="青春期",
        title="理解青春期",
        problem_statement="孩子进入青春期，家长还在用小时候的方式相处",
        assessment_criteria=("家长是否了解青春期典型的心理发展特征",),
        learning_goal="家长能识别青春期孩子对自主和隐私的正常需求",
        lessons=(
            _lesson(
                "lesson-1",
                1,
                "自主需求是发展信号",
                "对独立空间的需求是正常发展，不是叛逆",
                "给孩子一个不被打扰的独立空间",
            ),
        ),
        outcome_metrics=("因隐私/自主问题引发的冲突次数",),
    ),
    _DevCourseSpec(
        course_id="course-content-dev-harder-to-talk",
        system="青春期",
        title="青春期为什么越来越难沟通",
        problem_statement="孩子进入青春期后回应越来越少，家长觉得被拒之门外",
        assessment_criteria=("孩子主动发起对话的频率变化",),
        learning_goal="家长能调整沟通方式，减少说教式开场",
        lessons=(
            _lesson(
                "lesson-1",
                1,
                "减少说教式开场",
                "说教式开场是青春期对话最快被关闭的方式",
                "本周用一个非评判性问题开启对话",
            ),
        ),
        outcome_metrics=("孩子主动回应对话的比例",),
    ),
    _DevCourseSpec(
        course_id="course-content-dev-boundaries-and-freedom",
        system="青春期",
        title="青春期边界与自由",
        problem_statement="家长在管得太多和完全放手之间反复摇摆",
        assessment_criteria=("家庭规则是否随孩子年龄增长而调整",),
        learning_goal="家长能和孩子协商随年龄递增的自由与相应的责任",
        lessons=(
            _lesson(
                "lesson-1",
                1,
                "自由与责任对等",
                "扩大自由的同时需要匹配相应责任",
                "和孩子协商一项新增自由对应的责任",
            ),
        ),
        outcome_metrics=("协商达成的自由-责任约定数",),
    ),
    _DevCourseSpec(
        course_id="course-content-dev-from-managing-to-accompanying",
        system="青春期",
        title="从管理孩子到陪伴成长",
        problem_statement="家长的角色还停留在'管理者'，孩子已经需要'同行者'",
        assessment_criteria=("家长对孩子决定的介入程度",),
        learning_goal="家长能有意识地把决定权逐步交还给孩子",
        lessons=(
            _lesson(
                "lesson-1",
                1,
                "从决定到陪伴的角色转变",
                "角色转变需要家长主动松手，不会自然发生",
                "这周把一个小决定完全交给孩子",
            ),
        ),
        outcome_metrics=("完全由孩子自主决定的事项数",),
    ),
)


async def _publish_dev_course(spec: _DevCourseSpec) -> None:
    """Push one `_DevCourseSpec` through the real DRAFT -> UNDER_REVIEW ->
    PUBLISHED state machine — never by constructing a `CourseContent` already
    in `PUBLISHED` status. Idempotent per `spec.course_id`.

    Checking only the *published* list was not enough: this coroutine runs
    on every `_dev_family_need_actor` resolution (every request), and a
    process that crashes/times out partway through a previous seeding
    attempt (e.g. after `submit_content_for_review` but before
    `decide_content_review`) leaves the record in `UNDER_REVIEW` — not
    `PUBLISHED`, so the old guard missed it, and every subsequent request
    crashed forever trying to `submit_for_review()` a record that is no
    longer in `DRAFT`. Checking for the record's mere *existence* (any
    status) is the correct idempotency boundary for dev seed data: a
    partially-seeded fixture is still "already seeded", not "needs
    reseeding".
    """

    try:
        await _course_content_repository.load_course_content(spec.course_id, "dev")
        return
    except ProductIntelligenceNotFoundError:
        pass

    draft = await create_course_content_draft(
        _course_content_repository,
        _COURSE_AUTHOR_CONTEXT,
        title=spec.title,
        problem_statement=spec.problem_statement,
        assessment_criteria=list(spec.assessment_criteria),
        learning_goal=spec.learning_goal,
        lessons=list(spec.lessons),
        review_cadence="WEEKLY",
        outcome_metrics=list(spec.outcome_metrics),
        content_accuracy_claim_refs=[f"claim:dev-course:{spec.course_id}:v1"],
    )
    # Overwrite the generated id with the spec's stable id, then re-save
    # (create_course_content_draft already persisted the generated-id
    # version; this keeps exactly one record addressable by `spec.course_id`).
    stable_draft = draft.model_copy(update={"id": spec.course_id})
    await _course_content_repository.save_course_content(stable_draft)

    submission = await submit_course_content_for_review(
        _course_content_repository,
        _course_human_gate,
        _COURSE_AUTHOR_CONTEXT,
        course_content_id=spec.course_id,
    )
    await decide_course_content_review(
        _course_content_repository,
        _course_human_gate,
        _COURSE_REVIEWER_CONTEXT,
        task_id=submission.task.task_id,
        course_content_id=spec.course_id,
        approved=True,
        reason="dev seed: 内容审核通过，用于本地演示与测试",
    )


async def _seed_dev_published_course() -> None:
    """Seed the flagship "告别作业磨蹭" course plus the full 24-course
    blueprint catalog (`DEV_COURSE_CATALOG`) through the real publication
    state machine. Kept under its original name because existing call sites
    and tests already depend on it; it now seeds the whole catalog, not just
    one course.
    """

    await _publish_dev_course(
        _DevCourseSpec(
            course_id=DEV_SEEDED_COURSE_ID,
            system="学习成长",
            title="告别作业磨蹭",
            problem_statement="孩子做作业拖延，家长陪伴式督促力不从心",
            assessment_criteria=("作业开始拖延超过15分钟", "家长需反复催促才能推进"),
            learning_goal="孩子能在约定时间内独立开始并专注完成作业",
            lessons=(
                _lesson(
                    "lesson-1",
                    1,
                    "看懂拖延背后的信号",
                    "拖延常是任务感知过难或缺乏掌控感的表现",
                    "和孩子一起把作业拆成可完成的小步骤",
                ),
                _lesson(
                    "lesson-2",
                    2,
                    "建立可执行的开始仪式",
                    "固定的开始仪式能降低启动阻力",
                    "约定并练习一个3分钟的作业启动仪式",
                ),
            ),
            outcome_metrics=("作业启动延迟时长", "家长催促次数"),
        )
    )
    for spec in DEV_COURSE_CATALOG:
        await _publish_dev_course(spec)


async def _list_published_courses_for_dev() -> list:
    """Read-only seam `CourseSupplyAdapter` depends on; tenant-agnostic in
    dev because there is exactly one dev tenant scope ("dev") for the
    seeded course today."""

    return await _course_content_repository.list_published_course_content("dev")


# The supply port resolves PRODUCT-, SERVICE- and SOLUTION-shaped component
# references: PRODUCT against the same commerce catalogue the mobile
# PRODUCT journey uses (`ensure_mobile_product_master_data`), SERVICE
# against the same service repository the mobile SERVICE journey books
# against (`ensure_mobile_master_data`'s TEACHER_LI / TEACHER_ZHANG rows),
# SOLUTION against the one seeded, genuinely-published course
# (`_seed_dev_published_course`), so a solution draft can actually match
# real supply instead of always reporting a resource gap regardless of the
# profile's intervention tier.
_family_need_service = FamilyNeedApplicationService(
    _family_need_repository,
    _family_need_policy,
    supply_port=CompositeSupplyAdapter(
        commerce=CommerceSupplyAdapter(_commerce_repository),
        service=ServiceSupplyAdapter(_repository),
        course=CourseSupplyAdapter(_list_published_courses_for_dev),
    ),
)

# AI Coach: dev/test always use FakeProvider (deterministic, no network, not
# evidence of real generative behaviour — see
# `tests/intelligence/experience/test_family_ai_coach_real_model.py` for the
# gated real-DeepSeek verification path). This is the same
# fake-deterministic-by-default posture the assessment interpretation adapter
# above documents for the same governance reason: no external provider has
# cleared the §16 assessment for real family data.
_ai_coach_gateway = build_dev_ai_coach_gateway(environment="development")


def _dev_ai_coach_deps() -> family_need_ai_coach_deps.AiCoachDeps:
    # Reuses the same process-local `_journey_outcome_loop` the
    # complete-and-review/course-completion routes already write to (see
    # `_dev_fulfillment_deps` below), so the coach actually sees this
    # family's real growth history instead of an empty, newly-constructed
    # loop.
    return family_need_ai_coach_deps.AiCoachDeps(
        gateway=_ai_coach_gateway,
        repository=_family_need_repository,
        provider_id="fake-deterministic",
        outcome_loop=_journey_outcome_loop,
        memory_store=_coach_memory_store,
    )


# Same rationale for assessment: one repository per process so a session started
# by one request is findable by the next.
#
# The interpretation adapter is the deterministic one — not an AI path. That is
# deliberate, not a shortcut: routing dev traffic through a model would need the
# Model Gateway's provider admission, and no external provider is admissible
# today (every shipped provider record carries `sub_delegates=None`, which
# admission treats as forbidden under 《儿童个人信息网络保护规定》第16条). A
# deterministic interpretation keeps the chain runnable without pretending an AI
# path exists — see AI_NATIVE_PRINCIPLES §4 on deterministic fallback being
# necessary but never presentable as an AI capability.
_assessment_repository = FakeAssessmentRepository()
_assessment_interpretation = DeterministicInterpretationAdapter()

# Experience runs must survive separate HTTP requests in the synthetic
# composition just as they do in production persistence. Keep one explicit
# ledger per family for the process lifetime; the runtime scope still includes
# tenant and subject IDs, so a different family (or subject set) cannot read
# another family's run. ``reset_dev_state`` replaces this map for test
# isolation.
_experience_run_ledgers: dict[str, InMemoryExperienceRunLedger] = {}
# The synthetic resolver itself is request-scoped, so keep the test adapters in
# explicit family-keyed maps. This gives separate HTTP retries the same
# process-local context and draft registry without sharing state across families.
_experience_context_brokers: dict[str, ContextBroker] = {}
_experience_draft_registries: dict[str, InMemoryModelDraftRegistry] = {}
# One outcome loop for the process, same rationale as `_repository` above: a
# service-completion review recorded by one request must be readable by the
# next request that queries the family's journey.
_journey_outcome_loop = GrowthOutcomeLoop()


class _DevConsentQuery:
    """Synthesises a GRANTED consent for any subject in the acting family.

    **This is a consent bypass.** It exists because there is no consent store to
    read from, and the alternative (returning `[]`) makes every booking fail with
    a consent error that is indistinguishable from a genuine consent problem —
    the exact failure mode `dependencies.get_consent_query` calls out.

    It is honest about being synthetic: `consent_id` is prefixed `dev-synthetic:`
    so anything that logs or audits a grant shows where it came from, and the
    grant is minted per call rather than stored, so nothing can mistake it for
    recorded consent.
    """

    async def list_grants(
        self, *, tenant_id: str, subject_person_id: str, purpose: ConsentPurpose
    ) -> Sequence[ConsentGrant]:
        return [
            ConsentGrant(
                consent_id=f"dev-synthetic:{purpose.value}:{subject_person_id}",
                subject_person_id=subject_person_id,
                guardian_person_id=f"dev-guardian:{subject_person_id}",
                purpose=purpose,
                status=ConsentStatus.GRANTED,
                granted_at=datetime.now(UTC),
                subject_age=SubjectAge(10),
                guardian_relation=GuardianRelation.GUARDIAN,
            )
        ]


def _identity(authorization: str | None) -> dict[str, str]:
    """Resolve `{account_id, family_id}` from the dev bearer token.

    Rejects a missing or unknown token with 401 rather than inventing an
    identity — an unauthenticated caller must not acquire a family scope.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="authorization required")
    identity = get_dev_auth_state().tokens.get(authorization[7:])
    if not identity:
        raise HTTPException(status_code=401, detail="unknown or expired session")
    return identity


async def _dev_repository() -> FakeServiceRepository:
    return _repository


async def _dev_commerce_repository() -> FakeCommerceRepository:
    return _commerce_repository


def _dev_family_need_service() -> FamilyNeedApplicationService:
    return _family_need_service


async def _dev_consent_query() -> _DevConsentQuery:
    return _DevConsentQuery()


def _dev_fulfillment_deps() -> family_need_fulfillment_deps.FulfillmentDeps:
    """Wire the confirm-draft/complete-and-review routes to real (dev) domains.

    Reuses the same process-local `_repository` / `_commerce_repository` the
    mobile SERVICE/PRODUCT journeys and `family_need`'s own supply adapters
    already share, so a booking made through this flow is visible to the same
    `FakeServiceRepository` the ordinary SERVICE routes query.
    """

    return family_need_fulfillment_deps.FulfillmentDeps(
        commerce_repository=_commerce_repository,
        service_repository=_repository,
        consent_query=_DevConsentQuery(),
        audit_recorder=AuditRecorder(),
        outcome_loop=_journey_outcome_loop,
        fulfil_confirmed_draft=fulfil_confirmed_draft,
        course_content_repository=_course_content_repository,
        course_catalog_tenant_scope=DEV_COURSE_CATALOG_TENANT_SCOPE,
        family_need_repository=_family_need_repository,
        fgcn_provider_admission=_dev_fgcn_provider_admission,
        fgcn_session_factory=_dev_fgcn_session,
        improvement_candidate_repository=_improvement_candidate_repository,
        family_experience_signal_repository=_family_experience_signal_repository,
    )


async def _dev_action_context(
    authorization: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
) -> ActionContext:
    """Server-derived scope, taken from the session — never from path or body.

    That rule is `ActionContext`'s own reason for existing: a client command must
    not be able to name the family it acts for. `family_id` here comes from the
    token, and `routes._assert_path_family` then rejects a path that disagrees
    with it.
    """
    identity = _identity(authorization)
    await ensure_mobile_product_master_data(_commerce_repository)
    await ensure_mobile_master_data(_repository, identity["family_id"])
    return ActionContext(
        tenant_id=identity["family_id"],
        family_id=identity["family_id"],
        actor_person_id=identity["account_id"],
        actor=identity["account_id"],
        correlation_id=str(uuid4()),
        environment="DEV",
        idempotency_key=idempotency_key,
    )


async def _dev_actor_context(
    authorization: str | None = Header(default=None),
) -> ActorContext:
    """A dev session is always a HUMAN actor.

    Never `ActorType.AI`: the human-gated actions (`confirm_booking_request`,
    `fulfil_service_record`, `cancel_booking_request`) are denied unconditionally
    to AI actors by `PolicyEngine`, and issuing an AI actor here would make that
    denial look like a bug in the routes.
    """
    identity = _identity(authorization)
    return ActorContext(
        actor_id=identity["account_id"],
        actor_type=ActorType.HUMAN,
        tenant_id=identity["family_id"],
        correlation_id=str(uuid4()),
    )


def _dev_tenant_directory(
    authorization: str | None = Header(default=None),
) -> InMemoryTenantDirectory:
    """Every dev session's tenant is ACTIVE.

    `PolicyEngine` denies any actor whose tenant is not ACTIVE, resolving the
    status through a `TenantDirectory` whose production default denies
    everything (there is no tenant store — see
    `service/api/dependencies.get_tenant_directory`). Dev sessions derive
    `tenant_id` from `family_id` in the bearer token, so the only honest thing
    this can do is declare that synthetic tenant active.

    This is **not** tenant lifecycle. It has no suspension path and no store; a
    dev session cannot be suspended because nothing can suspend it. It is the
    same class of synthetic stand-in as `_DevConsentQuery` above, and it is
    installed only under the same environment guard.
    """
    identity = _identity(authorization)
    return InMemoryTenantDirectory({identity["family_id"]: TenantStatus.ACTIVE})


async def _dev_experience_runtime_resolver(
    authorization: str | None = Header(default=None),
    family_id: str = Path(...),
) -> SyntheticRuntimeResolver:
    """Resolve a request-scoped synthetic AI runtime from the dev session.

    ``family_id`` is a path parameter, but it is not trusted on its own: the
    bearer token remains the source of tenant/family/account identity. A token
    for another family is rejected before a resolver is returned, so the
    resolver cannot manufacture a runtime for an arbitrary URL. The two
    subjects are explicit synthetic identifiers: the authenticated guardian
    account and the named ``dev-child`` subject.

    This dependency is installed only by :func:`install_dev_wiring` after its
    positive environment guard. Production has no synthetic resolver override
    and therefore keeps the experience route fail-closed.
    """

    identity = _identity(authorization)
    if identity["family_id"] != family_id:
        raise HTTPException(status_code=403, detail="family access denied")
    ledger = _experience_run_ledgers.setdefault(
        family_id,
        InMemoryExperienceRunLedger(),
    )
    context_broker = _experience_context_brokers.setdefault(family_id, ContextBroker())
    draft_registry = _experience_draft_registries.setdefault(
        family_id,
        InMemoryModelDraftRegistry(),
    )
    return SyntheticRuntimeResolver(
        tenant_id=identity["family_id"],
        subject_ids=(identity["account_id"], f"dev-child:{identity['family_id']}"),
        environment="test",
        run_ledger=ledger,
        model_draft_subject_id=f"dev-child:{family_id}",
        model_draft_registry=draft_registry,
        context_broker=context_broker,
    )


async def _dev_engagement_runtime_resolver(
    authorization: str | None = Header(default=None),
    family_id: str = Path(...),
) -> SyntheticEngagementRuntimeResolver:
    """Resolve a synthetic Engagement runtime from the dev bearer session."""

    identity = _identity(authorization)
    if identity["family_id"] != family_id:
        raise HTTPException(status_code=403, detail="family access denied")
    return SyntheticEngagementRuntimeResolver(
        tenant_id=identity["family_id"],
        subject_ids=(identity["account_id"], f"dev-child:{family_id}"),
        environment="test",
    )


def install_dev_wiring(app: FastAPI) -> None:
    """Make the mounted SERVICE routes callable in a dev environment.

    Raises `DevWiringNotPermittedError` outside dev/test. Refusing rather than
    silently skipping is the point: a deployment that expected this wiring and
    did not get it should fail at startup, not serve endpoints that 500 later.
    """
    if not is_dev_environment():
        raise DevWiringNotPermittedError(
            f"dev wiring refused: {ENV_VAR}={current_environment()!r} is not one of "
            f"{sorted(DEV_ENVIRONMENTS)}. This module synthesises consent grants and "
            "uses an in-memory repository; it must never be reachable in production "
            "(R5: synthetic data must not masquerade as a business capability). "
            "Production requires a real session factory, a real consent store, and "
            "the Account -> TenantMembership -> Family binding chain."
        )

    app.dependency_overrides[service_deps.get_repository] = _dev_repository
    app.dependency_overrides[service_deps.get_consent_query] = _dev_consent_query
    app.dependency_overrides[service_deps.get_action_context] = _dev_action_context
    app.dependency_overrides[service_deps.get_actor_context] = _dev_actor_context
    app.dependency_overrides[service_deps.get_tenant_directory] = _dev_tenant_directory
    app.dependency_overrides[commerce_deps.get_repository] = _dev_commerce_repository
    app.dependency_overrides[family_need_deps.get_family_need_actor] = _dev_family_need_actor
    app.dependency_overrides[family_need_deps.get_family_need_service] = _dev_family_need_service
    app.dependency_overrides[family_need_fulfillment_deps.get_fulfillment_deps] = (
        _dev_fulfillment_deps
    )
    app.dependency_overrides[family_need_ai_coach_deps.get_ai_coach_deps] = _dev_ai_coach_deps
    app.dependency_overrides[get_multimodal_draft_runtime_resolver] = (
        _dev_experience_runtime_resolver
    )
    app.dependency_overrides[get_engagement_draft_runtime_resolver] = (
        _dev_engagement_runtime_resolver
    )

    # Assessment has the same four-raising-dependencies shape, for the same
    # reason, and had the same consequence: UI-02 → UI-03 is the one business
    # chain the functional decomposition marks "已实现可用", yet every route
    # returned 500 after the four-layer refactor moved handler construction out
    # of `api.py` and into dependencies that raise.
    #
    # Wiring it here rather than in the domain keeps the production path failing
    # closed, and keeps the claim in
    # docs/03_product/FUNCTIONAL_DECOMPOSITION.md honest — a functional
    # decomposition that calls an endpoint usable while it 500s is worse than one
    # that admits the gap.
    app.dependency_overrides[assessment_deps.get_family_context] = _dev_family_context
    app.dependency_overrides[assessment_deps.get_command_handler] = _dev_command_handler
    app.dependency_overrides[assessment_deps.get_query_handler] = _dev_query_handler
    app.dependency_overrides[assessment_deps.get_growth_hypothesis_handler] = (
        _dev_growth_hypothesis_handler
    )


async def _dev_family_context(
    authorization: str | None = Header(default=None),
) -> assessment_deps.FamilyContext:
    """Scope resolved from the bearer token, never from path or body.

    Same rule as `_dev_action_context`: a client must not be able to name the
    family it acts for. `dev_auth.resolve_actor` is the single place that turns a
    token into an identity, so both domains agree on who the caller is.
    """
    identity = _identity(authorization)
    tenant_id = identity["family_id"]
    family_id = identity["family_id"]
    person_id = identity["account_id"]

    # Seed the family on first sight of a session.
    #
    # `assert_tenant_family_scope` refuses a family with no tenant binding, and
    # in production that binding comes from the Account -> TenantMembership ->
    # Family chain (auth_identity, status: NOT_STARTED). With no such chain, a
    # dev session names a family the repository has never heard of and every
    # request answers `tenant_family_scope_denied` — indistinguishable from a
    # genuine authorization failure.
    #
    # Seeding here, keyed off an already-authenticated session, is narrower than
    # loosening the scope check: the check keeps working, including for the
    # cross-family case (a token for family-a still cannot reach family-b,
    # because the route compares the path against the token before this runs).
    if (tenant_id, family_id) not in _assessment_repository.tenant_family_bindings:
        _assessment_repository.seed_family(tenant_id, family_id)
    _assessment_repository.grant_family_manage_permission(
        family_id, person_id, role="OWNER_GUARDIAN"
    )

    return assessment_deps.FamilyContext(
        tenant_id=tenant_id,
        family_id=family_id,
        person_id=person_id,
    )


async def _dev_family_need_actor(
    authorization: str | None = Header(default=None),
) -> family_need_deps.FamilyNeedActor:
    """Resolve a synthetic guardian and seed only named test subjects.

    This is a test-data adapter, not an authorization shortcut. Production
    must replace it with the same route contract backed by account, family,
    subject and consent stores. The fixed ``dev-child:...`` subject makes the
    synthetic boundary explicit instead of accepting arbitrary child IDs.
    """

    identity = _identity(authorization)
    family_id = identity["family_id"]
    actor_id = identity["account_id"]
    child_id = f"dev-child:{family_id}"
    _family_need_policy.bind_family(identity["family_id"], family_id)
    _family_need_policy.grant_actor(family_id, actor_id, FamilyNeedActorType.FAMILY_GUARDIAN)
    _family_need_policy.add_subject(family_id, child_id)
    _family_need_policy.grant_consent(family_id, child_id, "FAMILY_NEED", "v1")
    # Seed the same real teacher offerings the mobile SERVICE journey books
    # against, so a Family Need solution draft can resolve a genuine supply
    # reference instead of always reporting a resource gap.
    await ensure_mobile_master_data(_repository, family_id)
    # Seed the same PRODUCT catalogue the mobile PRODUCT journey uses, so a
    # UNIVERSAL/LIGHT_GUIDANCE-tier solution draft can resolve a real
    # self-help product reference instead of always reporting a gap.
    await ensure_mobile_product_master_data(_commerce_repository)
    # Seed the one real, genuinely-published course ("告别作业磨蹭") through
    # the full DRAFT -> UNDER_REVIEW -> PUBLISHED Human Gate lifecycle, so a
    # SOLUTION-shaped solution draft can resolve a real course reference
    # instead of always reporting a gap.
    await _seed_dev_published_course()
    return family_need_deps.FamilyNeedActor(
        tenant_id=identity["family_id"],
        family_id=family_id,
        actor_id=actor_id,
        actor_type=FamilyNeedActorType.FAMILY_GUARDIAN,
    )


def _dev_command_handler() -> AssessmentCommandHandler:
    return AssessmentCommandHandler(_assessment_repository)


def _dev_query_handler() -> AssessmentQueryHandler:
    return AssessmentQueryHandler(_assessment_repository, _assessment_interpretation)


def _dev_growth_hypothesis_handler() -> GrowthHypothesisCommandHandler:
    return GrowthHypothesisCommandHandler(_assessment_repository, _assessment_interpretation)


def reset_dev_state() -> None:
    """Clear process-local state for both domains. For tests needing isolation.

    Resets assessment too: leaving its repository populated between tests is the
    same cross-test leak the service reset exists to prevent.

    For family_need / course_content / improvement_candidate /
    family_experience_signal, "clean state" now means the real
    `aifamily-dev-postgres` tables are truncated (`_truncate_dev_tables`), not
    that a fresh Python object replaces the old one — those four repositories
    are thin connection-scoped wrappers around the same cached `AsyncEngine`
    and do not need to be rebuilt on reset. The flagship seeded course is not
    re-inserted here: `_dev_family_need_actor` re-seeds it (idempotently, via
    `on conflict ... do update`) the next time any test resolves a family_need
    actor, mirroring how course/teacher/product master data was already
    re-seeded lazily per-request before this change.
    """
    global _repository, _commerce_repository, _assessment_repository
    global _family_need_policy, _family_need_service
    global _course_human_gate
    global _experience_run_ledgers, _experience_context_brokers, _experience_draft_registries
    global _journey_outcome_loop
    _truncate_dev_tables()
    _repository = FakeServiceRepository()
    _commerce_repository = FakeCommerceRepository()
    _family_need_policy = FakeFamilyNeedPolicy()
    _course_human_gate = InMemoryHumanGate()
    _family_need_service = FamilyNeedApplicationService(
        _family_need_repository,
        _family_need_policy,
        supply_port=CompositeSupplyAdapter(
            commerce=CommerceSupplyAdapter(_commerce_repository),
            service=ServiceSupplyAdapter(_repository),
            course=CourseSupplyAdapter(_list_published_courses_for_dev),
        ),
    )
    _assessment_repository = FakeAssessmentRepository()
    # `_dev_ai_coach_deps` reads `_family_need_repository` at call time, so
    # reassigning the global above is sufficient; the gateway itself is
    # stateless FakeProvider wiring and does not need to be rebuilt.
    _experience_run_ledgers = {}
    _experience_context_brokers = {}
    _experience_draft_registries = {}
    _journey_outcome_loop = GrowthOutcomeLoop()
