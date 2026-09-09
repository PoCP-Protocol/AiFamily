"""Composition root for the identity HTTP dependency seam.

Mirrors `domains/family_need/infrastructure/wiring.py`: installs a real,
Postgres-capable repository behind the same 4-endpoint contract dev/test and
production both use. There is no separate "fake" HTTP-facing runtime the way
`family_need` has one, because the whole point of this migration
(ADR-0011 §4, `governance/DOMAIN_REGISTRY.yaml` -> `auth_identity.known_gaps`)
was to stop the session store from being a process-local dict; a fake runtime
that reintroduced one would defeat that.

``engine_factory`` is a callable, not a bound ``AsyncEngine``, because
Starlette's ``TestClient`` opens a **new event loop per request** (see
``backend/apps/family_api/dev_wiring.py::_get_dev_engine`` for the fuller
explanation) and an asyncpg connection is bound to the loop that opened it.
For a shared SQLite ``StaticPool`` engine (the fast test/dev path) that does
not matter and the same engine may be returned every call; for a real
Postgres engine the caller must return a fresh, ``NullPool`` engine per call
and this module disposes it after the request.

Both installers are synchronous — ``create_app()`` (the composition root that
calls them) is itself synchronous and must not open an event loop of its own
to run setup coroutines (`asyncio.run`/`get_event_loop().run_until_complete`
inside a sync factory that may later run under an already-running loop is
exactly the "asyncio.run() cannot be called from a running event loop" trap).
Table creation for the SQLite fast path is therefore deferred to the first
actual request, inside the dependency callable itself, not performed eagerly
at wiring time.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from ..api import dependencies as identity_deps
from ..application.service import IdentityApplicationService
from .dev_auth_bridge import DevAuthMirroringIdentityService
from .sqlalchemy_models import Base
from .sqlalchemy_repository import SqlAlchemyIdentityRepository

EngineFactory = Callable[[], AsyncEngine]


async def ensure_identity_tables(engine: AsyncEngine) -> None:
    """Idempotent `CREATE TABLE IF NOT EXISTS` for the SQLite dev/fast path.

    Real Postgres deployments reuse the legacy baseline's `accounts` /
    `identity_sessions` tables plus the additive
    `database/migrations/versions/0071_identity_sessions_family_scope_ref.py`
    migration instead — this helper only runs against the in-memory/dev
    engine so tests do not need Alembic (or the legacy baseline) applied
    first, same convention `dev_wiring.py` and `tests/conftest.py` already
    use for other domains' fast SQLite path.
    """

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def install_identity_wiring(
    app: FastAPI,
    *,
    engine_factory: EngineFactory,
    ensure_tables: bool = False,
    mirror_into_dev_auth: bool = False,
) -> None:
    """Install a per-request `AsyncSession`-backed identity service.

    One session backs the repository for the duration of a single
    request/response cycle, same unit-of-work convention
    `SqlAlchemyMembershipRepository`/`SqlAlchemyServiceRepository` use. The
    engine itself is re-resolved via `engine_factory` on every call rather
    than captured once, so a Postgres-backed factory can hand out a fresh,
    disposable engine per request (see module docstring).

    `ensure_tables=True` runs `ensure_identity_tables` once, lazily, on the
    first request this dependency serves — correct for the SQLite fast path,
    a no-op-if-already-run guard for repeated calls within the same process.
    Real Postgres wiring must leave this `False` and rely on the Alembic
    migration instead.

    `mirror_into_dev_auth=True` wraps the service in
    `DevAuthMirroringIdentityService` (see that module's docstring for why:
    `dev_wiring.py`'s `_identity` helper and several other dev-only
    dependants still read `dev_auth`'s process-local token dict directly, not
    through this domain). Production wiring must leave this `False` — the
    mirror imports `backend.domains.assessment`, which a production identity
    service must not depend on.
    """

    tables_ready = not ensure_tables

    async def resolve_service() -> IdentityApplicationService:
        nonlocal tables_ready
        engine = engine_factory()
        if not tables_ready:
            await ensure_identity_tables(engine)
            tables_ready = True
        session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=engine, expire_on_commit=False
        )
        async with session_factory() as session:
            repository = SqlAlchemyIdentityRepository(session)
            service = IdentityApplicationService(repository)
            if mirror_into_dev_auth:
                service = DevAuthMirroringIdentityService(service)
            yield service

    app.dependency_overrides[identity_deps.get_identity_service] = resolve_service


def install_identity_dev_wiring(app: FastAPI, *, engine: AsyncEngine) -> None:
    """Dev/test wiring against a single shared engine (the SQLite fast path).

    `engine_factory` always returns the same, already-open `engine` — correct
    for the in-memory SQLite `StaticPool` engine, which has no per-loop
    connection binding to worry about. Tables are created lazily on first use
    (`ensure_tables=True`) rather than eagerly here, since this function is
    synchronous and must not open its own event loop (see module docstring).
    Mirrors into `dev_auth`'s shared dict (`mirror_into_dev_auth=True`) — see
    `install_identity_wiring`'s docstring for why.
    """

    install_identity_wiring(
        app, engine_factory=lambda: engine, ensure_tables=True, mirror_into_dev_auth=True
    )


__all__ = [
    "EngineFactory",
    "ensure_identity_tables",
    "install_identity_dev_wiring",
    "install_identity_wiring",
]
