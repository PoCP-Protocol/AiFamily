"""Composition helpers for the Product Factory draft API.

The application factory owns when these helpers run.  Mounting the router
advertises the stable Web contract, while the domain dependencies continue to
fail closed until trusted identity and an explicit database session factory
are installed.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from backend.domains.product_intelligence.api import product_factory_routes
from backend.domains.product_intelligence.api.dependencies import (
    clear_session_factory,
    configure_session_factory,
)


def mount_product_factory_router(application: FastAPI) -> None:
    """Mount the Product Factory draft endpoints exactly once."""

    application.include_router(product_factory_routes.router)


def install_product_factory_session_factory(session_factory: Any | None) -> None:
    """Bind an explicit app-owned async session factory for production."""

    configure_session_factory(session_factory)


def clear_product_factory_session_factory() -> None:
    """Clear Product Factory persistence wiring between app instances/tests."""

    clear_session_factory()


__all__ = [
    "clear_product_factory_session_factory",
    "install_product_factory_session_factory",
    "mount_product_factory_router",
]
