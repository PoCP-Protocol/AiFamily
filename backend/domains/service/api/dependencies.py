"""FastAPI dependencies for the service booking domain.

Four of these deliberately raise instead of returning a default.

`get_repository`, `get_consent_query`, `get_action_context` and
`get_actor_context` have nothing to resolve from yet: no session factory is
wired, and the Account → TenantMembership → Family binding chain that answers
"which family is this caller acting for" is a later capability
(`governance/DOMAIN_REGISTRY.yaml` → `family_core`, `auth_identity`). A "sensible
default" for any of them would be an authorization hole that fails *open* —
handing out some tenant/family, or an empty consent list that a buggy gate might
read as "nothing withheld". Tests supply them via `app.dependency_overrides`;
that is the intended mechanism, and it is why production code must not grow
test-friendly defaults.

`get_consent_query` raising is the load-bearing one. An implementation that
returned `[]` would be *safer* than a wrong grant (the gate would refuse
everything), but it would also mean a misconfigured deployment silently refuses
every booking with a consent error, which is indistinguishable from a genuine
consent problem. Failing at the dependency names the actual fault.

The policy engine is registered here rather than inline in the routes so the set
of human-gated actions is one readable list. It fails closed, so a route
performing an unregistered action returns 403 — a forgotten registration breaks
the feature loudly instead of silently permitting it.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends

from backend.platform.audit.recorder import AuditRecorder
from backend.platform.authorization.policy import PolicyEngine, PolicyRule
from backend.platform.identity.context import ActorContext, ActorType
from backend.platform.identity.directory import DenyAllTenantDirectory, TenantDirectory

from ..application.context import ActionContext
from ..application.live_ports import LiveSessionReadPort
from ..application.ports import ConsentQueryPort, ServiceRepositoryPort
from ..infrastructure.sqlalchemy_repository import SqlAlchemyServiceRepository

_session_factory = None  # set by the owning app at startup; not configured yet

SERVICE_SUPPLY_RESOURCE = "service_supply"
SERVICE_BOOKING_RESOURCE = "service_booking"

# Actions R8 classifies as high-impact. Confirming a booking commits a named
# human being's time and fulfilling one asserts that a service was delivered;
# both are decisions a family or an operator must own, so an AI actor is denied
# unconditionally by the engine's own `human_only` override rather than by
# convention of what got registered.
HUMAN_GATED_ACTIONS: frozenset[str] = frozenset(
    {
        "confirm_booking_request",
        "fulfil_service_record",
        "cancel_booking_request",
    }
)

_NON_GATED_ACTIONS: dict[str, str] = {
    "register_service_provider": SERVICE_SUPPLY_RESOURCE,
    "publish_service_offering": SERVICE_SUPPLY_RESOURCE,
    "open_availability_slot": SERVICE_SUPPLY_RESOURCE,
    "submit_booking_request": SERVICE_BOOKING_RESOURCE,
    "create_private_checkin_draft": SERVICE_BOOKING_RESOURCE,
}

_READ_ACTIONS: dict[str, str] = {
    "read_service_supply": SERVICE_SUPPLY_RESOURCE,
    "read_service_booking": SERVICE_BOOKING_RESOURCE,
    "read_live_session": SERVICE_BOOKING_RESOURCE,
}


def resource_for(action: str) -> str:
    if action in _NON_GATED_ACTIONS:
        return _NON_GATED_ACTIONS[action]
    if action in _READ_ACTIONS:
        return _READ_ACTIONS[action]
    return SERVICE_BOOKING_RESOURCE


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

    # Reads are scoped by construction (scope comes from the context, never the
    # URL), so an AI actor may read within the family it is already acting for.
    # It still cannot write anything.
    for action, resource in _READ_ACTIONS.items():
        engine.register(PolicyRule(action=action, resource_type=resource))
    return engine


_audit_recorder = AuditRecorder()


async def get_repository() -> AsyncGenerator[ServiceRepositoryPort, None]:
    if _session_factory is None:
        raise RuntimeError("service session factory not configured — no owning app exists yet")
    async with _session_factory() as session:  # pragma: no cover - no app yet
        yield SqlAlchemyServiceRepository(session)


async def get_consent_query() -> ConsentQueryPort:
    raise RuntimeError(
        "service consent query not configured — consent grants must be read from live "
        "state on every booking; an empty default would report a configuration fault "
        "as a consent refusal"
    )


async def get_live_session_read_port() -> LiveSessionReadPort:
    """Resolve the canonical live-session read adapter, fail-closed by default.

    H-LIVE-01 is a read-only contract.  Returning a fixture here would make a
    production process appear to have live-session data, so composition must
    explicitly provide the adapter (tests override this dependency).
    """
    raise RuntimeError(
        "service live-session read port not configured — no synthetic or implicit "
        "live-session source is allowed"
    )


async def get_action_context() -> ActionContext:
    raise RuntimeError(
        "service action context resolver not configured — must be derived from the "
        "authenticated session (tenant/family/actor), never from the request path or body"
    )


async def get_actor_context() -> ActorContext:
    raise RuntimeError(
        "service actor context resolver not configured — must be derived from the "
        "authenticated session; a default actor would fail open"
    )


def get_tenant_directory() -> TenantDirectory:
    """Where tenant status comes from. Fifth fail-closed dependency.

    Returns `DenyAllTenantDirectory` because this repository has no tenant store
    yet — the Account → TenantMembership → Family chain
    (`governance/DOMAIN_REGISTRY.yaml` → `auth_identity`, status NOT_STARTED) is
    where real tenant lifecycle will live. Unlike the other four, this one does
    not raise: an unknown tenant is a legitimate *authorization* answer (DENY),
    not a configuration fault, and `PolicyEngine` already reports it as such with
    a reason string that names the tenant. Raising here would turn every request
    into a 500 and lose that distinction.

    Overridden via `app.dependency_overrides` by dev wiring and tests, the same
    mechanism the other four use.
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
