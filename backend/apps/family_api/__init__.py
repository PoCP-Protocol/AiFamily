"""family_api — the first real FastAPI runtime entrypoint in AiFamily.

See governance/MIGRATION_MANIFEST.yaml capability
`fastapi_runtime_entrypoint` (disposition REIMPLEMENT). The source
repository had zero first-party `FastAPI()`/`uvicorn.run()`/
`include_router()` calls anywhere; this package is the first one, giving
R1 (single Python backend truth) its first runnable landing point.
"""

from __future__ import annotations


def __getattr__(name: str):
    """Load the FastAPI app lazily so submodule imports stay acyclic.

    Importing ``backend.apps.family_api.trusted_experience_scope`` must not
    execute the composition root: ``main`` imports ``dev_wiring``, which in
    turn imports the experience API.  A lazy attribute preserves the public
    ``from backend.apps.family_api import app`` convenience without making
    every family_api submodule pay that import cost or enter the cycle.
    """

    if name == "app":
        from backend.apps.family_api.main import app as application

        return application
    raise AttributeError(name)

__all__ = ["app"]
