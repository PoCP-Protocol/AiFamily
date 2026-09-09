"""Dev/test-only bridge to `backend.domains.assessment.api.dev_auth`'s
process-local token dict.

## Why this exists

Per ADR-0011 §4, `/auth/*` now issues real, persisted sessions through
`IdentityApplicationService` instead of `dev_auth.py`'s in-process
`DevAuthState.tokens` dict. But that dict is not merely `dev_auth.py`'s own
implementation detail — `backend/apps/family_api/dev_wiring.py`'s `_identity`
helper (and, through it, at least seven other dev-only dependency overrides
across the assessment, service, family_need and product_intelligence dev
wiring) reads directly from `dev_auth.get_state().tokens`, not through any
HTTP call to `/auth/*`. Untangling all of those call sites to go through
`IdentityApplicationService` instead is a real, separate migration this slice
does not attempt (see the module docstring updates on `dev_auth.py` and
`main.py::_mount_identity`).

## What this does instead

Mirrors every session `/auth/account-session` issues (and every revocation
`/auth/session/revoke` performs) into that same shared dict, so the seven
existing dev-only dependants keep resolving tokens issued by the new,
Postgres/SQLite-backed domain exactly as they did when `dev_auth.py` itself
issued them. This is *purely* a compatibility mirror: `dev_auth`'s dict is
never read by anything in `backend.domains.identity` itself, and this module
is never imported by production wiring — only `main.py::_mount_identity`
wires it in, and only when `is_dev_environment()`.
"""

from __future__ import annotations

from backend.domains.assessment.api.dev_auth import get_state as get_dev_auth_state

from ..application.service import IdentityApplicationService, ResolvedIdentity, SessionIssued


class DevAuthMirroringIdentityService:
    """Wraps a real `IdentityApplicationService`, mirroring writes into
    `dev_auth`'s shared dict after they succeed against real persistence.

    Reads (`resolve_actor`) are never mirrored — they go straight to the real
    service, which is the whole point of this migration (real expiry
    enforcement, real revocation). Only the two mutation methods write
    through to the legacy dict, and only after the real write has already
    committed, so the dict is a lagging mirror, never a source of truth.
    """

    def __init__(self, inner: IdentityApplicationService) -> None:
        self._inner = inner

    async def create_account_session(
        self, *, external_ref: str, idempotency_key: str
    ) -> SessionIssued:
        issued = await self._inner.create_account_session(
            external_ref=external_ref, idempotency_key=idempotency_key
        )
        state = get_dev_auth_state()
        state.tokens[issued.token] = {
            "account_id": issued.account_id,
            "family_id": issued.family_id,
        }
        return issued

    async def resolve_actor(
        self, *, bearer_token: str | None, family_id: str | None = None
    ) -> ResolvedIdentity:
        return await self._inner.resolve_actor(bearer_token=bearer_token, family_id=family_id)

    async def revoke_session(self, *, bearer_token: str | None, idempotency_key: str) -> bool:
        revoked = await self._inner.revoke_session(
            bearer_token=bearer_token, idempotency_key=idempotency_key
        )
        if revoked and bearer_token and bearer_token.startswith("Bearer "):
            get_dev_auth_state().tokens.pop(bearer_token[len("Bearer ") :], None)
        return revoked


__all__ = ["DevAuthMirroringIdentityService"]
