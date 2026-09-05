"""Engine cache eviction must dispose the evicted engine's connection pool.

`docs/06_platform/PERSISTENCE.md` §3 gap 4: `get_engine` was
`@lru_cache(maxsize=8)`, and `lru_cache` drops an evicted value on the floor. An
`AsyncEngine` owns a connection pool, so the ninth distinct URL leaked the first
engine's pooled connections. The test fixtures in this very directory generate a
fresh URL per test, so the leak was reachable from the existing suite.
"""

from __future__ import annotations

import pytest

from backend.platform.persistence import session as session_module
from backend.platform.persistence.session import (
    ENGINE_CACHE_SIZE,
    clear_engine_cache,
    get_engine,
)


def _url(n: int) -> str:
    return f"sqlite+aiosqlite:///:memory:?engine_cache_test={n}"


@pytest.fixture(autouse=True)
def _isolated_cache():
    """Run each test against an empty cache, and leave one behind.

    The cache is process-wide, so a test that filled it would change how many
    URLs the *next* test needs to trigger eviction.
    """
    clear_engine_cache()
    yield
    clear_engine_cache()


def test_same_url_returns_the_same_engine() -> None:
    """Caching still works — the fix must not have turned this into a factory."""
    assert get_engine(_url(1)) is get_engine(_url(1))


def test_cache_is_bounded() -> None:
    for n in range(ENGINE_CACHE_SIZE + 4):
        get_engine(_url(n))

    assert len(session_module._ENGINE_CACHE) == ENGINE_CACHE_SIZE


def test_evicted_engine_has_its_pool_disposed() -> None:
    """The defect. Overflow the cache and check the evicted pool was replaced.

    SQLAlchemy's `Pool.dispose()` swaps in a fresh, empty pool object, so
    identity of `engine.pool` changing is the observable evidence that dispose
    ran. Under the old `lru_cache` the evicted engine was simply dereferenced and
    this assertion failed.
    """
    victim = get_engine(_url(0))
    pool_before = victim.pool

    for n in range(1, ENGINE_CACHE_SIZE + 1):
        get_engine(_url(n))

    assert _url(0) not in session_module._ENGINE_CACHE, "victim should have been evicted"
    assert victim.pool is not pool_before, (
        "evicted engine's pool was never disposed — its pooled connections leak"
    )


def test_recently_used_url_is_not_the_one_evicted() -> None:
    """LRU ordering survives the rewrite: touching a URL keeps it alive."""
    for n in range(ENGINE_CACHE_SIZE):
        get_engine(_url(n))

    get_engine(_url(0))  # touch the oldest
    get_engine(_url(ENGINE_CACHE_SIZE))  # force one eviction

    assert _url(0) in session_module._ENGINE_CACHE
    assert _url(1) not in session_module._ENGINE_CACHE


def test_clear_engine_cache_disposes_everything() -> None:
    engines = [get_engine(_url(n)) for n in range(3)]
    pools_before = [engine.pool for engine in engines]

    clear_engine_cache()

    assert len(session_module._ENGINE_CACHE) == 0
    for engine, pool_before in zip(engines, pools_before, strict=True):
        assert engine.pool is not pool_before
