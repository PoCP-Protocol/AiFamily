"""FastAPI dependencies for the membership domain.

Three of these deliberately raise instead of returning a default.

`get_repository` has no session factory to hand out yet. `get_action_context`
and `get_actor_context` have no way to resolve `(tenant, family, actor)` from a
request: the Account → TenantMembership → Family binding chain is a later
capability (`governance/DOMAIN_REGISTRY.yaml` → `family_core`, `auth_identity`).
A "sensible default" for any of them would be an authorization hole that fails
*open* — handing out some tenant/family instead of refusing. Tests supply them
via `app.dependency_overrides`; that is the intended mechanism, and it is why
production code must not grow test-friendly defaults.

The policy engine is registered here rather than inline in the routes so that
the set of high-impact, human-gated actions is one readable list. It fails
closed, so a route performing an unregistered action returns 403 — a forgotten
registration breaks the feature loudly instead of silently permitting it.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends

from backend.platform.audit.recorder import AuditRecorder
from backend.platform.authorization.policy import PolicyEngine, PolicyRule
from backend.platform.identity.context import ActorContext, ActorType
from backend.platform.identity.directory import DenyAllTenantDirectory, TenantDirectory

from ..application.context import ActionContext
from ..application.ports import MembershipRepositoryPort
from ..infrastructure.sqlalchemy_repository import SqlAlchemyMembershipRepository

_session_factory = None  # set by the owning app at startup; not configured yet

MEMBERSHIP_RESOURCE = "membership"
BENEFIT_RESOURCE = "membership_benefit"

# Actions R8 classifies as high-impact and therefore human-gated. 会员升级 is
# named explicitly in that rule's list; renewal and expiry move the same tier
# state, and revocation takes something away from a family, so they are gated on
# the same grounds rather than on a narrower reading of the word "升级".
HUMAN_GATED_ACTIONS: frozenset[str] = frozenset(
    {
        "activate_membership_tier",
        "renew_membership_period",
        "expire_membership_period",
        "revoke_membership_benefit",
    }
)

_NON_GATED_ACTIONS: dict[str, str] = {
    "subscribe_membership": MEMBERSHIP_RESOURCE,
    "grant_membership_benefit": BENEFIT_RESOURCE,
    "reserve_membership_benefit": BENEFIT_RESOURCE,
    "release_membership_benefit_reservation": BENEFIT_RESOURCE,
    "consume_membership_benefit": BENEFIT_RESOURCE,
}


def resource_for(action: str) -> str:
    if action in _NON_GATED_ACTIONS:
        return _NON_GATED_ACTIONS[action]
    return BENEFIT_RESOURCE if action == "revoke_membership_benefit" else MEMBERSHIP_RESOURCE


def build_policy_engine(tenant_directory: TenantDirectory) -> PolicyEngine:
    """Register this domain's rules onto an engine bound to `tenant_directory`.

    The directory is a required argument, not a default: `PolicyEngine` denies
    every actor whose tenant is not ACTIVE, and it needs somewhere to look that
    up. Passing it in (rather than letting the engine invent one) keeps the
    production path fail-closed — see `get_tenant_directory` below.
    """
    engine = PolicyEngine(tenant_directory)
    human_and_system = frozenset({ActorType.HUMAN, ActorType.SYSTEM})

    for action, resource in _NON_GATED_ACTIONS.items():
        engine.register(
            PolicyRule(action=action, resource_type=resource, allowed_actor_types=human_and_system)
        )

    for action in sorted(HUMAN_GATED_ACTIONS):
        engine.register(
            PolicyRule(
                action=action,
                resource_type=resource_for(action),
                allowed_actor_types=frozenset({ActorType.HUMAN}),
                human_only=True,
            )
        )

    # Reads are family-scoped by construction (scope comes from the context,
    # never from the URL), so an AI actor may read a projection for the family
    # it is already acting within. It still cannot write anything.
    engine.register(
        PolicyRule(action="read_membership_projection", resource_type=MEMBERSHIP_RESOURCE)
    )
    return engine


_audit_recorder = AuditRecorder()


async def get_repository() -> AsyncGenerator[MembershipRepositoryPort, None]:
    if _session_factory is None:
        raise RuntimeError("membership session factory not configured — no owning app exists yet")
    async with _session_factory() as session:  # pragma: no cover - no app yet
        yield SqlAlchemyMembershipRepository(session)


async def get_action_context() -> ActionContext:
    raise RuntimeError(
        "membership action context resolver not configured — must be derived from the "
        "authenticated session (tenant/family/actor), never from the request body"
    )


async def get_actor_context() -> ActorContext:
    raise RuntimeError(
        "membership actor context resolver not configured — must be derived from the "
        "authenticated session; a default actor would fail open"
    )


def get_tenant_directory() -> TenantDirectory:
    """Where tenant status comes from. Fourth fail-closed dependency.

    Returns `DenyAllTenantDirectory` because this repository has no tenant store
    yet — the Account -> TenantMembership -> Family chain
    (`governance/DOMAIN_REGISTRY.yaml` -> `auth_identity`, status NOT_STARTED) is
    where real tenant lifecycle will live. Unlike the other three, this one does
    not raise: an unknown tenant is a legitimate *authorization* answer (DENY),
    not a configuration fault, and `PolicyEngine` already reports it as such with
    a reason string that names the tenant. Raising here would turn every request
    into a 500 and lose that distinction.

    Overridden via `app.dependency_overrides` by dev wiring and tests, the same
    mechanism the other three use.
    """
    return DenyAllTenantDirectory()


def get_policy_engine(
    tenant_directory: TenantDirectory = Depends(get_tenant_directory),
) -> PolicyEngine:
    """Built per request, bound to the resolved tenant directory.

    Not a module-level singleton any more: the engine now holds a tenant
    directory, and a process-wide instance built at import time would freeze
    whatever directory existed then — including in an app whose dev wiring
    installs a different one afterwards. Rule registration is a handful of
    dataclass appends, so rebuilding is cheaper than the bug.
    """
    return build_policy_engine(tenant_directory)


def get_audit_recorder() -> AuditRecorder:
    return _audit_recorder
