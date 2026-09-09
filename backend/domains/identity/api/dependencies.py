"""FastAPI dependency seam for the identity router.

Fails closed by design, same convention as `domains/service/api/dependencies.py`
and `domains/family_need/api/dependencies.py`: `get_identity_service` raises
until the composition root overrides it via `app.dependency_overrides`
(`infrastructure/wiring.py`). There is deliberately no in-module default that
would let a misconfigured production process silently serve a fake session
store.
"""

from __future__ import annotations

from ..application.service import IdentityApplicationService


def get_identity_service() -> IdentityApplicationService:
    raise RuntimeError(
        "identity_service_not_wired: install_identity_wiring / "
        "install_identity_dev_wiring must run before the /auth/* routes are "
        "callable — see backend/domains/identity/infrastructure/wiring.py"
    )


__all__ = ["get_identity_service"]
