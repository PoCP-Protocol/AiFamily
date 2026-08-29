"""FastAPI TestClient coverage for `api/zone_routes.py` — same style as
`test_api_endpoints.py`: `app.dependency_overrides` swaps in a
`FakeZoneAssessmentRepository` and a mutable `context_slot` so tests can
change the acting context between calls on the same client.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ..api.dependencies import get_actor_context, get_repository
from ..api.zone_routes import get_zone_repository, router
from ..application import zone_commands
from ..application.context import ActorContext
from ..domain.entities import ProductConcept
from ..infrastructure.fake_repository import FakeProductIntelligenceRepository
from ..infrastructure.zone_fake_repository import FakeZoneAssessmentRepository

UTC_NOW = datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc)

ZONE_REVIEW_PERMISSION = zone_commands.ZONE_REVIEW_PERMISSION


def _build_policy_payload() -> dict:
    return dict(
        policy_id="zone-policy-v0",
        version=1,
        dimension_definitions={
            "customer_scarcity": "positive",
            "replaceability": "negative",
            "data_advantage": "positive",
            "network_effect": "positive",
            "learning_effect": "positive",
            "switching_cost": "positive",
        },
        weights={
            "customer_scarcity": 1.0,
            "replaceability": 1.0,
            "data_advantage": 1.0,
            "network_effect": 1.0,
            "learning_effect": 1.0,
            "switching_cost": 1.0,
        },
        thresholds={
            "unique_defensibility_min": 75.0,
            "unique_floor_gate_min": 50.0,
            "commodity_differentiation_max": 40.0,
            "commodity_defensibility_max": 40.0,
        },
        classification_rules="UNIQUE if defensibility>=75 and floor>=50; COMMODITY if diff<40 and def<40; else ADVANTAGE",
        review_policy={"unique_requires_reviewers": 1},
        effective_from=UTC_NOW,
        status="ACTIVE",
    )


def _dimension_payload(score: float = 90.0) -> list[dict]:
    return [
        {
            "dimension": dimension,
            "score": score,
            "rationale": "strong signal",
            "evidence_refs": [f"evidence-{dimension}"],
            "evidence_strength": 0.8,
            "assessed_by": "human-scorer-1",
            "assessed_at": UTC_NOW.isoformat(),
        }
        for dimension in (
            "customer_scarcity",
            "replaceability",
            "data_advantage",
            "network_effect",
            "learning_effect",
            "switching_cost",
        )
    ]


def _seeded_product_intelligence_repo() -> FakeProductIntelligenceRepository:
    """Seeds the "concept-1"/"tenant-a" ProductConcept every test in this
    file references. `create_zone_assessment` now composes this port
    alongside `ZoneAssessmentRepositoryPort` specifically to enforce that
    `product_concept_id` exists and belongs to the caller's tenant — see
    `application/zone_commands.py` "Integration fix" item 2.
    """
    repo = FakeProductIntelligenceRepository()
    now = datetime.now(timezone.utc)
    repo._product_concepts["concept-1"] = ProductConcept(
        id="concept-1", created_at=now, updated_at=now, created_by="test-fixture",
        tenant_scope="tenant-a", strategy_id="stub-strategy-1", title="stub product concept",
    )
    return repo


def _build_client(shared_repo, context_by_call):
    app = FastAPI()
    app.include_router(router)
    product_intelligence_repo = _seeded_product_intelligence_repo()

    async def override_repo():
        yield shared_repo

    async def override_product_intelligence_repo():
        yield product_intelligence_repo

    async def override_context():
        return context_by_call[0]

    app.dependency_overrides[get_zone_repository] = override_repo
    app.dependency_overrides[get_repository] = override_product_intelligence_repo
    app.dependency_overrides[get_actor_context] = override_context
    return TestClient(app)


@pytest.fixture
def repo():
    return FakeZoneAssessmentRepository()


@pytest.fixture
def context_slot():
    return [ActorContext(
        actor_id="human-1", actor_type="HUMAN", tenant_scope="tenant-a",
        permissions=frozenset({ZONE_REVIEW_PERMISSION}),
    )]


@pytest.fixture
def client(repo, context_slot):
    return _build_client(repo, context_slot)


@pytest.fixture(autouse=True)
async def _seed_active_policy(repo):
    from ..domain.zone_entities import ZonePolicyVersion
    await repo.save_zone_policy_version(ZonePolicyVersion(**_build_policy_payload()))


def test_create_score_submit_approve_flow_via_http(client):
    r = client.post(
        "/product-intelligence/product-concepts/concept-1/zone-assessments",
        json={"zone_policy_version_id": "zone-policy-v0"},
    )
    assert r.status_code == 200
    assessment_id = r.json()["id"]
    assert r.json()["status"] == "DRAFT"

    r = client.post(
        f"/product-intelligence/zone-assessments/{assessment_id}/score",
        json={"dimension_assessments": _dimension_payload()},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "SCORED"
    assert r.json()["recommended_zone"] == "UNIQUE"

    r = client.post(f"/product-intelligence/zone-assessments/{assessment_id}/submit-review")
    assert r.status_code == 200
    assert r.json()["status"] == "UNDER_REVIEW"

    r = client.post(
        f"/product-intelligence/zone-assessments/{assessment_id}/approve",
        json={"approved_zone": "UNIQUE", "review_reason": "matches evidence"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "APPROVED"
    assert r.json()["approved_zone"] == "UNIQUE"

    r = client.get(f"/product-intelligence/zone-assessments/{assessment_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "APPROVED"


def test_reject_flow_via_http(client):
    r = client.post(
        "/product-intelligence/product-concepts/concept-1/zone-assessments",
        json={"zone_policy_version_id": "zone-policy-v0"},
    )
    assessment_id = r.json()["id"]
    client.post(
        f"/product-intelligence/zone-assessments/{assessment_id}/score",
        json={"dimension_assessments": _dimension_payload()},
    )
    client.post(f"/product-intelligence/zone-assessments/{assessment_id}/submit-review")

    r = client.post(
        f"/product-intelligence/zone-assessments/{assessment_id}/reject",
        json={"review_reason": "insufficient evidence"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "REJECTED"


def test_ai_actor_cannot_approve_via_http(client, context_slot):
    r = client.post(
        "/product-intelligence/product-concepts/concept-1/zone-assessments",
        json={"zone_policy_version_id": "zone-policy-v0"},
    )
    assessment_id = r.json()["id"]
    client.post(
        f"/product-intelligence/zone-assessments/{assessment_id}/score",
        json={"dimension_assessments": _dimension_payload()},
    )
    client.post(f"/product-intelligence/zone-assessments/{assessment_id}/submit-review")

    context_slot[0] = ActorContext(actor_id="ai-bot", actor_type="AI", tenant_scope="tenant-a")
    r = client.post(
        f"/product-intelligence/zone-assessments/{assessment_id}/approve",
        json={"approved_zone": "UNIQUE", "review_reason": "auto-approve"},
    )
    assert r.status_code == 403


def test_human_without_permission_cannot_approve_via_http(client, context_slot):
    r = client.post(
        "/product-intelligence/product-concepts/concept-1/zone-assessments",
        json={"zone_policy_version_id": "zone-policy-v0"},
    )
    assessment_id = r.json()["id"]
    client.post(
        f"/product-intelligence/zone-assessments/{assessment_id}/score",
        json={"dimension_assessments": _dimension_payload()},
    )
    client.post(f"/product-intelligence/zone-assessments/{assessment_id}/submit-review")

    context_slot[0] = ActorContext(actor_id="human-2", actor_type="HUMAN", tenant_scope="tenant-a", permissions=frozenset())
    r = client.post(
        f"/product-intelligence/zone-assessments/{assessment_id}/approve",
        json={"approved_zone": "UNIQUE", "review_reason": "no permission"},
    )
    assert r.status_code == 403


def test_cross_tenant_get_returns_404(client, context_slot):
    r = client.post(
        "/product-intelligence/product-concepts/concept-1/zone-assessments",
        json={"zone_policy_version_id": "zone-policy-v0"},
    )
    assessment_id = r.json()["id"]

    context_slot[0] = ActorContext(actor_id="human-b", actor_type="HUMAN", tenant_scope="tenant-b")
    r = client.get(f"/product-intelligence/zone-assessments/{assessment_id}")
    assert r.status_code == 404


def test_get_nonexistent_assessment_returns_404(client):
    r = client.get("/product-intelligence/zone-assessments/does-not-exist")
    assert r.status_code == 404


def test_approve_override_without_reason_returns_400(client):
    r = client.post(
        "/product-intelligence/product-concepts/concept-1/zone-assessments",
        json={"zone_policy_version_id": "zone-policy-v0"},
    )
    assessment_id = r.json()["id"]
    client.post(
        f"/product-intelligence/zone-assessments/{assessment_id}/score",
        json={"dimension_assessments": _dimension_payload()},
    )
    client.post(f"/product-intelligence/zone-assessments/{assessment_id}/submit-review")

    r = client.post(
        f"/product-intelligence/zone-assessments/{assessment_id}/approve",
        json={"approved_zone": "COMMODITY", "review_reason": "disagree"},
    )
    assert r.status_code == 400
