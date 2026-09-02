from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from poc.standalone_live_commerce_sandbox.commerce_api import create_app


def headers(
    *, role: str = "ADULT_VIEWER", family: str = "family.synthetic.alpha"
) -> dict[str, str]:
    return {
        "X-Sandbox-Source": "SANDBOX_SYNTHETIC",
        "X-Fixture-Only": "true",
        "X-Tenant-Id": "tenant.synthetic.alpha",
        "X-Family-Id": family,
        "X-Actor-Id": "actor.synthetic.adult",
        "X-Actor-Role": role,
    }


def test_membership_and_cash_support_are_adult_only() -> None:
    client = TestClient(create_app())
    membership = client.get("/sandbox/live-commerce/membership", headers=headers())
    assert membership.json()["membership"] == "ORANGE_LIGHT_MEMBER"
    supported = client.post(
        "/sandbox/live-commerce/sessions/media.synthetic.1/support",
        headers=headers(),
        json={
            "intent_ref": "support.1",
            "idempotency_key": "support-key.1",
            "kind": "TIP",
            "amount": 500,
            "currency": "CNY_CENT",
        },
    )
    assert supported.status_code == 200
    assert supported.json()["external_effect"] is False
    assert sum(item["amount"] for item in supported.json()["allocations"]) == 500


def test_auth_child_and_invalid_money_fail_closed() -> None:
    client = TestClient(create_app())
    url = "/sandbox/live-commerce/sessions/media.synthetic.1/support"
    payload = {
        "intent_ref": "support.2",
        "idempotency_key": "support-key.2",
        "kind": "TIP",
        "amount": 500,
        "currency": "CNY_CENT",
    }
    assert client.post(url, json=payload).status_code == 401
    assert client.post(url, headers=headers(role="CHILD"), json=payload).status_code == 403
    assert client.post(url, headers=headers(), json={**payload, "amount": 0}).status_code == 422


def test_support_is_idempotent_and_conflict_returns_409() -> None:
    client = TestClient(create_app())
    url = "/sandbox/live-commerce/sessions/media.synthetic.1/support"
    payload = {
        "intent_ref": "support.3",
        "idempotency_key": "support-key.3",
        "kind": "POINTS",
        "amount": 100,
        "currency": "POINT",
    }
    first = client.post(url, headers=headers(), json=payload)
    second = client.post(url, headers=headers(), json=payload)
    assert first.json() == second.json()
    conflict = client.post(url, headers=headers(), json={**payload, "amount": 200})
    assert conflict.status_code == 409


def test_refund_and_chargeback_reverse_split_and_reject_cross_family() -> None:
    client = TestClient(create_app())
    support_url = "/sandbox/live-commerce/sessions/media.synthetic.1/support"
    support = {
        "intent_ref": "support.4",
        "idempotency_key": "support-key.4",
        "kind": "TIP",
        "amount": 500,
        "currency": "CNY_CENT",
    }
    assert client.post(support_url, headers=headers(), json=support).status_code == 200
    refund = {
        "refund_ref": "refund.4",
        "support_intent_ref": "support.4",
        "idempotency_key": "refund-key.4",
        "reason": "chargeback",
    }
    denied = client.post(
        "/sandbox/live-commerce/refunds",
        headers=headers(family="family.synthetic.other"),
        json=refund,
    )
    assert denied.status_code == 403
    reversed_response = client.post(
        "/sandbox/live-commerce/refunds", headers=headers(), json=refund
    )
    assert reversed_response.status_code == 200
    assert reversed_response.json()["status"] == "SANDBOX_REVERSED"
    assert sum(item["amount"] for item in reversed_response.json()["reversed_allocations"]) == -500
    assert (
        client.post("/sandbox/live-commerce/refunds", headers=headers(), json=refund).json()
        == reversed_response.json()
    )


@pytest.mark.parametrize(
    ("track", "currency"),
    [
        ("CONTENT_SUPPORT", "CNY_CENT"),
        ("MEMBERSHIP", "CNY_CENT"),
        ("MEDIA_ENTITLEMENT", "CNY_CENT"),
        ("SERVICE_OFFERING", "CNY_CENT"),
        ("POINTS", "POINT"),
    ],
)
def test_five_track_http_ledger_survives_restart_and_reversal(
    tmp_path: Path, track: str, currency: str
) -> None:
    database = tmp_path / "commerce.sqlite3"
    client = TestClient(create_app(database))
    purchase_ref = f"purchase:{track}:http"
    payload = {
        "purchase_ref": purchase_ref,
        "track": track,
        "subject_ref": f"subject:{track}:http",
        "amount": 9900,
        "currency": currency,
        "idempotency_key": f"purchase-key:{track}:http",
    }
    purchased = client.post("/sandbox/live-commerce/purchases", headers=headers(), json=payload)
    assert purchased.status_code == 200
    assert purchased.json()["cash_amount"] == (0 if track == "POINTS" else 9900)
    restarted = TestClient(create_app(database))
    balance_url = f"/sandbox/live-commerce/purchases/{purchase_ref}/balances"
    balance = restarted.get(balance_url, headers=headers())
    assert balance.status_code == 200
    assert balance.json()["cash"] == (0 if track == "POINTS" else 9900)
    assert balance.json()["settlement"] == 9900
    assert balance.json()["entitlement"] == "ACTIVE"

    reversal = restarted.post(
        f"/sandbox/live-commerce/purchases/{purchase_ref}/reversals",
        headers=headers(),
        json={
            "reversal_ref": f"reversal:{track}:http",
            "idempotency_key": f"reversal-key:{track}:http",
            "reason": "撤销合成演示记录",
        },
    )
    assert reversal.status_code == 200
    after_restart = TestClient(create_app(database)).get(balance_url, headers=headers())
    assert after_restart.json()["cash"] == 0
    assert after_restart.json()["settlement"] == 0
    assert after_restart.json()["entitlement"] == "REVOKED"


def test_persistent_ledger_rejects_cross_family_child_and_conflict(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "commerce.sqlite3"))
    payload = {
        "purchase_ref": "purchase:membership:http",
        "track": "MEMBERSHIP",
        "subject_ref": "membership:orange-light:month",
        "amount": 3000,
        "currency": "CNY_CENT",
        "idempotency_key": "purchase-key:membership:http",
    }
    url = "/sandbox/live-commerce/purchases"
    assert client.post(url, headers=headers(role="CHILD"), json=payload).status_code == 403
    assert client.post(url, headers=headers(), json=payload).status_code == 200
    conflict = client.post(url, headers=headers(), json={**payload, "amount": 4000})
    assert conflict.status_code == 409
    balance_url = "/sandbox/live-commerce/purchases/purchase:membership:http/balances"
    assert (
        client.get(balance_url, headers=headers(family="family.synthetic.other")).status_code == 404
    )
