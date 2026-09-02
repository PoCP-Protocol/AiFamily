"""Disposable SQLite proof for three canonical live-commerce ledger ports.

This is not a production ledger. It proves the required separation between
cash movements, entitlements/points, and expert settlement using synthetic
adult data before AiFamily's canonical owners provide adapters.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class Track(StrEnum):
    CONTENT_SUPPORT = "CONTENT_SUPPORT"
    MEMBERSHIP = "MEMBERSHIP"
    MEDIA_ENTITLEMENT = "MEDIA_ENTITLEMENT"
    SERVICE_OFFERING = "SERVICE_OFFERING"
    POINTS = "POINTS"


class LedgerRejected(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LedgerActor:
    tenant_id: str
    family_id: str
    actor_id: str
    is_adult: bool = True


@dataclass(frozen=True, slots=True)
class Purchase:
    purchase_ref: str
    track: Track
    subject_ref: str
    amount: int
    currency: str
    idempotency_key: str


class ThreeLedgerSandbox:
    def __init__(self, database_path: Path) -> None:
        self._path = database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as database:
            database.executescript(
                """
                CREATE TABLE IF NOT EXISTS cash_ledger (
                    entry_ref TEXT PRIMARY KEY, purchase_ref TEXT NOT NULL,
                    tenant_id TEXT NOT NULL, family_id TEXT NOT NULL,
                    track TEXT NOT NULL, amount INTEGER NOT NULL,
                    currency TEXT NOT NULL, kind TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS entitlement_ledger (
                    entry_ref TEXT PRIMARY KEY, purchase_ref TEXT NOT NULL,
                    tenant_id TEXT NOT NULL, family_id TEXT NOT NULL,
                    track TEXT NOT NULL, subject_ref TEXT NOT NULL,
                    state TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settlement_ledger (
                    entry_ref TEXT PRIMARY KEY, purchase_ref TEXT NOT NULL,
                    tenant_id TEXT NOT NULL, family_id TEXT NOT NULL,
                    beneficiary_ref TEXT NOT NULL, amount INTEGER NOT NULL,
                    currency TEXT NOT NULL, kind TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS operation_keys (
                    idempotency_key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                    result_json TEXT NOT NULL
                );
                """
            )

    def purchase(self, *, actor: LedgerActor, command: Purchase) -> dict[str, object]:
        self._assert_actor(actor)
        if command.amount <= 0:
            raise LedgerRejected("amount must be positive")
        expected_currency = "POINT" if command.track is Track.POINTS else "CNY_CENT"
        if command.currency != expected_currency:
            raise LedgerRejected("track currency mismatch")
        fingerprint = json.dumps(
            [
                actor.tenant_id,
                actor.family_id,
                command.purchase_ref,
                command.track,
                command.subject_ref,
                command.amount,
                command.currency,
                command.idempotency_key,
            ],
            ensure_ascii=True,
        )
        with self._connect() as database:
            previous = database.execute(
                "SELECT fingerprint, result_json FROM operation_keys WHERE idempotency_key = ?",
                (command.idempotency_key,),
            ).fetchone()
            if previous is not None:
                if previous[0] != fingerprint:
                    raise LedgerRejected("idempotency conflict")
                return json.loads(previous[1])
            expert_amount = command.amount * 80 // 100
            platform_amount = command.amount - expert_amount
            cash_amount = 0 if command.track is Track.POINTS else command.amount
            if cash_amount:
                database.execute(
                    "INSERT INTO cash_ledger VALUES (?, ?, ?, ?, ?, ?, ?, 'CAPTURE')",
                    (
                        f"cash:{command.purchase_ref}",
                        command.purchase_ref,
                        actor.tenant_id,
                        actor.family_id,
                        command.track,
                        cash_amount,
                        command.currency,
                    ),
                )
            database.execute(
                "INSERT INTO entitlement_ledger VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE')",
                (
                    f"entitlement:{command.purchase_ref}",
                    command.purchase_ref,
                    actor.tenant_id,
                    actor.family_id,
                    command.track,
                    command.subject_ref,
                ),
            )
            for beneficiary, amount in (
                ("expert.synthetic.1", expert_amount),
                ("platform:aifamily", platform_amount),
            ):
                database.execute(
                    "INSERT INTO settlement_ledger VALUES (?, ?, ?, ?, ?, ?, ?, 'ACCRUAL')",
                    (
                        f"settlement:{beneficiary}:{command.purchase_ref}",
                        command.purchase_ref,
                        actor.tenant_id,
                        actor.family_id,
                        beneficiary,
                        amount,
                        command.currency,
                    ),
                )
            result: dict[str, object] = {
                "purchase_ref": command.purchase_ref,
                "track": command.track,
                "cash_amount": cash_amount,
                "entitlement_state": "ACTIVE",
                "expert_accrual": expert_amount,
                "platform_accrual": platform_amount,
                "external_effect": False,
            }
            database.execute(
                "INSERT INTO operation_keys VALUES (?, ?, ?)",
                (command.idempotency_key, fingerprint, json.dumps(result)),
            )
            database.commit()
            return result

    def reverse(
        self,
        *,
        actor: LedgerActor,
        purchase_ref: str,
        reversal_ref: str,
        idempotency_key: str,
        reason: str,
    ) -> dict[str, object]:
        self._assert_actor(actor)
        fingerprint = json.dumps(
            [actor.tenant_id, actor.family_id, purchase_ref, reversal_ref, reason]
        )
        with self._connect() as database:
            previous = database.execute(
                "SELECT fingerprint, result_json FROM operation_keys WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if previous is not None:
                if previous[0] != fingerprint:
                    raise LedgerRejected("idempotency conflict")
                return json.loads(previous[1])
            entitlement = database.execute(
                "SELECT track FROM entitlement_ledger "
                "WHERE purchase_ref = ? AND tenant_id = ? AND family_id = ? "
                "AND state = 'ACTIVE'",
                (purchase_ref, actor.tenant_id, actor.family_id),
            ).fetchone()
            if entitlement is None:
                raise LedgerRejected("active purchase not found in actor scope")
            database.execute(
                "UPDATE entitlement_ledger SET state = 'REVOKED' "
                "WHERE purchase_ref = ? AND tenant_id = ? AND family_id = ?",
                (purchase_ref, actor.tenant_id, actor.family_id),
            )
            cash = database.execute(
                "SELECT amount, currency FROM cash_ledger "
                "WHERE purchase_ref = ? AND tenant_id = ? AND family_id = ? "
                "AND kind = 'CAPTURE'",
                (purchase_ref, actor.tenant_id, actor.family_id),
            ).fetchone()
            if cash is not None:
                database.execute(
                    "INSERT INTO cash_ledger VALUES (?, ?, ?, ?, ?, ?, ?, 'REVERSAL')",
                    (
                        f"cash:{reversal_ref}",
                        purchase_ref,
                        actor.tenant_id,
                        actor.family_id,
                        entitlement[0],
                        -cash[0],
                        cash[1],
                    ),
                )
            accruals = database.execute(
                "SELECT beneficiary_ref, amount, currency FROM settlement_ledger "
                "WHERE purchase_ref = ? AND tenant_id = ? AND family_id = ? "
                "AND kind = 'ACCRUAL'",
                (purchase_ref, actor.tenant_id, actor.family_id),
            ).fetchall()
            for beneficiary, amount, currency in accruals:
                database.execute(
                    "INSERT INTO settlement_ledger VALUES (?, ?, ?, ?, ?, ?, ?, 'REVERSAL')",
                    (
                        f"settlement:{beneficiary}:{reversal_ref}",
                        purchase_ref,
                        actor.tenant_id,
                        actor.family_id,
                        beneficiary,
                        -amount,
                        currency,
                    ),
                )
            result: dict[str, object] = {
                "purchase_ref": purchase_ref,
                "state": "REVERSED",
                "cash_reversal": 0 if cash is None else -cash[0],
                "settlement_reversal": -sum(row[1] for row in accruals),
                "reason": reason,
                "external_effect": False,
            }
            database.execute(
                "INSERT INTO operation_keys VALUES (?, ?, ?)",
                (idempotency_key, fingerprint, json.dumps(result)),
            )
            database.commit()
            return result

    def balances(self, *, actor: LedgerActor, purchase_ref: str) -> dict[str, object]:
        self._assert_actor(actor)
        with self._connect() as database:
            state_row = database.execute(
                "SELECT state FROM entitlement_ledger "
                "WHERE purchase_ref = ? AND tenant_id = ? AND family_id = ?",
                (purchase_ref, actor.tenant_id, actor.family_id),
            ).fetchone()
            if state_row is None:
                raise LedgerRejected("purchase not found in actor scope")
            cash = database.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM cash_ledger "
                "WHERE purchase_ref = ? AND tenant_id = ? AND family_id = ?",
                (purchase_ref, actor.tenant_id, actor.family_id),
            ).fetchone()[0]
            settlement = database.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM settlement_ledger "
                "WHERE purchase_ref = ? AND tenant_id = ? AND family_id = ?",
                (purchase_ref, actor.tenant_id, actor.family_id),
            ).fetchone()[0]
        return {
            "purchase_ref": purchase_ref,
            "cash": cash,
            "settlement": settlement,
            "entitlement": state_row[0],
            "external_effect": False,
        }

    def settlements(self, *, actor: LedgerActor, purchase_ref: str) -> dict[str, object]:
        self._assert_actor(actor)
        with self._connect() as database:
            purchase = database.execute(
                "SELECT track, state FROM entitlement_ledger "
                "WHERE purchase_ref = ? AND tenant_id = ? AND family_id = ?",
                (purchase_ref, actor.tenant_id, actor.family_id),
            ).fetchone()
            if purchase is None:
                raise LedgerRejected("purchase not found in actor scope")
            rows = database.execute(
                "SELECT beneficiary_ref, currency, COALESCE(SUM(amount), 0) "
                "FROM settlement_ledger "
                "WHERE purchase_ref = ? AND tenant_id = ? AND family_id = ? "
                "GROUP BY beneficiary_ref, currency",
                (purchase_ref, actor.tenant_id, actor.family_id),
            ).fetchall()
        net_amounts = {row[0]: row[2] for row in rows}
        currencies = {row[1] for row in rows}
        if len(currencies) != 1:
            raise LedgerRejected("settlement currency unavailable")
        beneficiaries = [
            {
                "beneficiary_ref": beneficiary_ref,
                "net_amount": net_amounts.get(beneficiary_ref, 0),
            }
            for beneficiary_ref in ("expert.synthetic.1", "platform:aifamily")
        ]
        return {
            "purchase_ref": purchase_ref,
            "track": purchase[0],
            "currency": currencies.pop(),
            "entitlement": purchase[1],
            "beneficiaries": beneficiaries,
            "total": sum(item["net_amount"] for item in beneficiaries),
            "external_effect": False,
        }

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    @staticmethod
    def _assert_actor(actor: LedgerActor) -> None:
        if not actor.is_adult:
            raise LedgerRejected("child commerce prohibited")
        if not all((actor.tenant_id, actor.family_id, actor.actor_id)):
            raise LedgerRejected("trusted actor scope required")
