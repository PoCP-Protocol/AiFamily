from dataclasses import replace
from pathlib import Path

import pytest

from poc.standalone_live_commerce_sandbox.ledger_sandbox import (
    LedgerActor,
    LedgerRejected,
    Purchase,
    ThreeLedgerSandbox,
    Track,
)


def actor() -> LedgerActor:
    return LedgerActor("tenant.synthetic.alpha", "family.synthetic.alpha", "adult.synthetic.1")


@pytest.mark.parametrize("track", list(Track))
def test_five_revenue_tracks_are_separate_and_restart_readable(
    tmp_path: Path, track: Track
) -> None:
    path = tmp_path / "three-ledgers.sqlite3"
    ledger = ThreeLedgerSandbox(path)
    command = Purchase(
        purchase_ref=f"purchase:{track}",
        track=track,
        subject_ref=f"subject:{track}",
        amount=500,
        currency="POINT" if track is Track.POINTS else "CNY_CENT",
        idempotency_key=f"purchase-key:{track}",
    )
    result = ledger.purchase(actor=actor(), command=command)
    assert result["track"] == track
    assert result["external_effect"] is False
    assert result["expert_accrual"] + result["platform_accrual"] == 500
    restarted = ThreeLedgerSandbox(path)
    balances = restarted.balances(actor=actor(), purchase_ref=command.purchase_ref)
    assert balances["entitlement"] == "ACTIVE"
    assert balances["cash"] == (0 if track is Track.POINTS else 500)
    assert balances["settlement"] == 500


def test_refund_or_chargeback_reverses_all_three_ledgers_across_restart(tmp_path: Path) -> None:
    path = tmp_path / "three-ledgers.sqlite3"
    ledger = ThreeLedgerSandbox(path)
    command = Purchase(
        "purchase:service", Track.SERVICE_OFFERING, "service:30m", 9900, "CNY_CENT", "key:service"
    )
    ledger.purchase(actor=actor(), command=command)
    reversal = ledger.reverse(
        actor=actor(),
        purchase_ref=command.purchase_ref,
        reversal_ref="chargeback:1",
        idempotency_key="key:chargeback:1",
        reason="synthetic chargeback",
    )
    assert reversal["cash_reversal"] == -9900
    assert reversal["settlement_reversal"] == -9900
    assert (
        ledger.reverse(
            actor=actor(),
            purchase_ref=command.purchase_ref,
            reversal_ref="chargeback:1",
            idempotency_key="key:chargeback:1",
            reason="synthetic chargeback",
        )
        == reversal
    )
    assert ThreeLedgerSandbox(path).balances(actor=actor(), purchase_ref=command.purchase_ref) == {
        "purchase_ref": command.purchase_ref,
        "cash": 0,
        "settlement": 0,
        "entitlement": "REVOKED",
        "external_effect": False,
    }


def test_child_cross_family_currency_and_idempotency_fail_closed(tmp_path: Path) -> None:
    ledger = ThreeLedgerSandbox(tmp_path / "three-ledgers.sqlite3")
    command = Purchase(
        "purchase:membership", Track.MEMBERSHIP, "member:month", 3000, "CNY_CENT", "key:membership"
    )
    with pytest.raises(LedgerRejected, match="child"):
        ledger.purchase(actor=replace(actor(), is_adult=False), command=command)
    ledger.purchase(actor=actor(), command=command)
    with pytest.raises(LedgerRejected, match="idempotency"):
        ledger.purchase(actor=actor(), command=replace(command, amount=4000))
    with pytest.raises(LedgerRejected, match="currency"):
        ledger.purchase(
            actor=actor(),
            command=replace(command, purchase_ref="bad", idempotency_key="bad", currency="POINT"),
        )
    with pytest.raises(LedgerRejected, match="actor scope"):
        ledger.reverse(
            actor=replace(actor(), family_id="family.synthetic.other"),
            purchase_ref=command.purchase_ref,
            reversal_ref="refund:other",
            idempotency_key="key:other",
            reason="cross family",
        )
    with pytest.raises(LedgerRejected, match="actor scope"):
        ledger.balances(
            actor=replace(actor(), family_id="family.synthetic.other"),
            purchase_ref=command.purchase_ref,
        )
