"""FastAPI dependencies for the service booking and live read boundaries.

The booking dependencies deliberately raise instead of returning a default:
there is no session factory or authenticated family resolver in this baseline.
H-LIVE-01 adds its canonical projection seam below without changing any
booking or AvailabilitySlot semantics.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException

from backend.platform.audit.recorder import AuditRecorder
from backend.platform.authorization.policy import PolicyEngine, PolicyRule
from backend.platform.identity.context import ActorContext, ActorType
from backend.platform.identity.directory import DenyAllTenantDirectory, TenantDirectory

from ..application.context import ActionContext
from ..application.live_ports import LiveSessionProjectionPort
from ..application.ports import ConsentQueryPort, ServiceRepositoryPort
from ..infrastructure.sqlalchemy_repository import SqlAlchemyServiceRepository

_session_factory = None  # set by the owning app at startup; not configured yet

SERVICE_SUPPLY_RESOURCE = "service_supply"
SERVICE_BOOKING_RESOURCE = "service_booking"

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


# H-LIVE-01: this dependency is intentionally unavailable until Route B wires a
# real canonical projection provider. It must not return a local fixture.
LIVE_SESSION_RESOURCE = "live_session"
READ_LIVE_SESSION_ACTION = "read_live_session_detail"


def get_live_projection() -> LiveSessionProjectionPort:
    """Fail closed until Route B supplies a real canonical projection provider."""

    raise HTTPException(status_code=503, detail="live_projection_not_configured")


def get_live_policy_engine() -> PolicyEngine:
    """Return the explicit live read policy without changing booking policy."""

    engine = PolicyEngine()
    engine.register(
        PolicyRule(action=READ_LIVE_SESSION_ACTION, resource_type=LIVE_SESSION_RESOURCE)
    )
    return engine
