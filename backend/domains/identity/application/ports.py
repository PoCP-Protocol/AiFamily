"""Ports the application layer depends on, implemented by `infrastructure/`.

Same "define the seam before the real adapter exists" posture as
`backend/platform/identity/session_port.py`'s `IdentitySessionPort` (a
different, HTTP-facing port consumed by the AI composition root) and
`backend/domains/family_need/application/ports.py`'s `SupplyReferencePort`.
"""

from __future__ import annotations

from typing import Protocol

from ..domain.entities import Account, IdentitySession, OtpChallenge


class IdentityRepositoryPort(Protocol):
    """Persistence seam for Account / IdentitySession.

    `save_session` / `find_session` etc. are `async` because the real adapter
    is `SqlAlchemyIdentityRepository` (asyncpg-backed); the in-memory fake used
    by dev/test satisfies the same signatures synchronously-inside-async, same
    convention as `FakeFamilyNeedRepository`.
    """

    async def save_account(self, account: Account) -> None: ...

    async def find_account_by_external_ref(self, external_ref: str) -> Account | None: ...

    async def save_session(self, session: IdentitySession) -> None: ...

    async def find_session(self, session_id: str) -> IdentitySession | None: ...

    async def find_receipt(self, idempotency_key: str) -> dict | None: ...

    async def save_receipt(self, idempotency_key: str, response: dict) -> None: ...

    async def commit(self) -> None: ...


class OtpSender(Protocol):
    """Provider-neutral one-time-passcode delivery boundary.

    Deciding *which* SMS/email provider to integrate is a business/legal
    decision (delivery contracts, opt-in consent copy, regional compliance) —
    out of scope for this slice, same posture `backend/intelligence/model_gateway`
    takes toward model provider selection: the seam is designed here, the
    supplier choice is deferred to whoever owns that decision. Swapping the
    stub implementation below for a real provider must not require any change
    to code that calls `OtpSender` — only a new adapter class.
    """

    async def send(self, challenge: OtpChallenge) -> None: ...


__all__ = ["IdentityRepositoryPort", "OtpSender"]
