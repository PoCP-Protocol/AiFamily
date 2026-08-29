"""family_api — the first real FastAPI runtime entrypoint in AiFamily.

See governance/MIGRATION_MANIFEST.yaml capability
`fastapi_runtime_entrypoint` (disposition REIMPLEMENT). The source
repository had zero first-party `FastAPI()`/`uvicorn.run()`/
`include_router()` calls anywhere; this package is the first one, giving
R1 (single Python backend truth) its first runnable landing point.
"""

from __future__ import annotations

from backend.apps.family_api.main import app

__all__ = ["app"]
