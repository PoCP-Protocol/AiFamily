"""Process-local `IdentityRepositoryPort` for tests that do not need real
Postgres. Same role as `domains/membership/infrastructure/fake_repository.py`
would play — this domain's actual dev/test HTTP wiring uses the real SQLite/
Postgres-backed `SqlAlchemyIdentityRepository` (see `wiring.py`), so this fake
exists for unit tests of `IdentityApplicationService` in isolation.
"""

from __future__ import annotations

from ..domain.entities import Account, IdentitySession


class FakeIdentityRepository:
    def __init__(self) -> None:
        self._accounts_by_ref: dict[str, Account] = {}
        self._sessions: dict[str, IdentitySession] = {}
        self._receipts: dict[str, dict] = {}

    async def save_account(self, account: Account) -> None:
        self._accounts_by_ref[account.external_ref] = account

    async def find_account_by_external_ref(self, external_ref: str) -> Account | None:
        return self._accounts_by_ref.get(external_ref)

    async def save_session(self, session: IdentitySession) -> None:
        self._sessions[session.session_id] = session

    async def find_session(self, session_id: str) -> IdentitySession | None:
        return self._sessions.get(session_id)

    async def find_receipt(self, idempotency_key: str) -> dict | None:
        return self._receipts.get(idempotency_key)

    async def save_receipt(self, idempotency_key: str, response: dict) -> None:
        self._receipts.setdefault(idempotency_key, response)

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


__all__ = ["FakeIdentityRepository"]
