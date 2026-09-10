"""R0.5 Case 02 regression: an ephemeral database's engine must be fully,
awaitably disposed before the database backing it is dropped.

`clear_engine_cache()` is a synchronous, best-effort cache reset — it does
not await the underlying driver-level connection close (see its docstring
in `session.py`). A fixture that drops an ephemeral Postgres database after
only calling `clear_engine_cache()` can leave an async resource (a pending
asyncpg connection tied to the disposed-but-not-awaited `AsyncEngine`)
alive past the database's destruction. That leaked resource's exception
then surfaces during an unrelated, later test — exactly the
`journey_e2e_*` / `test_course_release_baseline_routes.py` order-dependency
failure diagnosed in `docs/06_platform/R0_5_ORDER_DEPENDENCY_FINDINGS.md`.

`dispose_cached_engine(url)` exists to close that gap: it pops exactly one
cached engine and awaits its `dispose()` directly, so the caller can prove
the engine is closed before proceeding to drop the database.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from backend.platform.persistence import session as session_module
from backend.platform.persistence.session import (
    clear_engine_cache,
    dispose_cached_engine,
    get_engine,
)


def _url(n: int) -> str:
    return f"sqlite+aiosqlite:///:memory:?ephemeral_disposal_test={n}"


@pytest.fixture(autouse=True)
def _isolated_cache():
    clear_engine_cache()
    yield
    clear_engine_cache()


async def test_dispose_cached_engine_removes_exactly_the_named_url() -> None:
    target = _url(0)
    other = _url(1)
    get_engine(target)
    get_engine(other)

    disposed = await dispose_cached_engine(target)

    assert disposed is True
    assert target not in session_module._ENGINE_CACHE
    assert other in session_module._ENGINE_CACHE


async def test_dispose_cached_engine_returns_false_when_nothing_cached() -> None:
    disposed = await dispose_cached_engine(_url(99))

    assert disposed is False


async def test_ephemeral_engine_is_fully_disposed_before_database_drop() -> None:
    """Proves the exact lifecycle the ephemeral-Postgres fixtures must follow.

    Not a real Postgres test — SQLite stands in for "a database" here; what
    is under test is the disposal contract itself (borrow -> return -> await
    dispose -> gone from cache), independent of which backend is behind it.
    """
    ephemeral_url = _url(2)
    engine = get_engine(ephemeral_url)

    async with engine.connect() as connection:
        await connection.execute(text("select 1"))

    disposed = await dispose_cached_engine(ephemeral_url)

    assert disposed is True
    assert ephemeral_url not in session_module._ENGINE_CACHE, (
        "the engine must be gone from the cache before the caller drops "
        "the database it points at — a later get_engine(ephemeral_url) "
        "must build a brand-new engine, never resurrect this one"
    )
