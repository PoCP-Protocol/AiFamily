from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from poc.standalone_live_commerce_sandbox.commerce_api import create_app


def headers(
    *,
    role: str = "ADULT_VIEWER",
    family: str = "family.synthetic.alpha",
    actor: str = "actor.synthetic.adult",
) -> dict[str, str]:
    return {
        "X-Sandbox-Source": "SANDBOX_SYNTHETIC",
        "X-Fixture-Only": "true",
        "X-Tenant-Id": "tenant.synthetic.alpha",
        "X-Family-Id": family,
        "X-Actor-Id": actor,
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


@pytest.mark.parametrize(
    ("track", "amount", "currency", "expert_net", "platform_net"),
    [
        ("CONTENT_SUPPORT", 500, "CNY_CENT", 400, 100),
        ("POINTS", 100, "POINT", 80, 20),
    ],
)
def test_http_settlements_are_scoped_restart_safe_and_zero_after_reversal(
    tmp_path: Path,
    track: str,
    amount: int,
    currency: str,
    expert_net: int,
    platform_net: int,
) -> None:
    database = tmp_path / "commerce.sqlite3"
    purchase_ref = f"purchase:settlement:http:{track}"
    purchase = {
        "purchase_ref": purchase_ref,
        "track": track,
        "subject_ref": f"subject:settlement:http:{track}",
        "amount": amount,
        "currency": currency,
        "idempotency_key": f"purchase-key:settlement:http:{track}",
    }
    client = TestClient(create_app(database))
    assert (
        client.post(
            "/sandbox/live-commerce/purchases", headers=headers(), json=purchase
        ).status_code
        == 200
    )

    settlement_url = f"/sandbox/live-commerce/purchases/{purchase_ref}/settlements"
    settlement = TestClient(create_app(database)).get(settlement_url, headers=headers())
    assert settlement.status_code == 200
    assert settlement.json() == {
        "purchase_ref": purchase_ref,
        "track": track,
        "currency": currency,
        "entitlement": "ACTIVE",
        "beneficiaries": [
            {"beneficiary_ref": "expert.synthetic.1", "net_amount": expert_net},
            {"beneficiary_ref": "platform:aifamily", "net_amount": platform_net},
        ],
        "total": amount,
        "external_effect": False,
        "source": "SANDBOX_SYNTHETIC",
        "fixture_only": True,
    }

    reversal = TestClient(create_app(database)).post(
        f"/sandbox/live-commerce/purchases/{purchase_ref}/reversals",
        headers=headers(),
        json={
            "reversal_ref": f"reversal:settlement:http:{track}",
            "idempotency_key": f"reversal-key:settlement:http:{track}",
            "reason": "synthetic settlement reversal",
        },
    )
    assert reversal.status_code == 200
    after_restart = TestClient(create_app(database)).get(settlement_url, headers=headers())
    assert after_restart.status_code == 200
    assert after_restart.json()["entitlement"] == "REVOKED"
    assert after_restart.json()["beneficiaries"] == [
        {"beneficiary_ref": "expert.synthetic.1", "net_amount": 0},
        {"beneficiary_ref": "platform:aifamily", "net_amount": 0},
    ]
    assert after_restart.json()["total"] == 0


def test_http_settlements_fail_closed_for_scope_child_and_unsafe_actor(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "commerce.sqlite3"))
    purchase_ref = "purchase:settlement:http:scope"
    assert (
        client.post(
            "/sandbox/live-commerce/purchases",
            headers=headers(),
            json={
                "purchase_ref": purchase_ref,
                "track": "CONTENT_SUPPORT",
                "subject_ref": "subject:settlement:http:scope",
                "amount": 500,
                "currency": "CNY_CENT",
                "idempotency_key": "purchase-key:settlement:http:scope",
            },
        ).status_code
        == 200
    )
    url = f"/sandbox/live-commerce/purchases/{purchase_ref}/settlements"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=headers(role="CHILD")).status_code == 403
    assert client.get(url, headers=headers(family="family.synthetic.other")).status_code == 404
    assert (
        client.get(
            url,
            headers={**headers(), "X-Sandbox-Source": "PRODUCTION"},
        ).status_code
        == 401
    )
    assert (
        client.get(
            url,
            headers={**headers(), "X-Actor-Id": "adult.real.1"},
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/sandbox/live-commerce/purchases/purchase:missing/settlements",
            headers=headers(),
        ).status_code
        == 404
    )


def test_http_settlement_gate_persists_human_approval_without_payment(tmp_path: Path) -> None:
    database = tmp_path / "commerce.sqlite3"
    client = TestClient(create_app(database))
    purchase = {
        "purchase_ref": "purchase:support:gate:http",
        "track": "CONTENT_SUPPORT",
        "subject_ref": "session.synthetic.1",
        "amount": 500,
        "currency": "CNY_CENT",
        "idempotency_key": "purchase-key:support:gate:http",
    }
    assert (
        client.post(
            "/sandbox/live-commerce/purchases", headers=headers(), json=purchase
        ).status_code
        == 200
    )
    creator_headers = headers(role="CREATOR_OPERATOR", actor="actor.synthetic.creator.1")
    request_payload = {
        "request_ref": "settlement-request:http:1",
        "purchase_ref": purchase["purchase_ref"],
        "beneficiary_ref": "expert.synthetic.1",
        "idempotency_key": "settlement-request-key:http:1",
    }
    created = client.post(
        "/sandbox/live-commerce/settlement-requests",
        headers=creator_headers,
        json=request_payload,
    )
    assert created.status_code == 200
    assert created.json()["amount"] == 400
    assert created.json()["state"] == "PENDING"
    assert created.json()["requester_id"] == "actor.synthetic.creator.1"
    assert created.json()["created_at"] == created.json()["updated_at"]
    assert (
        client.post(
            "/sandbox/live-commerce/settlement-requests",
            headers=creator_headers,
            json=request_payload,
        ).json()
        == created.json()
    )

    restarted = TestClient(create_app(database))
    reviewer_headers = headers(role="HUMAN_FINANCE_REVIEWER", actor="actor.synthetic.finance.1")
    creator_list = restarted.get(
        "/sandbox/live-commerce/settlement-requests", headers=creator_headers
    )
    reviewer_list = restarted.get(
        "/sandbox/live-commerce/settlement-requests", headers=reviewer_headers
    )
    assert creator_list.json()["requests"] == reviewer_list.json()["requests"]
    assert len(reviewer_list.json()["requests"]) == 1
    other_family_reviewer = headers(
        role="HUMAN_FINANCE_REVIEWER",
        actor="actor.synthetic.finance.1",
        family="family.synthetic.other",
    )
    assert (
        restarted.get(
            "/sandbox/live-commerce/settlement-requests", headers=other_family_reviewer
        ).json()["requests"]
        == []
    )
    decision_payload = {
        "decision_key": "settlement-decision-key:http:1",
        "decision": "APPROVE",
        "reason": "synthetic finance review approved",
    }
    approved = restarted.post(
        "/sandbox/live-commerce/settlement-requests/settlement-request:http:1/decisions",
        headers=reviewer_headers,
        json=decision_payload,
    )
    assert approved.status_code == 200
    assert approved.json()["state"] == "APPROVED"
    assert approved.json()["payment_state"] == "NOT_EXECUTED"
    assert approved.json()["external_effect"] is False
    assert (
        restarted.post(
            "/sandbox/live-commerce/settlement-requests/settlement-request:http:1/decisions",
            headers=other_family_reviewer,
            json={
                "decision_key": "settlement-decision-key:http:cross-family",
                "decision": "REJECT",
                "reason": "cross-family review denied",
            },
        ).status_code
        == 404
    )
    assert (
        TestClient(create_app(database))
        .post(
            "/sandbox/live-commerce/settlement-requests/settlement-request:http:1/decisions",
            headers=reviewer_headers,
            json=decision_payload,
        )
        .json()
        == approved.json()
    )


def test_http_settlement_gate_revalidates_reversal_and_rejects_conflicts(tmp_path: Path) -> None:
    database = tmp_path / "commerce.sqlite3"
    client = TestClient(create_app(database))
    purchase_ref = "purchase:support:gate:withdrawn"
    assert (
        client.post(
            "/sandbox/live-commerce/purchases",
            headers=headers(),
            json={
                "purchase_ref": purchase_ref,
                "track": "CONTENT_SUPPORT",
                "subject_ref": "session.synthetic.1",
                "amount": 500,
                "currency": "CNY_CENT",
                "idempotency_key": "purchase-key:support:gate:withdrawn",
            },
        ).status_code
        == 200
    )
    creator_headers = headers(role="CREATOR_OPERATOR", actor="actor.synthetic.creator.1")
    request_payload = {
        "request_ref": "settlement-request:http:withdrawn",
        "purchase_ref": purchase_ref,
        "beneficiary_ref": "expert.synthetic.1",
        "idempotency_key": "settlement-request-key:http:withdrawn",
    }
    assert (
        client.post(
            "/sandbox/live-commerce/settlement-requests",
            headers=creator_headers,
            json=request_payload,
        ).status_code
        == 200
    )
    conflict = client.post(
        "/sandbox/live-commerce/settlement-requests",
        headers=creator_headers,
        json={**request_payload, "request_ref": "settlement-request:http:changed"},
    )
    assert conflict.status_code == 409
    assert (
        client.post(
            f"/sandbox/live-commerce/purchases/{purchase_ref}/reversals",
            headers=headers(),
            json={
                "reversal_ref": "reversal:support:gate:withdrawn",
                "idempotency_key": "reversal-key:support:gate:withdrawn",
                "reason": "synthetic support withdrawn",
            },
        ).status_code
        == 200
    )
    reviewer_headers = headers(role="HUMAN_FINANCE_REVIEWER", actor="actor.synthetic.finance.1")
    decision_url = (
        "/sandbox/live-commerce/settlement-requests/settlement-request:http:withdrawn/decisions"
    )
    decision = client.post(
        decision_url,
        headers=reviewer_headers,
        json={
            "decision_key": "settlement-decision-key:http:withdrawn",
            "decision": "APPROVE",
            "reason": "must revalidate purchase",
        },
    )
    assert decision.status_code == 409


def test_http_settlement_gate_permissions_scope_and_missing_fail_closed(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "commerce.sqlite3"))
    list_url = "/sandbox/live-commerce/settlement-requests"
    assert client.get(list_url).status_code == 401
    assert client.get(list_url, headers=headers(role="CHILD")).status_code == 403
    assert client.get(list_url, headers=headers(role="ADULT_VIEWER")).status_code == 403
    assert (
        client.post(
            "/sandbox/live-commerce/settlement-requests",
            headers=headers(role="ADULT_VIEWER"),
            json={
                "request_ref": "settlement-request:viewer-denied",
                "purchase_ref": "purchase:missing",
                "beneficiary_ref": "expert.synthetic.1",
                "idempotency_key": "settlement-request-key:viewer-denied",
            },
        ).status_code
        == 403
    )
    assert (
        client.get(
            list_url,
            headers=headers(
                role="CREATOR_OPERATOR",
                actor="actor.synthetic.creator.1",
                family="family.synthetic.other",
            ),
        ).json()["requests"]
        == []
    )
    reviewer_headers = headers(role="HUMAN_FINANCE_REVIEWER", actor="actor.synthetic.finance.1")
    assert (
        client.post(
            "/sandbox/live-commerce/settlement-requests/missing/decisions",
            headers=reviewer_headers,
            json={
                "decision_key": "settlement-decision-key:missing",
                "decision": "REJECT",
                "reason": "missing request",
            },
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/sandbox/live-commerce/settlement-requests/missing/decisions",
            headers=reviewer_headers,
            json={
                "decision_key": "settlement-decision-key:blank-reason",
                "decision": "REJECT",
                "reason": " ",
            },
        ).status_code
        == 422
    )
