from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.apps.family_api.product_factory_identity import ProductFactoryIdentityError
from backend.intelligence.human_gate.persistence import HumanGateBase, HumanTaskRow
from backend.platform.audit import AuditBase, AuditEventRow

from ..api.dependencies import clear_actor_resolver, configure_actor_resolver
from ..api.product_package_submission_dependencies import (
    clear_product_package_submission_services,
    configure_product_package_submission_services,
    get_product_package_actor_context,
    get_product_package_submission_clock,
)
from ..api.product_package_submission_routes import router
from ..application.context import ActorContext
from ..application.product_package_source_resolution import (
    ProductPackageDesignIntent,
    ResolvedProductPackageSource,
)
from ..application.product_package_submission import (
    PRODUCT_PACKAGE_READ_PERMISSION,
    PRODUCT_PACKAGE_SUBMIT_PERMISSION,
    ProductPackageSubmissionInput,
)
from ..domain.entities import ProductConcept
from ..domain.zone_entities import DimensionAssessment, ProductZoneAssessment
from ..infrastructure.product_package_submission_repository import ProductPackageDraftRow
from ..infrastructure.sqlalchemy_models import Base as ProductBase
from ..infrastructure.sqlalchemy_repository import SqlAlchemyProductIntelligenceRepository
from ..infrastructure.zone_sqlalchemy_models import Base as ZoneBase
from ..infrastructure.zone_sqlalchemy_repository import SqlAlchemyZoneAssessmentRepository

NOW = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
DIMENSIONS = (
    "customer_scarcity",
    "replaceability",
    "data_advantage",
    "network_effect",
    "learning_effect",
    "switching_cost",
)


def _actor(*, tenant: str = "tenant-a", allowed: bool = True) -> ActorContext:
    permissions = (
        frozenset({PRODUCT_PACKAGE_SUBMIT_PERMISSION, PRODUCT_PACKAGE_READ_PERMISSION})
        if allowed
        else frozenset()
    )
    return ActorContext(
        actor_id="human:product-owner",
        actor_type="HUMAN",
        tenant_scope=tenant,
        permissions=permissions,
        trace_id="trace:http:package",
    )


def _ai_actor() -> ActorContext:
    return ActorContext(
        actor_id="ai:product-composer",
        actor_type="AI",
        tenant_scope="tenant-a",
        permissions=frozenset({PRODUCT_PACKAGE_SUBMIT_PERMISSION, PRODUCT_PACKAGE_READ_PERMISSION}),
        trace_id="trace:http:ai-package",
    )


def _concept() -> ProductConcept:
    return ProductConcept(
        id="concept:one",
        created_at=NOW,
        updated_at=NOW,
        created_by="human:research-owner",
        tenant_scope="tenant-a",
        strategy_id="strategy:one",
        title="家庭行动支持",
    )


def _assessment() -> ProductZoneAssessment:
    dimensions = [
        DimensionAssessment(
            dimension=dimension,
            score=82,
            rationale="evidence-backed",
            evidence_refs=[f"evidence:{dimension}"],
            evidence_strength=0.8,
            assessed_by="human:research-owner",
            assessed_at=NOW,
        )
        for dimension in DIMENSIONS
    ]
    return ProductZoneAssessment(
        id="assessment:one",
        version=3,
        created_at=NOW,
        updated_at=NOW,
        created_by="human:research-owner",
        tenant_scope="tenant-a",
        status="APPROVED",
        subject_ref="concept:one",
        zone_policy_version_id="zone-policy:v2",
        dimension_assessments=dimensions,
        differentiation_index=76,
        defensibility_index=84,
        commodity_score=12,
        advantage_score=70,
        unique_score=82,
        recommended_zone="UNIQUE",
        approved_zone="UNIQUE",
        reviewed_by="human:portfolio-owner",
        reviewed_at=NOW,
        review_reason="证据足以进入产品设计",
    )


def _payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_draft_locator": "model-draft-locator:one",
        "concept_id": "concept:one",
        "zone_assessment_id": "assessment:one",
        "product_kind": "MICRO_CAMP",
        "duration_days": 21,
        "primary_contradiction": "理解与行动之间存在断点",
        "demand_ref": "demand:one",
        "market_insight_refs": ["insight:one"],
        "competitor_evidence_refs": ["competitor-evidence:one"],
        "component_ids": ["component:understand:v1", "component:action:v1"],
        "skill_ids": ["skill:compose:v1"],
        "success_metric_ids": ["metric:action-adoption"],
        "guardrail_ids": ["guardrail:consent"],
        "stop_conditions": ["stop:safety"],
        "pause_policy": "家长可随时暂停",
        "human_gate_policy": "敏感建议需人工复核",
        "evidence_locators": ["verification-receipt:market", "verification-receipt:pilot"],
        "assumptions": ["需要小批家庭验证"],
        "unknowns": ["不同年龄段的节奏差异"],
        "next_validation": "完成五个家庭的匿名试点",
        "requested_ttl_hours": 24,
    }
    payload.update(changes)
    return payload


class _TrustedResolver:
    def __init__(self, *, mismatch: bool = False, exceed_ttl: bool = False):
        self.calls = 0
        self.mismatch = mismatch
        self.exceed_ttl = exceed_ttl

    async def resolve(
        self,
        *,
        context: ActorContext,
        intent: ProductPackageDesignIntent,
        now: datetime,
    ) -> ResolvedProductPackageSource:
        self.calls += 1
        expiry_hours = intent.requested_ttl_hours + (1 if self.exceed_ttl else 0)
        source = ProductPackageSubmissionInput(
            concept_id=intent.concept_id,
            zone_assessment_id=intent.zone_assessment_id,
            upstream_decision_draft_ref="model-draft:canonical:one",
            product_kind=intent.product_kind,
            duration_days=intent.duration_days + (1 if self.mismatch else 0),
            primary_contradiction=intent.primary_contradiction,
            demand_ref=intent.demand_ref,
            market_insight_refs=intent.market_insight_refs,
            competitor_evidence_refs=intent.competitor_evidence_refs,
            component_ids=intent.component_ids,
            skill_ids=intent.skill_ids,
            success_metric_ids=intent.success_metric_ids,
            guardrail_ids=intent.guardrail_ids,
            stop_conditions=intent.stop_conditions,
            pause_policy=intent.pause_policy,
            human_gate_policy=intent.human_gate_policy,
            evidence_refs=intent.evidence_locators,
            evidence_statuses={ref: "VERIFIED" for ref in intent.evidence_locators},
            assumptions=intent.assumptions,
            unknowns=intent.unknowns,
            next_validation=intent.next_validation,
            expires_at=now + timedelta(hours=expiry_hours),
            source_provenance_ref="model-draft:canonical:one",
            model_ref="model:test@1",
            prompt_use_case_version="service-product-composition@1",
            confidence=0.82,
        )
        return ResolvedProductPackageSource(
            source_draft_locator=intent.source_draft_locator,
            submission=source,
        )


async def _harness(
    resolver: _TrustedResolver | None = None,
) -> tuple[object, async_sessionmaker[AsyncSession], FastAPI, _TrustedResolver]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(ProductBase.metadata.create_all)
        await connection.run_sync(ZoneBase.metadata.create_all)
        await connection.run_sync(HumanGateBase.metadata.create_all)
        await connection.run_sync(AuditBase.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        await SqlAlchemyProductIntelligenceRepository(session).save_product_concept(_concept())
        await SqlAlchemyZoneAssessmentRepository(session).save_zone_assessment(_assessment())
        await session.commit()

    trusted_resolver = resolver or _TrustedResolver()
    configure_product_package_submission_services(
        factory,
        lambda _session: trusted_resolver,
    )
    app = FastAPI()
    app.include_router(router)

    async def actor_context() -> ActorContext:
        return _actor()

    app.dependency_overrides[get_product_package_actor_context] = actor_context
    app.dependency_overrides[get_product_package_submission_clock] = lambda: NOW
    return engine, factory, app, trusted_resolver


@pytest.mark.asyncio
async def test_create_readback_and_idempotent_replay_use_server_canonical_state() -> None:
    engine, factory, app, resolver = await _harness()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            created = await client.post(
                "/product-intelligence/product-package-review-submissions",
                headers={"Idempotency-Key": "http-package-one"},
                json=_payload(),
            )
            assert created.status_code == 201
            body = created.json()
            assert body["lifecycle_state"] == "SUBMITTED_FOR_REVIEW"
            assert body["draft"]["approved_zone"] == "UNIQUE"
            assert body["draft"]["source_draft_locator"] == "model-draft-locator:one"
            assert len(body["draft"]["intent_hash"]) == 64
            assert body["draft"]["source_provenance_ref"] == "model-draft:canonical:one"
            assert body["review_task"]["status"] == "OPEN"
            assert created.headers["etag"] == body["etag"]

            readback = await client.get(created.headers["location"])
            assert readback.status_code == 200
            assert readback.json()["draft"] == body["draft"]
            assert readback.json()["review_task"] == body["review_task"]

            replay = await client.post(
                "/product-intelligence/product-package-review-submissions",
                headers={"Idempotency-Key": "http-package-one"},
                json=_payload(),
            )
            assert replay.status_code == 200
            assert replay.json()["replayed"] is True
            assert replay.json()["draft"]["draft_id"] == body["draft"]["draft_id"]

            conflict = await client.post(
                "/product-intelligence/product-package-review-submissions",
                headers={"Idempotency-Key": "http-package-one"},
                json=_payload(duration_days=90, product_kind="SCALE_PLAN"),
            )
            assert conflict.status_code == 409

        async with factory() as session:
            draft_count = await session.scalar(
                select(func.count()).select_from(ProductPackageDraftRow)
            )
            assert draft_count == 1
            assert await session.scalar(select(func.count()).select_from(HumanTaskRow)) == 1
            assert await session.scalar(select(func.count()).select_from(AuditEventRow)) == 2
        assert resolver.calls == 1
    finally:
        clear_product_package_submission_services()
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tenant_scope", "tenant-forged"),
        ("actor_id", "human:forged"),
        ("zone", "UNIQUE"),
        ("evidence_statuses", {"verification-receipt:market": "VERIFIED"}),
        ("source_provenance_ref", "model-draft:forged"),
        ("model_ref", "model:forged"),
        ("confidence", 1.0),
        ("task_id", "human-task:forged"),
    ],
)
async def test_browser_cannot_submit_governance_fields(field: str, value: object) -> None:
    engine, _factory, app, resolver = await _harness()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/product-intelligence/product-package-review-submissions",
                headers={"Idempotency-Key": "forged-governance"},
                json=_payload(**{field: value}),
            )
        assert response.status_code == 422
        assert resolver.calls == 0
    finally:
        clear_product_package_submission_services()
        await engine.dispose()


@pytest.mark.asyncio
async def test_unauthorized_context_is_rejected_before_source_resolution() -> None:
    engine, _factory, app, resolver = await _harness()

    async def forbidden_actor() -> ActorContext:
        return _actor(allowed=False)

    app.dependency_overrides[get_product_package_actor_context] = forbidden_actor
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/product-intelligence/product-package-review-submissions",
                headers={"Idempotency-Key": "forbidden"},
                json=_payload(),
            )
        assert response.status_code == 403
        assert resolver.calls == 0
    finally:
        clear_product_package_submission_services()
        await engine.dispose()


@pytest.mark.asyncio
async def test_ai_actor_cannot_submit_review_even_with_permission() -> None:
    engine, _factory, app, resolver = await _harness()

    async def ai_actor() -> ActorContext:
        return _ai_actor()

    app.dependency_overrides[get_product_package_actor_context] = ai_actor
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/product-intelligence/product-package-review-submissions",
                headers={"Idempotency-Key": "ai-forbidden"},
                json=_payload(),
            )
        assert response.status_code == 403
        assert resolver.calls == 0
    finally:
        clear_product_package_submission_services()
        await engine.dispose()


@pytest.mark.asyncio
async def test_cross_tenant_read_is_indistinguishable_from_missing() -> None:
    engine, _factory, app, _resolver = await _harness()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            created = await client.post(
                "/product-intelligence/product-package-review-submissions",
                headers={"Idempotency-Key": "tenant-read"},
                json=_payload(),
            )

            async def other_tenant() -> ActorContext:
                return _actor(tenant="tenant-b")

            app.dependency_overrides[get_product_package_actor_context] = other_tenant
            response = await client.get(created.headers["location"])
        assert response.status_code == 404
    finally:
        clear_product_package_submission_services()
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "resolver",
    [_TrustedResolver(mismatch=True), _TrustedResolver(exceed_ttl=True)],
)
async def test_mismatched_or_overlong_resolution_writes_nothing(
    resolver: _TrustedResolver,
) -> None:
    engine, factory, app, _resolver = await _harness(resolver)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/product-intelligence/product-package-review-submissions",
                headers={"Idempotency-Key": "invalid-resolution"},
                json=_payload(),
            )
        assert response.status_code == 422
        async with factory() as session:
            draft_count = await session.scalar(
                select(func.count()).select_from(ProductPackageDraftRow)
            )
            assert draft_count == 0
            assert await session.scalar(select(func.count()).select_from(HumanTaskRow)) == 0
    finally:
        clear_product_package_submission_services()
        await engine.dispose()


@pytest.mark.asyncio
async def test_unconfigured_trusted_resolver_fails_closed() -> None:
    clear_product_package_submission_services()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_product_package_actor_context] = lambda: _actor()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/product-intelligence/product-package-review-submissions",
            headers={"Idempotency-Key": "not-configured"},
            json=_payload(),
        )
    assert response.status_code == 503
    assert response.json()["detail"] == "PRODUCT_PACKAGE_TRUSTED_SOURCE_RESOLVER_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_authorization_runs_before_unconfigured_services() -> None:
    clear_product_package_submission_services()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_product_package_actor_context] = lambda: _actor(allowed=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/product-intelligence/product-package-review-submissions",
            headers={"Idempotency-Key": "auth-first"},
            json=_payload(),
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_readback_does_not_depend_on_source_resolver_availability() -> None:
    engine, factory, app, _resolver = await _harness()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            created = await client.post(
                "/product-intelligence/product-package-review-submissions",
                headers={"Idempotency-Key": "read-without-resolver"},
                json=_payload(),
            )
            configure_product_package_submission_services(factory, None)
            readback = await client.get(created.headers["location"])
        assert readback.status_code == 200
        assert readback.json()["draft"]["draft_id"] == created.json()["draft"]["draft_id"]
    finally:
        clear_product_package_submission_services()
        await engine.dispose()


@pytest.mark.asyncio
async def test_exact_post_replay_precedes_unavailable_or_changed_trusted_source() -> None:
    engine, factory, app, resolver = await _harness()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            created = await client.post(
                "/product-intelligence/product-package-review-submissions",
                headers={"Idempotency-Key": "replay-without-resolver"},
                json=_payload(),
            )
            assert created.status_code == 201
            configure_product_package_submission_services(factory, None)

            replay = await client.post(
                "/product-intelligence/product-package-review-submissions",
                headers={"Idempotency-Key": "replay-without-resolver"},
                json=_payload(),
            )
            assert replay.status_code == 200
            assert replay.json()["replayed"] is True
            assert replay.json()["draft"] == created.json()["draft"]

            mismatch = await client.post(
                "/product-intelligence/product-package-review-submissions",
                headers={"Idempotency-Key": "replay-without-resolver"},
                json=_payload(duration_days=90),
            )
            assert mismatch.status_code == 409
            assert mismatch.json()["detail"] == "PRODUCT_PACKAGE_INTENT_REPLAY_MISMATCH"

            fresh = await client.post(
                "/product-intelligence/product-package-review-submissions",
                headers={"Idempotency-Key": "fresh-without-resolver"},
                json=_payload(),
            )
            assert fresh.status_code == 503
            assert fresh.json()["detail"] == (
                "PRODUCT_PACKAGE_TRUSTED_SOURCE_RESOLVER_NOT_CONFIGURED"
            )
        assert resolver.calls == 1
    finally:
        clear_product_package_submission_services()
        await engine.dispose()


@pytest.mark.asyncio
async def test_identity_errors_map_before_service_configuration() -> None:
    clear_product_package_submission_services()

    async def missing_bearer(_request) -> ActorContext:
        raise ProductFactoryIdentityError("BEARER_REQUIRED")

    configure_actor_resolver(missing_bearer)
    app = FastAPI()
    app.include_router(router)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/product-intelligence/product-package-review-submissions",
                headers={"Idempotency-Key": "identity-first"},
                json=_payload(),
            )
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.json()["detail"] == "BEARER_REQUIRED"
    finally:
        clear_actor_resolver()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("component_ids", ["c" * 513]),
        ("evidence_locators", ["e" * 513]),
        ("assumptions", ["a" * 2001]),
        ("unknowns", ["u" * 2001]),
        ("stop_conditions", ["s" * 2001]),
    ],
)
async def test_oversized_array_items_are_rejected_before_resolution(
    field: str, value: object
) -> None:
    engine, _factory, app, resolver = await _harness()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/product-intelligence/product-package-review-submissions",
                headers={"Idempotency-Key": "oversized-item"},
                json=_payload(**{field: value}),
            )
        assert response.status_code == 422
        assert resolver.calls == 0
    finally:
        clear_product_package_submission_services()
        await engine.dispose()
