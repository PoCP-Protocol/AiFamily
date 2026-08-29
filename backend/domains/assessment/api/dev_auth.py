"""Development-only account session endpoints.

## Why this file exists at all

These four endpoints (`/auth/account-session`, `/auth/me`, `/auth/contexts`,
`/auth/session/revoke`) are the **only** way the migrated mobile app obtains a
bearer token. All 34 UI screens are unusable without them
(`contracts/openapi/UI_API_ENDPOINT_INVENTORY.md`, AUTH group).

## Why it is in the assessment domain, which is wrong

It is not authentication's home. Authentication belongs to `auth_identity`,
which `governance/DOMAIN_REGISTRY.yaml` still lists as `NOT_STARTED`. These
endpoints landed inside the assessment domain only because assessment was the
first vertical slice that needed an HTTP session, and they stayed there.

`governance/CAPABILITY_REGISTRY.yaml` → `dev_account_session` records this as a
deliberate misplacement (`business_capability: PLATFORM_INTERNAL` on code that
physically sits in `domains/assessment`), not as an oversight. The migration-out
plan is `governance/ADR/ADR-0010-dev-auth-restored-in-assessment.md`.

## Why it was rewritten rather than moved verbatim

The four-layer refactor of this domain dropped these endpoints entirely — a real
functional regression: `grep '"/auth/account-session"'` over `backend/` returned
nothing, so the mobile app could not authenticate at all. Restoring them from
`git show HEAD:backend/domains/assessment/api.py` would have brought back a
dependency on `AssessmentService`, coupling session issuance to assessment
state for no reason. This module is self-contained instead: its only dependency
is the audit recorder.

## What this is NOT

Not production authentication. There is no OTP, no password, no real identity
proof: `external_ref` is exchanged for a token directly. Tokens live in a
process-local dict and vanish on restart. `expires_at` is a hardcoded sentinel,
not an enforced expiry. Do not build authorization decisions of consequence on
this — see `known_gaps` on the registry entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException

from backend.platform.audit import AuditEvent, AuditRecorder

# Sentinel far-future expiry. Deliberately not computed from `now`: a real
# expiry would need a clock, a refresh path and revocation-on-expiry, none of
# which exist here. A fixed obviously-fake value is more honest than a
# plausible-looking one that nothing enforces.
_NON_EXPIRY = "2099-01-01T00:00:00+00:00"

router = APIRouter()


@dataclass
class DevAuthState:
    """Process-local session store.

    `tokens` maps bearer token -> {account_id, family_id}. `receipts` gives the
    mutation endpoints replay semantics so a repeated idempotency-key returns
    the original response instead of minting a second session.
    """

    tokens: dict[str, dict[str, str]] = field(default_factory=dict)
    receipts: dict[str, Any] = field(default_factory=dict)
    recorder: AuditRecorder = field(default_factory=AuditRecorder)


_state = DevAuthState()


def get_state() -> DevAuthState:
    """Overridable via `app.dependency_overrides` in tests."""
    return _state


def _require_idempotency_key(key: str | None) -> str:
    if not key:
        raise HTTPException(status_code=400, detail="idempotency-key header is required")
    return key


def resolve_actor(
    authorization: str | None,
    family_id: str | None = None,
    state: DevAuthState | None = None,
) -> dict[str, str]:
    """Resolve a bearer token to an identity, optionally scoped to a family.

    Exported because the assessment routes need the same check. Two distinct
    failures on purpose: 401 for "no usable credential", 403 for "credential is
    fine but not for this family". Collapsing them would tell a caller with a
    valid token for family A that family B does not exist.
    """
    state = state or _state
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="authorization required")
    identity = state.tokens.get(authorization[7:])
    if not identity or (family_id and identity["family_id"] != family_id):
        raise HTTPException(status_code=403, detail="family access denied")
    return identity


def _replay_or(state: DevAuthState, key: str, operation: Any) -> Any:
    if key in state.receipts:
        return state.receipts[key]
    receipt = operation()
    state.receipts[key] = receipt
    return receipt


@router.post("/auth/account-session")
def create_account_session(
    body: dict[str, str],
    idempotency_key: str | None = Header(default=None),
) -> dict[str, str]:
    key = _require_idempotency_key(idempotency_key)
    state = get_state()
    external_ref = body.get("external_ref", "")
    if not external_ref:
        raise HTTPException(status_code=422, detail="external_ref is required")

    def create() -> dict[str, str]:
        # Dev convention is "<account>:<family>" — the shape the mobile client
        # sends via EXPO_PUBLIC_FAMILY_DEV_EXTERNAL_REF. The family is the
        # segment *after* the colon; reading [0] instead bound the session to
        # the account segment and every /families/{family_id}/... request then
        # failed its family check with 403. A ref with no colon is treated as
        # both account and family.
        account_part, _, family_part = external_ref.partition(":")
        account_id = account_part or external_ref
        family_id = family_part or account_id
        token = str(uuid4())
        state.tokens[token] = {"account_id": account_id, "family_id": family_id}
        state.recorder.record(
            AuditEvent(
                actor_id=account_id,
                tenant_id=family_id,
                action="auth.session_created",
                resource_type="IdentitySession",
                resource_id=token,
                reason="dev account session",
                correlation_id=str(uuid4()),
                after={"account_id": account_id},
            )
        )
        return {
            "token": token,
            "expires_at": _NON_EXPIRY,
            "account_id": account_id,
            "family_id": family_id,
        }

    return _replay_or(state, f"auth:{key}", create)


@router.get("/auth/me")
def get_me(authorization: str | None = Header(default=None)) -> dict[str, str]:
    identity = resolve_actor(authorization, state=get_state())
    return {"account_id": identity["account_id"], "session_id": identity["account_id"]}


@router.get("/auth/contexts")
def get_contexts(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    identity = resolve_actor(authorization, state=get_state())
    return {
        "account_id": identity["account_id"],
        "contexts": [
            {
                "type": "FAMILY",
                "tenant_id": identity["family_id"],
                "family_id": identity["family_id"],
                "person_id": identity["account_id"],
                "membership_id": "dev-membership",
                "role": "GUARDIAN",
            }
        ],
    }


@router.post("/auth/session/revoke")
def revoke_session(
    authorization: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
) -> dict[str, bool]:
    state = get_state()
    identity = resolve_actor(authorization, state=state)
    key = _require_idempotency_key(idempotency_key)

    def revoke_once() -> dict[str, bool]:
        state.recorder.record(
            AuditEvent(
                actor_id=identity["account_id"],
                tenant_id=identity["family_id"],
                action="auth.session_revoked",
                resource_type="IdentitySession",
                resource_id=identity["account_id"],
                reason="dev session revoke",
                correlation_id=str(uuid4()),
                after={"revoked": True},
            )
        )
        return {"revoked": True}

    return _replay_or(state, f"revoke:{identity['account_id']}:{key}", revoke_once)
