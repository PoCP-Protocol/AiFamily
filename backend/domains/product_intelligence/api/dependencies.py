"""FastAPI dependency wiring for this domain's repository port and actor
context.

Not included in any app yet — `apps/family_api` (per
`architecture/FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md` section 2) has not
been bootstrapped by any batch as of this PR. This module is real and
importable/testable on its own (see `tests/`), but `router` in `routes.py`
is not mounted anywhere until an app exists to mount it into.

PR-001R (chief-architect review on PR #27, item 3): `get_actor_context`
is the ONLY place a real app should ever obtain an `ActorContext` from —
never from request-body fields (see `api/requests.py`'s docstring). This
PR does not implement real authentication (no JWT/session verification
exists yet in this domain, or anywhere in `apps/`), so this dependency
fails closed with `RuntimeError` rather than trusting a header or
accepting an unauthenticated default. Whichever future PR adds real
identity/auth (per the Python-only migration plan's `identity` domain)
must replace this function's body, not add a fallback branch here.

PR-001R item 6: `get_repository` now wraps the session in
`SqlAlchemyUnitOfWork` so a successful request commits once, and any
unhandled exception rolls back — the repository's own `save_*` calls no
longer commit.
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncGenerator, Awaitable, Callable

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..application.context import ActorContext
from ..application.ports import ProductIntelligenceRepositoryPort
from ..infrastructure.sqlalchemy_repository import SqlAlchemyProductIntelligenceRepository
from ..infrastructure.unit_of_work import SqlAlchemyUnitOfWork

_session_factory: async_sessionmaker[AsyncSession] | None = None
ActorResolver = Callable[[Request], ActorContext | Awaitable[ActorContext]]
_actor_resolver: ActorResolver | None = None


def configure_session_factory(
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> None:
    """Install the owning application's explicit async session factory.

    Product Intelligence never chooses a local fallback database.  The
    composition root must call this setter during startup and may clear it
    when an app instance is torn down or has no configured database.
    """

    global _session_factory
    _session_factory = session_factory


def clear_session_factory() -> None:
    """Remove process wiring so a later app cannot inherit stale state."""

    configure_session_factory(None)


def configure_actor_resolver(resolver: ActorResolver | None) -> None:
    """Install an app-owned request identity bridge.

    The resolver must derive ``ActorContext`` from trusted authentication and
    tenant binding.  No header, query parameter, or request body is accepted
    as an identity fallback.
    """

    global _actor_resolver
    if resolver is not None and not callable(resolver):
        raise TypeError("actor resolver must be callable")
    _actor_resolver = resolver


def clear_actor_resolver() -> None:
    """Remove process wiring so later app instances cannot inherit identity."""

    configure_actor_resolver(None)


async def get_actor_context(request: Request) -> ActorContext:
    """Fails closed: no real authentication exists yet for this domain.
    A future PR wiring real identity/auth must implement this, not this
    domain — see module docstring.
    """
    resolver = _actor_resolver
    if resolver is None:
        raise RuntimeError(
            "get_actor_context is not implemented — no real authentication exists yet for "
            "domains/product_intelligence; do not fall back to trusting a request header or "
            "body field for actor identity/tenant_scope (see api/requests.py docstring)"
        )
    context = resolver(request)
    if inspect.isawaitable(context):
        context = await context
    if not isinstance(context, ActorContext):
        raise RuntimeError(
            "configured product_intelligence actor resolver returned invalid context"
        )
    return context


async def get_repository() -> AsyncGenerator[ProductIntelligenceRepositoryPort, None]:
    if _session_factory is None:
        raise RuntimeError(
            "product_intelligence session factory not configured — no owning app exists yet"
        )
    async with (
        _session_factory() as session,
        SqlAlchemyUnitOfWork(session),
    ):
        yield SqlAlchemyProductIntelligenceRepository(session)


__all__ = [
    "ActorResolver",
    "clear_actor_resolver",
    "clear_session_factory",
    "configure_actor_resolver",
    "configure_session_factory",
    "get_actor_context",
    "get_repository",
]
