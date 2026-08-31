from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ..api.dependencies import get_actor_context, get_repository
from ..api.product_factory_routes import router
from ..application.context import ActorContext
from ..domain.entities import ProductConcept
from ..domain.errors import ProductIntelligenceValidationError
from ..infrastructure.fake_repository import FakeProductIntelligenceRepository


def _payload(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "evidence_refs": ["evidence:one"],
        "assumptions": ["需要通过访谈验证"],
        "unknowns": ["区域差异尚未确认"],
        "next_validation": "访谈五个目标家庭",
        "expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
    }
    value.update(overrides)
    return value


def _client(repo: FakeProductIntelligenceRepository, context: ActorContext) -> TestClient:
    app = FastAPI()
    app.include_router(router)

    async def override_repo():
        yield repo

    async def override_context():
        return context

    app.dependency_overrides[get_repository] = override_repo
    app.dependency_overrides[get_actor_context] = override_context
    return TestClient(app)


@pytest.fixture
def repo() -> FakeProductIntelligenceRepository:
    return FakeProductIntelligenceRepository()


@pytest.fixture
def human_context() -> ActorContext:
    return ActorContext(actor_id="human:pm", actor_type="HUMAN", tenant_scope="tenant-a")


def test_demand_frame_route_reuses_market_signal_and_returns_draft(repo, human_context) -> None:
    client = _client(repo, human_context)
    response = client.post(
        "/product-intelligence/product-factory/demand-frames",
        json=_payload(
            statement="家长需要更可执行的家庭沟通支持",
            scenario="家庭沟通",
            source_refs=["source:interview:one"],
            target_segment="小学阶段家长",
        ),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["requires_human_confirmation"] is True
    assert body["may_mutate_business_state"] is False
    assert body["source_refs"] == ["source:interview:one"]


def test_ai_demand_draft_returns_complete_provenance(repo) -> None:
    context = ActorContext(
        actor_id="ai:discovery",
        actor_type="AI",
        tenant_scope="tenant-a",
    )
    response = _client(repo, context).post(
        "/product-intelligence/product-factory/demand-frames",
        json=_payload(
            statement="AI 生成的需求草案",
            scenario="家庭沟通",
            source_refs=["source:one"],
            target_segment="家长",
            provenance_ref="model-draft:one",
            model_ref="model:gateway:test",
            prompt_use_case_version="demand.frame.generate@1",
            confidence=0.82,
        ),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["provenance_ref"] == "model-draft:one"
    assert body["model_ref"] == "model:gateway:test"
    assert body["prompt_use_case_version"] == "demand.frame.generate@1"
    assert body["confidence"] == 0.82


def test_market_insight_route_reuses_customer_insight_and_is_tenant_scoped(
    repo, human_context
) -> None:
    client = _client(repo, human_context)
    demand = client.post(
        "/product-intelligence/product-factory/demand-frames",
        json=_payload(
            statement="家长反馈",
            scenario="家庭沟通",
            source_refs=["source:one"],
            target_segment="家长",
        ),
    ).json()
    response = client.post(
        "/product-intelligence/product-factory/market-insights",
        json=_payload(
            demand_ref=demand["demand_id"],
            statement="可暂停行动值得验证",
            source_refs=["source:research:one"],
        ),
    )
    assert response.status_code == 201
    assert response.json()["demand_ref"] == demand["demand_id"]
    assert response.json()["status"] == "DRAFT"


def test_ai_draft_requires_provenance_before_command(repo) -> None:
    context = ActorContext(actor_id="ai:discovery", actor_type="AI", tenant_scope="tenant-a")
    response = _client(repo, context).post(
        "/product-intelligence/product-factory/demand-frames",
        json=_payload(
            statement="需求草案",
            scenario="家庭沟通",
            source_refs=["source:one"],
            target_segment="家长",
        ),
    )
    assert response.status_code == 422
    assert "ai_actor_requires_full_provenance" in response.json()["detail"]
    assert repo._market_signals == {}


def test_request_rejects_client_identity_and_missing_evidence(repo, human_context) -> None:
    client = _client(repo, human_context)
    response = client.post(
        "/product-intelligence/product-factory/demand-frames",
        json=_payload(
            statement="需求草案",
            scenario="家庭沟通",
            source_refs=["source:one"],
            target_segment="家长",
            tenant_scope="tenant-attacker",
        ),
    )
    assert response.status_code == 422
    response = client.post(
        "/product-intelligence/product-factory/demand-frames",
        json=_payload(
            statement="需求草案",
            scenario="家庭沟通",
            source_refs=[],
            target_segment="家长",
        ),
    )
    assert response.status_code == 422


def test_expired_draft_is_rejected_before_parent_is_persisted(repo, human_context) -> None:
    client = _client(repo, human_context)
    response = client.post(
        "/product-intelligence/product-factory/demand-frames",
        json=_payload(
            statement="过期需求草案",
            scenario="家庭沟通",
            source_refs=["source:one"],
            target_segment="家长",
            expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        ),
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "Value error, expires_at_must_be_in_the_future"
    assert repo._market_signals == {}


def test_naive_draft_expiry_is_rejected_at_http_boundary(repo, human_context) -> None:
    client = _client(repo, human_context)
    response = client.post(
        "/product-intelligence/product-factory/demand-frames",
        json=_payload(
            statement="无时区需求草案",
            scenario="家庭沟通",
            source_refs=["source:one"],
            target_segment="家长",
            expires_at="2099-01-01T00:00:00",
        ),
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "Value error, expires_at_must_be_timezone_aware"
    assert repo._market_signals == {}


def test_competitor_route_persists_draft_with_tenant_scope(repo, human_context) -> None:
    response = _client(repo, human_context).post(
        "/product-intelligence/product-factory/competitor-evidence",
        json=_payload(
            competitor_ref="competitor:example",
            claim="公开资料显示其提供提醒功能",
            source_refs=["source:public:one"],
            demand_ref="demand:one",
            evidence_status="UNKNOWN",
        ),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["evidence_id"].startswith("competitor-evidence:")
    stored, tenant_scope, created_by = repo._competitor_evidence[body["evidence_id"]]
    assert stored.claim == "公开资料显示其提供提醒功能"
    assert tenant_scope == "tenant-a"
    assert created_by == "human:pm"

    read = _client(repo, human_context).get(
        f"/product-intelligence/product-factory/competitor-evidence/{body['evidence_id']}"
    )
    assert read.status_code == 200
    assert read.json()["claim"] == "公开资料显示其提供提醒功能"


def test_competitor_source_card_cannot_self_declare_verified(repo, human_context) -> None:
    response = _client(repo, human_context).post(
        "/product-intelligence/product-factory/competitor-evidence",
        json=_payload(
            competitor_ref="competitor:example",
            claim="客户端不能自行核验证据",
            source_refs=["source:public:one"],
            demand_ref="demand:one",
            evidence_status="VERIFIED",
        ),
    )
    assert response.status_code == 422
    assert repo._competitor_evidence == {}


@pytest.mark.asyncio
async def test_competitor_repository_rejects_internal_self_verification(repo) -> None:
    class InternalCard:
        evidence_id = "evidence:forged"
        evidence_status = "VERIFIED"

    with pytest.raises(
        ProductIntelligenceValidationError,
        match="competitor_evidence_cannot_self_verify",
    ):
        await repo.save_competitor_evidence(
            InternalCard(),
            tenant_scope="tenant-a",
            created_by="import:job",
        )
    assert repo._competitor_evidence == {}


def test_competitor_read_is_tenant_scoped(repo, human_context) -> None:
    create = _client(repo, human_context).post(
        "/product-intelligence/product-factory/competitor-evidence",
        json=_payload(
            competitor_ref="competitor:example",
            claim="租户隔离证据",
            source_refs=["source:public:one"],
            demand_ref="demand:one",
        ),
    )
    evidence_id = create.json()["evidence_id"]
    other_context = ActorContext(
        actor_id="human:other", actor_type="HUMAN", tenant_scope="tenant-b"
    )
    read = _client(repo, other_context).get(
        f"/product-intelligence/product-factory/competitor-evidence/{evidence_id}"
    )
    assert read.status_code == 404


def test_competitor_route_fails_closed_without_repository_saver(human_context) -> None:
    class RepositoryWithoutCompetitorSaver:
        pass

    app = FastAPI()
    app.include_router(router)

    async def override_repo():
        yield RepositoryWithoutCompetitorSaver()

    async def override_context():
        return human_context

    app.dependency_overrides[get_repository] = override_repo
    app.dependency_overrides[get_actor_context] = override_context
    response = TestClient(app).post(
        "/product-intelligence/product-factory/competitor-evidence",
        json=_payload(
            competitor_ref="competitor:example",
            claim="公开资料显示其提供提醒功能",
            source_refs=["source:public:one"],
            demand_ref="demand:one",
            evidence_status="UNKNOWN",
        ),
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "competitor_evidence_persistence_not_configured"


def test_product_package_route_returns_draft_without_persisting_definition(
    repo, human_context
) -> None:
    now = datetime.now(UTC)
    import asyncio

    asyncio.run(
        repo.save_product_concept(
            ProductConcept(
                id="concept:one",
                created_at=now,
                updated_at=now,
                created_by="human:pm",
                tenant_scope="tenant-a",
                strategy_id="strategy:one",
                title="家庭行动支持",
            )
        )
    )
    response = _client(repo, human_context).post(
        "/product-intelligence/product-factory/product-packages",
        json=_payload(
            concept_id="concept:one",
            product_kind="MICRO_CAMP",
            duration_days=21,
            zone="ADVANTAGE",
            primary_contradiction="理解与行动之间存在断点",
            demand_ref="demand:one",
            market_insight_refs=["insight:one"],
            competitor_evidence_refs=["competitor-evidence:one"],
            component_ids=["component:understand:v1", "component:action:v1"],
            skill_ids=["skill:compose:v1"],
            success_metric_ids=["metric:adoption"],
            guardrail_ids=["guardrail:consent"],
            stop_conditions=["stop:safety"],
            pause_policy="家长可随时暂停",
            human_gate_policy="敏感建议需人工复核",
        ),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["draft_id"].startswith("draft:product-package:")
    assert body["product_definition_id"] is None
    assert body["duration_days"] == 21
    assert body["may_mutate_business_state"] is False
    assert repo._product_definitions == {}


def test_product_package_parent_scope_failure_returns_not_found(repo, human_context) -> None:
    response = _client(repo, human_context).post(
        "/product-intelligence/product-factory/product-packages",
        json=_payload(
            concept_id="concept:missing",
            product_kind="MICRO_CAMP",
            duration_days=21,
            zone="ADVANTAGE",
            primary_contradiction="理解与行动之间存在断点",
            demand_ref="demand:one",
            market_insight_refs=["insight:one"],
            competitor_evidence_refs=["competitor-evidence:one"],
            component_ids=["component:action:v1"],
            skill_ids=["skill:compose:v1"],
            success_metric_ids=["metric:adoption"],
            guardrail_ids=["guardrail:consent"],
            stop_conditions=["stop:safety"],
            pause_policy="家长可随时暂停",
            human_gate_policy="敏感建议需人工复核",
        ),
    )
    assert response.status_code == 404
