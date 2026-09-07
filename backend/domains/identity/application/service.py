"""Session issue / introspect / revoke use cases.

Backs the 4 `/auth/*` endpoints migrated from
`backend/domains/assessment/api/dev_auth.py` (ADR-0011 §4). The request/
response *shapes* below are deliberately identical to that module's — the
mobile client contract must not change — but every value is now computed
from a real clock and persisted through `IdentityRepositoryPort` instead of
a process-local dict, and a session that has passed `expires_at` is rejected
rather than accepted forever.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from backend.platform.audit import AuditEvent, AuditRecorder

from ..domain.entities import Account, IdentitySession
from ..domain.errors import (
    IdentityForbiddenError,
    IdentityUnauthenticatedError,
    IdentityValidationError,
)
from .ports import IdentityRepositoryPort

#: Session lifetime. A real, enforced value — the property `dev_auth.py`
#: explicitly did *not* have (`_NON_EXPIRY`, a hardcoded 2099 sentinel).
#: 12 hours mirrors a typical mobile-session lifetime; nothing about the
#: mobile contract depends on this exact number, only on `expires_at` being
#: present and eventually making the session `is_valid_at() is False`.
DEFAULT_SESSION_LIFETIME = timedelta(hours=12)


@dataclass(frozen=True, slots=True)
class SessionIssued:
    token: str
    expires_at: datetime
    account_id: str
    family_id: str


@dataclass(frozen=True, slots=True)
class ResolvedIdentity:
    account_id: str
    family_id: str
    session_id: str


class IdentityApplicationService:
    """Use cases for the 4 `/auth/*` endpoints. No HTTP, no FastAPI import."""

    def __init__(
        self,
        repository: IdentityRepositoryPort,
        *,
        recorder: AuditRecorder | None = None,
        clock: type[datetime] | None = None,
        session_lifetime: timedelta = DEFAULT_SESSION_LIFETIME,
    ) -> None:
        self._repository = repository
        self._recorder = recorder or AuditRecorder()
        self._clock = clock or datetime
        self._session_lifetime = session_lifetime

    def _now(self) -> datetime:
        return self._clock.now(UTC)

    async def create_account_session(
        self, *, external_ref: str, idempotency_key: str
    ) -> SessionIssued:
        if not external_ref:
            raise IdentityValidationError("EXTERNAL_REF_REQUIRED")
        if not idempotency_key:
            raise IdentityValidationError("IDEMPOTENCY_KEY_REQUIRED")

        receipt_key = f"auth:{idempotency_key}"
        existing = await self._repository.find_receipt(receipt_key)
        if existing is not None:
            return SessionIssued(**existing)

        # Dev/test convention preserved verbatim from `dev_auth.py`:
        # "<account>:<family>" — the family is the segment *after* the colon.
        # A ref with no colon is treated as both account and family.
        account_part, _, family_part = external_ref.partition(":")
        account_id = account_part or external_ref
        family_id = family_part or account_id

        account = await self._repository.find_account_by_external_ref(external_ref)
        if account is None:
            account = Account(
                account_id=account_id,
                external_ref=external_ref,
                created_at=self._now(),
            )
            await self._repository.save_account(account)

        now = self._now()
        session = IdentitySession(
            session_id=str(uuid.uuid4()),
            account_id=account.account_id,
            family_id=family_id,
            issued_at=now,
            expires_at=now + self._session_lifetime,
        )
        await self._repository.save_session(session)

        self._recorder.record(
            AuditEvent(
                actor_id=account.account_id,
                tenant_id=family_id,
                action="auth.session_created",
                resource_type="IdentitySession",
                resource_id=session.session_id,
                reason="account session issued",
                correlation_id=str(uuid.uuid4()),
                after={"account_id": account.account_id},
            )
        )

        response = {
            "token": session.session_id,
            "expires_at": session.expires_at,
            "account_id": account.account_id,
            "family_id": family_id,
        }
        await self._repository.save_receipt(receipt_key, response)
        await self._repository.commit()
        return SessionIssued(**response)

    async def resolve_actor(
        self, *, bearer_token: str | None, family_id: str | None = None
    ) -> ResolvedIdentity:
        """Same two-failure-mode contract as `dev_auth.resolve_actor`:
        401 for "no usable credential" (missing/malformed/unknown/expired/
        revoked token), 403 for "credential is fine but not for this family".
        """

        if not bearer_token or not bearer_token.startswith("Bearer "):
            raise IdentityUnauthenticatedError("AUTHORIZATION_REQUIRED")
        session = await self._repository.find_session(bearer_token[len("Bearer ") :])
        if session is None or not session.is_valid_at(self._now()):
            raise IdentityUnauthenticatedError("UNKNOWN_OR_EXPIRED_SESSION")
        if family_id and session.family_id != family_id:
            raise IdentityForbiddenError("FAMILY_ACCESS_DENIED")
        return ResolvedIdentity(
            account_id=session.account_id,
            family_id=session.family_id,
            session_id=session.session_id,
        )

    async def revoke_session(self, *, bearer_token: str | None, idempotency_key: str) -> bool:
        """Revoke the session the bearer token names.

        Unlike `dev_auth.py`'s `revoke_once` — which recorded an audit event
        but never actually removed the token from its dict, so a second
        `/auth/session/revoke` call with a *different* replay key would still
        succeed against the same, still-live token — this makes revocation
        real: `IdentitySession.is_valid_at` returns `False` for it afterwards.
        That means a *replay* of the same idempotency key must not go through
        `resolve_actor` a second time, because the session it names is by
        then legitimately no longer live; the receipt lookup happens first,
        keyed only on the token's own session id, so a repeated call short-
        circuits before it would otherwise see "session already revoked" and
        misreport that as 401.
        """

        if not bearer_token or not bearer_token.startswith("Bearer "):
            raise IdentityUnauthenticatedError("AUTHORIZATION_REQUIRED")
        if not idempotency_key:
            raise IdentityValidationError("IDEMPOTENCY_KEY_REQUIRED")

        token = bearer_token[len("Bearer ") :]
        session = await self._repository.find_session(token)
        if session is None:
            raise IdentityUnauthenticatedError("UNKNOWN_OR_EXPIRED_SESSION")

        receipt_key = f"revoke:{session.account_id}:{idempotency_key}"
        existing = await self._repository.find_receipt(receipt_key)
        if existing is not None:
            return bool(existing["revoked"])

        if not session.is_valid_at(self._now()):
            raise IdentityUnauthenticatedError("UNKNOWN_OR_EXPIRED_SESSION")

        await self._repository.save_session(session.revoke(at=self._now()))

        self._recorder.record(
            AuditEvent(
                actor_id=session.account_id,
                tenant_id=session.family_id,
                action="auth.session_revoked",
                resource_type="IdentitySession",
                resource_id=session.account_id,
                reason="session revoke",
                correlation_id=str(uuid.uuid4()),
                after={"revoked": True},
            )
        )
        await self._repository.save_receipt(receipt_key, {"revoked": True})
        await self._repository.commit()
        return True


__all__ = [
    "DEFAULT_SESSION_LIFETIME",
    "IdentityApplicationService",
    "ResolvedIdentity",
    "SessionIssued",
]
