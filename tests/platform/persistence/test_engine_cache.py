"""Contracts for the process-local persistence engine cache."""

from __future__ import annotations

from backend.platform.persistence import session as session_module
from backend.platform.persistence.session import (
    clear_engine_cache,
    get_engine,
    get_sessionmaker,
)


def _url(suffix: str) -> str:
    return f"sqlite+aiosqlite:///:memory:?persistence_cache_test={suffix}"


def setup_function() -> None:
    clear_engine_cache()


def teardown_function() -> None:
    clear_engine_cache()


def test_clear_engine_cache_forces_a_fresh_engine_for_the_same_url() -> None:
    database_url = _url("reset")
    first_engine = get_engine(database_url)

    clear_engine_cache()

    second_engine = get_engine(database_url)
    assert second_engine is not first_engine


def test_clear_engine_cache_preserves_existing_sessionmaker_binding() -> None:
    database_url = _url("sessionmaker")
    first_engine = get_engine(database_url)
    existing_sessionmaker = get_sessionmaker(database_url)

    clear_engine_cache()

    second_engine = get_engine(database_url)
    assert second_engine is not first_engine
    assert existing_sessionmaker.kw["bind"] is first_engine
    assert session_module._cached_engine.cache_info().currsize == 1
