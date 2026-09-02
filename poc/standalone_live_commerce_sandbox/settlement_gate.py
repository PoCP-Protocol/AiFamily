"""Synthetic creator settlement requests with a human finance gate.

This workflow stores requests and review decisions only. It reads the existing
three-ledger sandbox for eligibility and never creates a cash payout entry.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from poc.standalone_live_commerce_sandbox.ledger_sandbox import (
    LedgerActor,
    LedgerRejected,
    ThreeLedgerSandbox,
)

EXPERT_BENEFICIARY = "expert.synthetic.1"
CREATOR_ACTOR = "actor.synthetic.creator.1"


class SettlementGateRejected(RuntimeError):
    pass


class SettlementGateNotFound(SettlementGateRejected):
    pass


class SettlementGateConflict(SettlementGateRejected):
    pass


@dataclass(frozen=True, slots=True)
class SettlementActor:
    tenant_id: str
    family_id: str
    actor_id: str
    role: str


class SettlementGate:
    def __init__(self, database_path: Path, ledger: ThreeLedgerSandbox) -> None:
        self._path = database_path
        self._ledger = ledger
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as database:
            database.executescript(
                """
                CREATE TABLE IF NOT EXISTS settlement_requests (
                    request_ref TEXT PRIMARY KEY,
                    purchase_ref TEXT NOT NULL,
                    beneficiary_ref TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    family_id TEXT NOT NULL,
                    requester_id TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    currency TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    reviewer_id TEXT,
                    decision_reason TEXT
                );
                CREATE TABLE IF NOT EXISTS settlement_request_keys (
                    idempotency_key TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    result_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settlement_decisions (
                    decision_key TEXT PRIMARY KEY,
                    request_ref TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    reviewer_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    decided_at TEXT NOT NULL,
                    result_json TEXT NOT NULL
                );
                """
            )
            columns = {
                row["name"] for row in database.execute("PRAGMA table_info(settlement_requests)")
            }
            if "reviewer_id" not in columns:
                database.execute("ALTER TABLE settlement_requests ADD COLUMN reviewer_id TEXT")
            if "decision_reason" not in columns:
                database.execute("ALTER TABLE settlement_requests ADD COLUMN decision_reason TEXT")

    def request(
        self,
        *,
        actor: SettlementActor,
        request_ref: str,
        purchase_ref: str,
        beneficiary_ref: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        self._assert_actor(actor, "CREATOR_OPERATOR")
        if actor.actor_id != CREATOR_ACTOR or beneficiary_ref != EXPERT_BENEFICIARY:
            raise SettlementGateRejected("creator beneficiary scope denied")
        fingerprint = self._fingerprint(
            actor.tenant_id,
            actor.family_id,
            actor.actor_id,
            request_ref,
            purchase_ref,
            beneficiary_ref,
        )
        with self._connect() as database:
            prior = database.execute(
                "SELECT fingerprint, result_json FROM settlement_request_keys "
                "WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if prior is not None:
                if prior["fingerprint"] != fingerprint:
                    raise SettlementGateConflict("settlement request idempotency conflict")
                return json.loads(prior["result_json"])
        amount, currency = self._eligible_expert_net(actor, purchase_ref)
        timestamp = now_iso()
        result: dict[str, object] = {
            "request_ref": request_ref,
            "purchase_ref": purchase_ref,
            "beneficiary_ref": beneficiary_ref,
            "amount": amount,
            "currency": currency,
            "state": "PENDING",
            "requester_id": actor.actor_id,
            "reviewer_id": None,
            "decision_reason": None,
            "payment_state": "NOT_EXECUTED",
            "source": "SANDBOX_SYNTHETIC",
            "fixture_only": True,
            "created_at": timestamp,
            "updated_at": timestamp,
            "external_effect": False,
        }
        with self._connect() as database:
            try:
                database.execute(
                    """
                    INSERT INTO settlement_requests (
                        request_ref, purchase_ref, beneficiary_ref, tenant_id,
                        family_id, requester_id, amount, currency, state,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request_ref,
                        purchase_ref,
                        beneficiary_ref,
                        actor.tenant_id,
                        actor.family_id,
                        actor.actor_id,
                        amount,
                        currency,
                        "PENDING",
                        timestamp,
                        timestamp,
                    ),
                )
                database.execute(
                    "INSERT INTO settlement_request_keys VALUES (?, ?, ?)",
                    (idempotency_key, fingerprint, json.dumps(result)),
                )
                database.commit()
            except sqlite3.IntegrityError as exc:
                raise SettlementGateConflict("settlement request reference conflict") from exc
        return result

    def list_requests(self, *, actor: SettlementActor) -> list[dict[str, object]]:
        self._assert_actor(actor, "CREATOR_OPERATOR", "HUMAN_FINANCE_REVIEWER")
        query = "SELECT * FROM settlement_requests WHERE tenant_id = ? AND family_id = ?"
        parameters: list[str] = [actor.tenant_id, actor.family_id]
        if actor.role == "CREATOR_OPERATOR":
            if actor.actor_id != CREATOR_ACTOR:
                return []
            query += " AND requester_id = ? AND beneficiary_ref = ?"
            parameters.extend((actor.actor_id, EXPERT_BENEFICIARY))
        query += " ORDER BY created_at ASC, request_ref ASC"
        with self._connect() as database:
            rows = database.execute(query, parameters).fetchall()
        return [self._request_view(row) for row in rows]

    def decide(
        self,
        *,
        actor: SettlementActor,
        request_ref: str,
        decision_key: str,
        decision: str,
        reason: str,
    ) -> dict[str, object]:
        self._assert_actor(actor, "HUMAN_FINANCE_REVIEWER")
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise SettlementGateRejected("decision reason required")
        if decision not in {"APPROVE", "REJECT"}:
            raise SettlementGateRejected("unsupported settlement decision")
        fingerprint = self._fingerprint(
            actor.tenant_id,
            actor.family_id,
            actor.actor_id,
            request_ref,
            decision,
            normalized_reason,
        )
        with self._connect() as database:
            prior = database.execute(
                "SELECT fingerprint, result_json FROM settlement_decisions WHERE decision_key = ?",
                (decision_key,),
            ).fetchone()
            if prior is not None:
                if prior["fingerprint"] != fingerprint:
                    raise SettlementGateConflict("settlement decision idempotency conflict")
                return json.loads(prior["result_json"])
            request_row = database.execute(
                "SELECT * FROM settlement_requests "
                "WHERE request_ref = ? AND tenant_id = ? AND family_id = ?",
                (request_ref, actor.tenant_id, actor.family_id),
            ).fetchone()
            if request_row is None:
                raise SettlementGateNotFound("settlement request not found in actor scope")
            if request_row["state"] != "PENDING":
                raise SettlementGateConflict("settlement request already decided")

        amount, currency = self._eligible_expert_net(actor, request_row["purchase_ref"])
        if amount != request_row["amount"] or currency != request_row["currency"]:
            raise SettlementGateConflict("settlement amount changed before decision")
        state = "APPROVED" if decision == "APPROVE" else "REJECTED"
        timestamp = now_iso()
        result = {
            **self._request_view(request_row),
            "state": state,
            "updated_at": timestamp,
            "reviewer_id": actor.actor_id,
            "decision_reason": normalized_reason,
            "payment_state": "NOT_EXECUTED",
            "external_effect": False,
        }
        with self._connect() as database:
            database.execute(
                "UPDATE settlement_requests "
                "SET state = ?, updated_at = ?, reviewer_id = ?, decision_reason = ? "
                "WHERE request_ref = ? AND state = 'PENDING'",
                (state, timestamp, actor.actor_id, normalized_reason, request_ref),
            )
            database.execute(
                "INSERT INTO settlement_decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    decision_key,
                    request_ref,
                    fingerprint,
                    actor.actor_id,
                    decision,
                    normalized_reason,
                    timestamp,
                    json.dumps(result),
                ),
            )
            database.commit()
        return result

    def _eligible_expert_net(self, actor: SettlementActor, purchase_ref: str) -> tuple[int, str]:
        try:
            settlement = self._ledger.settlements(
                actor=LedgerActor(actor.tenant_id, actor.family_id, actor.actor_id),
                purchase_ref=purchase_ref,
            )
        except LedgerRejected as exc:
            raise SettlementGateNotFound(str(exc)) from exc
        if settlement["track"] != "CONTENT_SUPPORT":
            raise SettlementGateConflict("only CONTENT_SUPPORT can request settlement")
        if settlement["entitlement"] != "ACTIVE":
            raise SettlementGateConflict("purchase is no longer active")
        beneficiary = next(
            (
                item
                for item in settlement["beneficiaries"]
                if item["beneficiary_ref"] == EXPERT_BENEFICIARY
            ),
            None,
        )
        if beneficiary is None or beneficiary["net_amount"] <= 0:
            raise SettlementGateConflict("expert net settlement is unavailable")
        return beneficiary["net_amount"], settlement["currency"]

    @staticmethod
    def _request_view(row: sqlite3.Row) -> dict[str, object]:
        return {
            "request_ref": row["request_ref"],
            "purchase_ref": row["purchase_ref"],
            "beneficiary_ref": row["beneficiary_ref"],
            "amount": row["amount"],
            "currency": row["currency"],
            "state": row["state"],
            "requester_id": row["requester_id"],
            "reviewer_id": row["reviewer_id"],
            "decision_reason": row["decision_reason"],
            "payment_state": "NOT_EXECUTED",
            "source": "SANDBOX_SYNTHETIC",
            "fixture_only": True,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "external_effect": False,
        }

    def _connect(self) -> sqlite3.Connection:
        database = sqlite3.connect(self._path)
        database.row_factory = sqlite3.Row
        return database

    @staticmethod
    def _assert_actor(actor: SettlementActor, *roles: str) -> None:
        if not all((actor.tenant_id, actor.family_id, actor.actor_id, actor.role)):
            raise SettlementGateRejected("trusted synthetic actor scope required")
        if not actor.tenant_id.startswith("tenant.synthetic"):
            raise SettlementGateRejected("trusted synthetic actor scope required")
        if not actor.family_id.startswith("family.synthetic"):
            raise SettlementGateRejected("trusted synthetic actor scope required")
        if not actor.actor_id.startswith("actor.synthetic"):
            raise SettlementGateRejected("trusted synthetic actor scope required")
        if actor.role not in roles:
            raise SettlementGateRejected("settlement actor role denied")

    @staticmethod
    def _fingerprint(*values: str) -> str:
        return json.dumps(values, ensure_ascii=True)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
