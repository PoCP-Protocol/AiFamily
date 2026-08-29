"""Automated FastAPI TestClient coverage — PR-001R item 8: turns the
original manual smoke test (run by hand once during PR #27's review) into
a repeatable test. Covers: full chain via real HTTP calls, invalid parent,
cross-tenant, AI provenance missing, AI actor validate rejected, human
validate accepted.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ..api.dependencies import get_actor_context, get_repository
from ..api.routes import router
from ..application.context import ActorContext
from ..infrastructure.fake_repository import FakeProductIntelligenceRepository


def _build_client(shared_repo, context_by_call):
    """`context_by_call` is a mutable single-item list so tests can swap
    the acting context between calls on the same client (simulating
    different requests from different actors) without rebuilding the app.
    """
    app = FastAPI()
    app.include_router(router)

    async def override_repo():
        yield shared_repo

    async def override_context():
        return context_by_call[0]

    app.dependency_overrides[get_repository] = override_repo
    app.dependency_overrides[get_actor_context] = override_context
    return TestClient(app)


@pytest.fixture
def repo():
    return FakeProductIntelligenceRepository()


@pytest.fixture
def context_slot():
    return [ActorContext(
        actor_id="human-1", actor_type="HUMAN", tenant_scope="tenant-a",
        permissions=frozenset({"product_intelligence.hypothesis.review"}),
    )]


@pytest.fixture
def client(repo, context_slot):
    return _build_client(repo, context_slot)


def test_full_chain_via_http(client):
    r = client.post("/product-intelligence/market-signals", json={"raw_text": "test signal"})
    assert r.status_code == 200
    signal_id = r.json()["id"]

    r = client.post("/product-intelligence/customer-insights", json={"signal_id": signal_id, "statement": "insight"})
    assert r.status_code == 200
    insight_id = r.json()["id"]

    r = client.post("/product-intelligence/opportunities", json={"insight_id": insight_id, "statement": "opp"})
    opp_id = r.json()["id"]

    r = client.post("/product-intelligence/growth-problems", json={"opportunity_id": opp_id, "symptom": "sym"})
    problem_id = r.json()["id"]

    r = client.post("/product-intelligence/growth-hypotheses", json={"problem_id": problem_id, "statement": "h"})
    assert r.json()["status"] == "DRAFT"
    hyp_id = r.json()["id"]

    r = client.post("/product-intelligence/growth-strategies", json={"problem_id": problem_id, "hypothesis_ids": [hyp_id], "statement": "strat"})
    strat_id = r.json()["id"]

    r = client.post("/product-intelligence/product-concepts", json={"strategy_id": strat_id, "title": "concept"})
    concept_id = r.json()["id"]

    r = client.get(f"/product-intelligence/product-concepts/{concept_id}/chain")
    assert r.status_code == 200
    assert r.json()["market_signal"]["id"] == signal_id


def test_invalid_parent_returns_404(client):
    r = client.post("/product-intelligence/customer-insights", json={"signal_id": "does-not-exist", "statement": "x"})
    assert r.status_code == 404


def test_ai_actor_validate_rejected_human_accepted_via_http(client, context_slot):
    r = client.post("/product-intelligence/market-signals", json={"raw_text": "x"})
    signal_id = r.json()["id"]
    r = client.post("/product-intelligence/customer-insights", json={"signal_id": signal_id, "statement": "i"})
    insight_id = r.json()["id"]
    r = client.post("/product-intelligence/opportunities", json={"insight_id": insight_id, "statement": "o"})
    opp_id = r.json()["id"]
    r = client.post("/product-intelligence/growth-problems", json={"opportunity_id": opp_id, "symptom": "p"})
    problem_id = r.json()["id"]
    r = client.post("/product-intelligence/growth-hypotheses", json={"problem_id": problem_id, "statement": "h2"})
    hyp_id = r.json()["id"]

    context_slot[0] = ActorContext(actor_id="ai-bot", actor_type="AI", tenant_scope="tenant-a")
    r = client.post(f"/product-intelligence/growth-hypotheses/{hyp_id}/validate", json={"reason": "auto-approve"})
    assert r.status_code == 403

    context_slot[0] = ActorContext(
        actor_id="human-1", actor_type="HUMAN", tenant_scope="tenant-a",
        permissions=frozenset({"product_intelligence.hypothesis.review"}),
    )
    r = client.post(f"/product-intelligence/growth-hypotheses/{hyp_id}/validate", json={"reason": "reviewed"})
    assert r.status_code == 200
    assert r.json()["status"] == "VALIDATED"


def test_cross_tenant_via_http_returns_404(client, context_slot):
    r = client.post("/product-intelligence/market-signals", json={"raw_text": "tenant-a signal"})
    signal_id = r.json()["id"]

    context_slot[0] = ActorContext(actor_id="human-2", actor_type="HUMAN", tenant_scope="tenant-b")
    r = client.post("/product-intelligence/customer-insights", json={"signal_id": signal_id, "statement": "tenant-b reaching into tenant-a"})
    assert r.status_code == 404


def test_ai_actor_missing_provenance_via_http_returns_400(client, context_slot):
    r = client.post("/product-intelligence/market-signals", json={"raw_text": "x"})
    signal_id = r.json()["id"]

    context_slot[0] = ActorContext(actor_id="ai-bot", actor_type="AI", tenant_scope="tenant-a")
    r = client.post("/product-intelligence/customer-insights", json={"signal_id": signal_id, "statement": "no provenance supplied"})
    assert r.status_code == 400
