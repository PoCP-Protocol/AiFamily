"""Assessment domain HTTP surface.

Re-exports the two things an app factory needs to mount this domain:

* `router` — the APIRouter carrying the UI-02 → UI-03 endpoints. Its paths are
  relative (`/{family_id}/...`), so the mounting app supplies the `/families`
  prefix. Keeping the prefix out of the router lets the same routes be mounted
  under a different root without editing every decorator.
* `register_exception_handlers` — installs one handler mapping
  `AssessmentDomainError` subclasses onto status codes, so routes do not each
  carry their own try/except.

Both must be called: mounting the router without registering the handlers means
a domain error surfaces as a 500 instead of the 404/409 it should be.

Historical note: this package replaced a single `api.py` module that exported an
`install_state(app)` function which both created in-process state and mounted
the router in one call. That shape did not survive the four-layer refactor —
state now comes from `dependencies.py` and is overridable via
`app.dependency_overrides` in tests, which `install_state` made awkward.
`backend/apps/family_api/main.py` was updated to the router form at the same
time; if you find a caller still importing `install_state`, it predates that
change.
"""

from __future__ import annotations

from backend.domains.assessment.api.routes import register_exception_handlers, router

__all__ = ["register_exception_handlers", "router"]
