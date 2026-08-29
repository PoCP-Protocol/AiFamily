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

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..application.context import ActorContext
from ..application.ports import ProductIntelligenceRepositoryPort
from ..infrastructure.sqlalchemy_repository import SqlAlchemyProductIntelligenceRepository
from ..infrastructure.unit_of_work import SqlAlchemyUnitOfWork

_session_factory = None  # set by the owning app at startup; not configured in this PR


async def get_actor_context(request: Request) -> ActorContext:
    """Fails closed: no real authentication exists yet for this domain.
    A future PR wiring real identity/auth must implement this, not this
    domain — see module docstring.
    """
    raise RuntimeError(
        "get_actor_context is not implemented — no real authentication exists yet for "
        "domains/product_intelligence; do not fall back to trusting a request header or "
        "body field for actor identity/tenant_scope (see api/requests.py docstring)"
    )


async def get_repository() -> AsyncGenerator[ProductIntelligenceRepositoryPort, None]:
    if _session_factory is None:
        raise RuntimeError("product_intelligence session factory not configured — no owning app exists yet")
    async with _session_factory() as session:  # type: AsyncSession
        async with SqlAlchemyUnitOfWork(session):
            yield SqlAlchemyProductIntelligenceRepository(session)
