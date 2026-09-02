from dataclasses import replace
from pathlib import Path

import pytest

from poc.standalone_live_commerce_sandbox.ledger_sandbox import (
    LedgerActor,
    Purchase,
    ThreeLedgerSandbox,
    Track,
)
from poc.standalone_live_commerce_sandbox.settlement_gate import (
    EXPERT_BENEFICIARY,
    SettlementActor,
    SettlementGate,
    SettlementGateConflict,
    SettlementGateNotFound,
    SettlementGateRejected,
)


def creator() -> SettlementActor:
    return SettlementActor(
        "tenant.synthetic.alpha",
        "family.synthetic.alpha",
        "actor.synthetic.creator.1",
        "CREATOR_OPERATOR",
    )


def reviewer() -> SettlementActor:
    return SettlementActor(
        "tenant.synthetic.alpha",
        "family.synthetic.alpha",
        "actor.synthetic.finance.1",
        "HUMAN_FINANCE_REVIEWER",
    )


def create_support(ledger: ThreeLedgerSandbox, purchase_ref: str = "purchase:support:1") -> None:
    ledger.purchase(
        actor=LedgerActor(
            "tenant.synthetic.alpha", "family.synthetic.alpha", "actor.synthetic.adult"
        ),
        command=Purchase(
            purchase_ref=purchase_ref,
            track=Track.CONTENT_SUPPORT,
            subject_ref="session.synthetic.1",
            amount=500,
            currency="CNY_CENT",
            idempotency_key=f"purchase-key:{purchase_ref}",
        ),
    )


def test_request_review_and_restart_without_payment_effect(tmp_path: Path) -> None:
    path = tmp_path / "commerce.sqlite3"
    ledger = ThreeLedgerSandbox(path)
    create_support(ledger)
    gate = SettlementGate(path, ledger)
    requested = gate.request(
        actor=creator(),
        request_ref="settlement-request:1",
        purchase_ref="purchase:support:1",
        beneficiary_ref=EXPERT_BENEFICIARY,
        idempotency_key="settlement-request-key:1",
    )
    assert requested["amount"] == 400
    assert requested["currency"] == "CNY_CENT"
    assert requested["state"] == "PENDING"
    assert requested["requester_id"] == "actor.synthetic.creator.1"
    assert requested["created_at"] == requested["updated_at"]
    assert requested["external_effect"] is False
    assert (
        gate.request(
            actor=creator(),
            request_ref="settlement-request:1",
            purchase_ref="purchase:support:1",
            beneficiary_ref=EXPERT_BENEFICIARY,
            idempotency_key="settlement-request-key:1",
        )
        == requested
    )

    restarted = SettlementGate(path, ThreeLedgerSandbox(path))
    assert restarted.list_requests(actor=creator()) == [requested]
    assert restarted.list_requests(actor=reviewer()) == [requested]
    approved = restarted.decide(
        actor=reviewer(),
        request_ref="settlement-request:1",
        decision_key="settlement-decision-key:1",
        decision="APPROVE",
        reason="synthetic finance review approved",
    )
    assert approved["state"] == "APPROVED"
    assert approved["payment_state"] == "NOT_EXECUTED"
    assert approved["external_effect"] is False
    assert (
        SettlementGate(path, ThreeLedgerSandbox(path)).decide(
            actor=reviewer(),
            request_ref="settlement-request:1",
            decision_key="settlement-decision-key:1",
            decision="APPROVE",
            reason="synthetic finance review approved",
        )
        == approved
    )


def test_request_and_decision_idempotency_conflicts(tmp_path: Path) -> None:
    path = tmp_path / "commerce.sqlite3"
    ledger = ThreeLedgerSandbox(path)
    create_support(ledger)
    gate = SettlementGate(path, ledger)
    gate.request(
        actor=creator(),
        request_ref="settlement-request:1",
        purchase_ref="purchase:support:1",
        beneficiary_ref=EXPERT_BENEFICIARY,
        idempotency_key="settlement-request-key:1",
    )
    with pytest.raises(SettlementGateConflict, match="idempotency"):
        gate.request(
            actor=creator(),
            request_ref="settlement-request:changed",
            purchase_ref="purchase:support:1",
            beneficiary_ref=EXPERT_BENEFICIARY,
            idempotency_key="settlement-request-key:1",
        )
    rejected = gate.decide(
        actor=reviewer(),
        request_ref="settlement-request:1",
        decision_key="settlement-decision-key:1",
        decision="REJECT",
        reason="synthetic finance rejection",
    )
    assert rejected["state"] == "REJECTED"
    assert rejected["payment_state"] == "NOT_EXECUTED"
    assert rejected["external_effect"] is False
    with pytest.raises(SettlementGateConflict, match="idempotency"):
        gate.decide(
            actor=reviewer(),
            request_ref="settlement-request:1",
            decision_key="settlement-decision-key:1",
            decision="APPROVE",
            reason="changed decision",
        )


def test_decision_revalidates_active_purchase(tmp_path: Path) -> None:
    path = tmp_path / "commerce.sqlite3"
    ledger = ThreeLedgerSandbox(path)
    create_support(ledger)
    gate = SettlementGate(path, ledger)
    gate.request(
        actor=creator(),
        request_ref="settlement-request:1",
        purchase_ref="purchase:support:1",
        beneficiary_ref=EXPERT_BENEFICIARY,
        idempotency_key="settlement-request-key:1",
    )
    ledger.reverse(
        actor=LedgerActor(
            "tenant.synthetic.alpha", "family.synthetic.alpha", "actor.synthetic.adult"
        ),
        purchase_ref="purchase:support:1",
        reversal_ref="reversal:support:1",
        idempotency_key="reversal-key:support:1",
        reason="synthetic purchase withdrawn",
    )
    with pytest.raises(SettlementGateConflict, match="no longer active"):
        SettlementGate(path, ThreeLedgerSandbox(path)).decide(
            actor=reviewer(),
            request_ref="settlement-request:1",
            decision_key="settlement-decision-key:1",
            decision="APPROVE",
            reason="must revalidate before approval",
        )


def test_scope_roles_missing_and_content_track_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "commerce.sqlite3"
    ledger = ThreeLedgerSandbox(path)
    create_support(ledger)
    ledger.purchase(
        actor=LedgerActor(
            "tenant.synthetic.alpha", "family.synthetic.alpha", "actor.synthetic.adult"
        ),
        command=Purchase(
            "purchase:points:1",
            Track.POINTS,
            "points.synthetic.1",
            100,
            "POINT",
            "purchase-key:points:1",
        ),
    )
    gate = SettlementGate(path, ledger)
    gate.request(
        actor=creator(),
        request_ref="settlement-request:scoped",
        purchase_ref="purchase:support:1",
        beneficiary_ref=EXPERT_BENEFICIARY,
        idempotency_key="settlement-request-key:scoped",
    )
    with pytest.raises(SettlementGateConflict, match="CONTENT_SUPPORT"):
        gate.request(
            actor=creator(),
            request_ref="settlement-request:points",
            purchase_ref="purchase:points:1",
            beneficiary_ref=EXPERT_BENEFICIARY,
            idempotency_key="settlement-request-key:points",
        )
    with pytest.raises(SettlementGateNotFound):
        gate.request(
            actor=creator(),
            request_ref="settlement-request:missing",
            purchase_ref="purchase:missing",
            beneficiary_ref=EXPERT_BENEFICIARY,
            idempotency_key="settlement-request-key:missing",
        )
    with pytest.raises(SettlementGateRejected, match="role"):
        gate.list_requests(actor=replace(creator(), role="ADULT_VIEWER"))
    with pytest.raises(SettlementGateRejected, match="scope"):
        gate.list_requests(actor=replace(creator(), actor_id="adult.real.1"))
    assert gate.list_requests(actor=replace(creator(), actor_id="actor.synthetic.creator.2")) == []
    with pytest.raises(SettlementGateNotFound):
        gate.request(
            actor=replace(creator(), family_id="family.synthetic.other"),
            request_ref="settlement-request:cross-family",
            purchase_ref="purchase:support:1",
            beneficiary_ref=EXPERT_BENEFICIARY,
            idempotency_key="settlement-request-key:cross-family",
        )
    with pytest.raises(SettlementGateNotFound):
        gate.decide(
            actor=replace(reviewer(), family_id="family.synthetic.other"),
            request_ref="settlement-request:scoped",
            decision_key="settlement-decision-key:cross-family",
            decision="REJECT",
            reason="not in reviewer scope",
        )
