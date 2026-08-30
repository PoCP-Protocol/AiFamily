"""Dev-only wiring that makes the mounted SERVICE / MEMBERSHIP routes callable.

## The problem this solves

`backend/domains/service/api/dependencies.py` has four dependencies that raise
by design — `get_repository`, `get_consent_query`, `get_action_context`,
`get_actor_context`. That design is correct and this module does not change it:
a "sensible default" inside those functions would be an authorization hole that
fails *open*, and its own docstring says so.

But the consequence today is that the six Batch 2 SERVICE endpoints are mounted,
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

import os
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import FastAPI, Header, HTTPException

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
from backend.domains.service.api import dependencies as service_deps
from backend.domains.service.application.context import ActionContext
from backend.domains.service.infrastructure.fake_repository import FakeServiceRepository
from backend.platform.consent.models import ConsentGrant, ConsentPurpose, ConsentStatus
from backend.platform.identity.context import ActorContext, ActorType

ENV_VAR = "AIFAMILY_ENV"
DEV_ENVIRONMENTS = frozenset({"development", "dev", "test", "local"})
"""Environments this wiring may be installed in.

Deliberately a positive list, not "anything except production": a typo in the
env var (`AIFAMILY_ENV=prod-eu`) must fall on the refusing side, not the
installing side.
"""


def current_environment() -> str:
    return os.environ.get(ENV_VAR, "development").strip().lower()


def is_dev_environment() -> bool:
    return current_environment() in DEV_ENVIRONMENTS


class DevWiringNotPermittedError(RuntimeError):
    """Raised when dev wiring is asked to install outside a dev environment."""


# One repository for the process, so a booking submitted by one request is
# visible to the next. A per-request instance would make every read return
# empty and look like a persistence bug.
_repository = FakeServiceRepository()

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
                guardian_person_id=subject_person_id,
                purpose=purpose,
                status=ConsentStatus.GRANTED,
                granted_at=datetime.now(UTC),
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


async def _dev_consent_query() -> _DevConsentQuery:
    return _DevConsentQuery()


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

    # The browser slice needs one explicit synthetic beneficiary in order to
    # exercise the real assessment route.  Keep this fixture in dev wiring,
    # not in the domain or a second consent implementation: `seed_subject`
    # populates the fake repository's existing subject/consent test boundary,
    # and the stable UUID makes the fixture safe to replay for one family.
    if not _assessment_repository.subjects.get(family_id):
        synthetic_subject_id = str(
            uuid5(NAMESPACE_URL, f"aifamily:{family_id}:assessment-subject")
        )
        _assessment_repository.seed_subject(
            family_id,
            synthetic_subject_id,
            "家庭成员（合成）",
            consent_granted=True,
        )
    for focus_ref, need_type_ref, title, description in (
        (
            "LEARNING_HABITS",
            "NEED_LEARNING_HABITS",
            "学习开始与节奏",
            "先从一个固定的开始时刻做一个小调整。",
        ),
        (
            "EMOTION_REGULATION",
            "NEED_EMOTION_REGULATION",
            "情绪起伏时的缓冲",
            "先留出一点缓冲，再一起确认当下最难的部分。",
        ),
        (
            "PARENT_CHILD_COMMUNICATION",
            "NEED_PARENT_CHILD_COMMUNICATION",
            "亲子沟通支持",
            "先从倾听开始，再一起找一个可尝试的小约定。",
        ),
        (
            "DEVICE_USE_CONTEXT",
            "NEED_DEVICE_USE_CONTEXT",
            "屏幕使用边界",
            "先把一个具体时刻说清楚，再试一个双方都知道的边界。",
        ),
        (
            "SELF_REGULATION",
            "NEED_SELF_REGULATION",
            "家庭节奏与自我管理",
            "先选择一个容易做到的时刻，建立可回看的小节奏。",
        ),
    ):
        if focus_ref not in _assessment_repository.need_types:
            _assessment_repository.seed_need_type(
                focus_ref,
                need_type_ref,
                title,
                description,
                ["LISTENING_COACH"],
            )

    return assessment_deps.FamilyContext(
        tenant_id=tenant_id,
        family_id=family_id,
        person_id=person_id,
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
    """
    global _repository, _assessment_repository
    _repository = FakeServiceRepository()
    _assessment_repository = FakeAssessmentRepository()
