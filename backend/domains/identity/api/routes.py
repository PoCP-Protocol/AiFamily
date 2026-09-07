"""The 4 `/auth/*` endpoints, migrated out of `backend/domains/assessment/api/dev_auth.py`
per ADR-0011 §4.

Request/response shapes are byte-for-byte identical to `dev_auth.py`'s — the
mobile client (`frontend/mobile/lib/family/family-api-client.ts`) is the only
consumer and its contract must not change. What changed is entirely behind
the contract: `IdentityApplicationService` persists through
`IdentityRepositoryPort` (real Postgres in production wiring) instead of a
process dict, and `expires_at` is a real, enforced value instead of the
`_NON_EXPIRY` sentinel `dev_auth.py` used.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from ..application.service import IdentityApplicationService
from ..domain.errors import (
    IdentityForbiddenError,
    IdentityUnauthenticatedError,
    IdentityValidationError,
)
from .dependencies import get_identity_service

router = APIRouter()


def _require_idempotency_key(key: str | None) -> str:
    if not key:
        raise HTTPException(status_code=400, detail="idempotency-key header is required")
    return key


@router.post("/auth/account-session")
async def create_account_session(
    body: dict[str, str],
    idempotency_key: str | None = Header(default=None),
    service: IdentityApplicationService = Depends(get_identity_service),
) -> dict[str, Any]:
    key = _require_idempotency_key(idempotency_key)
    external_ref = body.get("external_ref", "")
    if not external_ref:
        raise HTTPException(status_code=422, detail="external_ref is required")
    try:
        issued = await service.create_account_session(
            external_ref=external_ref, idempotency_key=key
        )
    except IdentityValidationError as error:
        raise HTTPException(status_code=422, detail=error.code) from error
    return {
        "token": issued.token,
        "expires_at": issued.expires_at.isoformat(),
        "account_id": issued.account_id,
        "family_id": issued.family_id,
    }


@router.get("/auth/me")
async def get_me(
    authorization: str | None = Header(default=None),
    service: IdentityApplicationService = Depends(get_identity_service),
) -> dict[str, str]:
    identity = await _resolve_or_raise(service, authorization)
    return {"account_id": identity.account_id, "session_id": identity.account_id}


@router.get("/auth/contexts")
async def get_contexts(
    authorization: str | None = Header(default=None),
    service: IdentityApplicationService = Depends(get_identity_service),
) -> dict[str, Any]:
    identity = await _resolve_or_raise(service, authorization)
    return {
        "account_id": identity.account_id,
        "contexts": [
            {
                "type": "FAMILY",
                "tenant_id": identity.family_id,
                "family_id": identity.family_id,
                "person_id": identity.account_id,
                "membership_id": "dev-membership",
                "role": "GUARDIAN",
            }
        ],
    }


@router.post("/auth/session/revoke")
async def revoke_session(
    authorization: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
    service: IdentityApplicationService = Depends(get_identity_service),
) -> dict[str, bool]:
    key = _require_idempotency_key(idempotency_key)
    try:
        revoked = await service.revoke_session(bearer_token=authorization, idempotency_key=key)
    except IdentityUnauthenticatedError as error:
        raise HTTPException(status_code=401, detail=error.code) from error
    except IdentityForbiddenError as error:
        raise HTTPException(status_code=403, detail=error.code) from error
    except IdentityValidationError as error:
        raise HTTPException(status_code=400, detail=error.code) from error
    return {"revoked": revoked}


async def _resolve_or_raise(service: IdentityApplicationService, authorization: str | None):
    try:
        return await service.resolve_actor(bearer_token=authorization)
    except IdentityUnauthenticatedError as error:
        raise HTTPException(status_code=401, detail=error.code) from error
    except IdentityForbiddenError as error:
        raise HTTPException(status_code=403, detail=error.code) from error


__all__ = ["router"]
