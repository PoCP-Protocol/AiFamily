"""Composition helpers for the Product Factory draft API.

The application factory owns when these helpers run.  Mounting the router
advertises the stable Web contract, while the domain dependencies continue to
fail closed until trusted identity and an explicit database session factory
are installed.
"""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.apps.family_api.product_factory_identity import (
    PermissionResolver,
    ProductFactoryBearerActorResolver,
    TenantScopeResolver,
)
from backend.domains.product_intelligence.api import (
    product_definition_review_routes,
    product_factory_routes,
)
from backend.domains.product_intelligence.api.dependencies import (
    ActorResolver,
    clear_actor_resolver,
    clear_session_factory,
    configure_actor_resolver,
    configure_session_factory,
)
from backend.domains.product_intelligence.api.product_definition_review_dependencies import (
    clear_product_definition_review_session_factory,
    configure_product_definition_review_session_factory,
)
from backend.platform.identity.session_port import IdentitySessionPort


def mount_product_factory_router(application: FastAPI) -> None:
    """Mount the Product Factory draft endpoints exactly once.

    Composition roots may be assembled by more than one environment adapter
    (for example, a test harness and the production factory).  Treat a second
    invocation as a no-op so route registration cannot silently duplicate
    OpenAPI operations or request dispatch entries.
    """

    for domain_router in (
        product_factory_routes.router,
        product_definition_review_routes.router,
    ):
        if any(
            getattr(route, "original_router", None) is domain_router for route in application.routes
        ):
            continue
        expected = {(route.path, frozenset(route.methods or ())) for route in domain_router.routes}
        registered = {
            (
                getattr(route, "path", None),
                frozenset(getattr(route, "methods", None) or ()),
            )
            for route in application.routes
        }
        if expected and not expected.issubset(registered):
            application.include_router(domain_router)


def install_product_factory_session_factory(
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> None:
    """Bind an explicit app-owned async session factory for production."""

    configure_session_factory(session_factory)
    configure_product_definition_review_session_factory(session_factory)


def clear_product_factory_session_factory() -> None:
    """Clear Product Factory persistence wiring between app instances/tests."""

    clear_session_factory()
    clear_product_definition_review_session_factory()


def install_product_factory_actor_resolver(
    resolver: ActorResolver,
) -> None:
    """Install the owning app's trusted request-to-actor bridge."""

    configure_actor_resolver(resolver)


def clear_product_factory_actor_resolver() -> None:
    """Clear identity wiring between app instances/tests."""

    clear_actor_resolver()


def install_product_factory_bearer_identity(
    session_port: IdentitySessionPort,
    tenant_scope_resolver: TenantScopeResolver,
    permission_resolver: PermissionResolver | None = None,
) -> None:
    """Compose the standard Bearer-to-ActorContext bridge for the app."""

    install_product_factory_actor_resolver(
        ProductFactoryBearerActorResolver(
            session_port=session_port,
            tenant_scope_resolver=tenant_scope_resolver,
            permission_resolver=permission_resolver,
        )
    )


__all__ = [
    "clear_product_factory_actor_resolver",
    "clear_product_factory_session_factory",
    "install_product_factory_actor_resolver",
    "install_product_factory_bearer_identity",
    "install_product_factory_session_factory",
    "mount_product_factory_router",
]
