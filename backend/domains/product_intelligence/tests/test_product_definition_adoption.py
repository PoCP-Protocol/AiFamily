from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.intelligence.human_gate.contracts import (
    ActionProposal,
    ActorType,
    DecisionOutcome,
    GateScope,
    NamedActionRequest,
)
from backend.intelligence.human_gate.gate import InMemoryHumanGate
from backend.intelligence.tool_runtime.accepted_dispatch import (
    AcceptedNamedActionDispatcher,
)
from backend.intelligence.tool_runtime.accepted_worker import PermanentAcceptedActionError
from backend.platform.audit import AuditBase, AuditRecorder, read_all_events

from ..accepted_action import build_product_definition_accepted_action_handlers
from ..application.product_definition_adoption import (
    ADOPT_PRODUCT_DEFINITION_ACTION,
    ADOPT_PRODUCT_DEFINITION_PERMISSION,
    ADOPTION_PURPOSE,
    _definition_id,
    execute_product_definition_named_action,
)
from ..domain.entities import ProductConcept
from ..domain.errors import (
    ProductIntelligenceConflictError,
    ProductIntelligenceForbiddenError,
    ProductIntelligenceNotFoundError,
    ProductIntelligenceValidationError,
)
from ..domain.zone_entities import DimensionAssessment, ProductZoneAssessment
from ..infrastructure.product_definition_adoption_repository import (
    FakeProductDefinitionAdoptionRepository,
    SqlAlchemyProductDefinitionAdoptionRepository,
)
from ..infrastructure.sqlalchemy_models import Base

NOW = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
DIMENSIONS = (
    "customer_scarcity",
    "replaceability",
    "data_advantage",
    "network_effect",
    "learning_effect",
    "switching_cost",
)


class _Authorizer:
    def __init__(self, allowed: bool = True):
        self.allowed = allowed
        self.calls: list[tuple[str, str, str]] = []

    async def is_allowed(self, *, actor_id: str, tenant_scope: str, permission: str) -> bool:
        self.calls.append((actor_id, tenant_scope, permission))
        return self.allowed


class _FailingAuditRepository(FakeProductDefinitionAdoptionRepository):
    def __init__(self) -> None:
        super().__init__()
        self.fail_audit = True

    async def flush_audit(self, recorder: AuditRecorder) -> int:
        count = await super().flush_audit(recorder)
        if self.fail_audit:
            raise RuntimeError("audit_store_unavailable")
        return count


class _FailingSqlAuditRepository(SqlAlchemyProductDefinitionAdoptionRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.fail_audit = True

    async def flush_audit(self, recorder: AuditRecorder) -> int:
        count = await super().flush_audit(recorder)
        if self.fail_audit:
            raise RuntimeError("sql_audit_store_unavailable")
        return count


def _concept(*, tenant: str = "tenant-a") -> ProductConcept:
    return ProductConcept(
        id="concept:one",
        created_at=NOW,
        updated_at=NOW,
        created_by="human:research-owner",
        tenant_scope=tenant,
        strategy_id="strategy:one",
        title="家庭行动支持",
    )


def _assessment(
    *,
    tenant: str = "tenant-a",
    status: str = "APPROVED",
    approved_zone: str | None = "UNIQUE",
    subject_ref: str = "concept:one",
) -> ProductZoneAssessment:
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
        created_at=NOW,
        updated_at=NOW,
        created_by="human:research-owner",
        tenant_scope=tenant,
        status=status,
        subject_ref=subject_ref,
        zone_policy_version_id="zone-policy:v1",
        dimension_assessments=dimensions,
        differentiation_index=76,
        defensibility_index=84,
        commodity_score=12,
        advantage_score=70,
        unique_score=82,
        recommended_zone="UNIQUE",
        approved_zone=approved_zone,
        override_reason=(
            "人工基于组合证据调整三区" if approved_zone not in {None, "UNIQUE"} else None
        ),
        reviewed_by="human:portfolio-owner" if status == "APPROVED" else None,
        reviewed_at=NOW if status == "APPROVED" else None,
        review_reason="证据足以进入产品定义" if status == "APPROVED" else None,
    )


def _arguments(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "concept_id": "concept:one",
        "zone_assessment_id": "assessment:one",
        "source_decision_draft_ref": "decision-draft:one",
        "product_kind": "MICRO_CAMP",
        "duration_days": 21,
        "primary_contradiction": "理解与行动之间存在断点",
        "demand_ref": "demand:one",
        "market_insight_refs": ["insight:one"],
        "component_ids": ["component:understand:v1", "component:action:v1"],
        "skill_ids": ["skill:compose:v1"],
        "success_metric_ids": ["metric:action-adoption"],
        "guardrail_ids": ["guardrail:consent"],
        "stop_conditions": ["stop:safety"],
        "pause_policy": "家长可随时暂停",
        "human_gate_policy": "敏感建议需人工复核",
    }
    values.update(changes)
    return values


def _request(
    *,
    actor_type: ActorType = ActorType.OPERATOR,
    arguments: dict[str, object] | None = None,
    scope: GateScope | None = None,
    idempotency_key: str = "adopt-key-one",
) -> NamedActionRequest:
    return NamedActionRequest(
        request_id="named-action-request:one",
        action_name=ADOPT_PRODUCT_DEFINITION_ACTION,
        action_arguments=arguments or _arguments(),
        task_id="human-task:one",
        proposal_id="proposal:one",
        decision_id="decision:one",
        actor_id="operator:product-owner",
        actor_type=actor_type,
        scope=scope
        or GateScope(
            tenant_id="tenant-a",
            family_id=None,
            subject_ids=("concept:one", "assessment:one"),
            purpose=ADOPTION_PURPOSE,
            consent_version="processing-basis:internal-product-design:v1",
            correlation_id="trace:adopt:one",
        ),
        provenance_ref="model-draft:product-package:one",
        idempotency_key=idempotency_key,
    )


async def _seed(
    repo: FakeProductDefinitionAdoptionRepository, *, approved_zone: str = "UNIQUE"
) -> None:
    await repo.products.save_product_concept(_concept())
    await repo.zones.save_zone_assessment(_assessment(approved_zone=approved_zone))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("approved_zone", "definition_zone"),
    [
        ("COMMODITY", "HOMOGENEOUS"),
        ("ADVANTAGE", "ADVANTAGE"),
        ("UNIQUE", "UNIQUE_CANDIDATE"),
    ],
)
async def test_accepted_named_action_derives_the_approved_zone(
    approved_zone: str, definition_zone: str
) -> None:
    repo = FakeProductDefinitionAdoptionRepository()
    await _seed(repo, approved_zone=approved_zone)
    authorizer = _Authorizer()

    definition, replay = await execute_product_definition_named_action(
        repo,
        _request(),
        human_actor_authorizer=authorizer,
        recorder=AuditRecorder(),
    )

    assert replay is False
    assert definition.status == "DRAFT"
    assert definition.zone == definition_zone
    assert definition.generated_by is None
    assert definition.education_spec is not None
    snapshot = definition.education_spec.adoption
    assert snapshot is not None
    assert snapshot.schema_version == "1.0"
    assert snapshot.approved_zone == approved_zone
    assert snapshot.zone_assessment_version == 1
    assert snapshot.decision_id == "decision:one"
    assert snapshot.processing_basis_ref == "processing-basis:internal-product-design:v1"
    assert snapshot.provenance_ref == "model-draft:product-package:one"
    assert authorizer.calls == [
        (
            "operator:product-owner",
            "tenant-a",
            ADOPT_PRODUCT_DEFINITION_PERMISSION,
        )
    ]
    assert repo.audit_events[0].action == ADOPT_PRODUCT_DEFINITION_ACTION
    assert repo.commits == 1


@pytest.mark.asyncio
async def test_dispatcher_calls_only_the_registered_product_handler() -> None:
    repo = FakeProductDefinitionAdoptionRepository()
    await _seed(repo)
    request = _request()
    dispatcher = AcceptedNamedActionDispatcher(
        build_product_definition_accepted_action_handlers(
            repo,
            authorizer=_Authorizer(),
        )
    )

    receipt = await dispatcher.dispatch(
        request,
        tenant_id="tenant-a",
        family_id=None,
    )

    assert receipt.request_id == request.request_id
    assert receipt.action_name == ADOPT_PRODUCT_DEFINITION_ACTION
    assert receipt.result_ref in repo.products._product_definitions


@pytest.mark.asyncio
async def test_real_human_gate_acceptance_flows_through_dispatcher_to_pdm() -> None:
    repo = FakeProductDefinitionAdoptionRepository()
    await _seed(repo)
    proposal = ActionProposal(
        proposal_id="proposal:real-gate",
        draft_id="decision-draft:real-gate",
        draft_status="DRAFT",
        action_name=ADOPT_PRODUCT_DEFINITION_ACTION,
        action_arguments=_arguments(source_decision_draft_ref="decision-draft:real-gate"),
        scope=_request().scope,
        allowed_actor_types=(ActorType.OPERATOR,),
        risk_level="MEDIUM",
        provenance_ref="model-draft:product-package:real-gate",
        created_at=NOW,
        expires_at=NOW + timedelta(days=1),
    )
    gate = InMemoryHumanGate()
    task = gate.submit(proposal)
    _, request = gate.decide(
        task.task_id,
        actor_id="operator:product-owner",
        actor_type=ActorType.OPERATOR,
        outcome=DecisionOutcome.ACCEPT,
        decision_id="decision:real-gate",
        now=NOW + timedelta(minutes=1),
    )
    assert request is not None
    dispatcher = AcceptedNamedActionDispatcher(
        build_product_definition_accepted_action_handlers(
            repo,
            authorizer=_Authorizer(),
        )
    )

    receipt = await dispatcher.dispatch(
        request,
        tenant_id="tenant-a",
        family_id=None,
    )

    definition = repo.products._product_definitions[receipt.result_ref]
    assert definition.education_spec is not None
    assert definition.education_spec.adoption is not None
    assert definition.education_spec.adoption.decision_id == "decision:real-gate"


@pytest.mark.asyncio
async def test_durable_replay_uses_snapshot_after_assessment_lifecycle_changes() -> None:
    repo = FakeProductDefinitionAdoptionRepository()
    await _seed(repo)
    request = _request()
    first, first_replay = await execute_product_definition_named_action(
        repo, request, human_actor_authorizer=_Authorizer(), recorder=AuditRecorder()
    )
    repo.zones._assessments["assessment:one"] = _assessment(status="RETIRED")
    revoked_authorizer = _Authorizer(allowed=False)
    second, second_replay = await execute_product_definition_named_action(
        repo,
        request,
        human_actor_authorizer=revoked_authorizer,
        recorder=AuditRecorder(),
    )

    assert first_replay is False
    assert second_replay is True
    assert second.id == first.id
    assert len(repo.audit_events) == 1
    assert repo.commits == 1
    assert revoked_authorizer.calls == []


@pytest.mark.asyncio
async def test_handler_marks_domain_rejections_as_permanent() -> None:
    repo = FakeProductDefinitionAdoptionRepository()
    await _seed(repo)
    handler = build_product_definition_accepted_action_handlers(
        repo,
        authorizer=_Authorizer(),
    )[ADOPT_PRODUCT_DEFINITION_ACTION]

    with pytest.raises(PermanentAcceptedActionError, match="arguments_invalid"):
        await handler(_request(arguments=_arguments(product_kind="UNKNOWN")))


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_and_repository_remains_reusable() -> None:
    repo = _FailingAuditRepository()
    await _seed(repo)
    request = _request()

    with pytest.raises(RuntimeError, match="audit_store_unavailable"):
        await execute_product_definition_named_action(
            repo,
            request,
            human_actor_authorizer=_Authorizer(),
            recorder=AuditRecorder(),
        )

    assert repo.products._product_definitions == {}
    assert repo.audit_events == []
    assert repo.commits == 0
    assert repo.rollbacks == 1

    repo.fail_audit = False
    definition, replay = await execute_product_definition_named_action(
        repo,
        request,
        human_actor_authorizer=_Authorizer(),
        recorder=AuditRecorder(),
    )

    assert replay is False
    assert repo.products._product_definitions[definition.id] == definition
    assert len(repo.audit_events) == 1
    assert repo.commits == 1


@pytest.mark.asyncio
async def test_same_key_with_changed_accepted_request_is_rejected() -> None:
    repo = FakeProductDefinitionAdoptionRepository()
    await _seed(repo)
    await execute_product_definition_named_action(
        repo, _request(), human_actor_authorizer=_Authorizer(), recorder=AuditRecorder()
    )
    changed = replace(
        _request(),
        request_id="named-action-request:changed",
        action_arguments=_arguments(primary_contradiction="changed"),
    )
    with pytest.raises(ProductIntelligenceConflictError, match="replay_mismatch"):
        await execute_product_definition_named_action(
            repo, changed, human_actor_authorizer=_Authorizer(), recorder=AuditRecorder()
        )


@pytest.mark.asyncio
async def test_actor_permission_and_exact_scope_fail_closed() -> None:
    repo = FakeProductDefinitionAdoptionRepository()
    await _seed(repo)
    with pytest.raises(ProductIntelligenceForbiddenError, match="requires_operator"):
        await execute_product_definition_named_action(
            repo,
            _request(actor_type=ActorType.GUARDIAN),
            human_actor_authorizer=_Authorizer(),
            recorder=AuditRecorder(),
        )
    with pytest.raises(ProductIntelligenceForbiddenError, match="permission_required"):
        await execute_product_definition_named_action(
            repo,
            _request(),
            human_actor_authorizer=_Authorizer(allowed=False),
            recorder=AuditRecorder(),
        )
    wrong_scope = GateScope(
        tenant_id="tenant-a",
        family_id="family:forged",
        subject_ids=("concept:one", "assessment:one"),
        purpose=ADOPTION_PURPOSE,
        consent_version="processing-basis:internal-product-design:v1",
        correlation_id="trace:forged",
    )
    with pytest.raises(ProductIntelligenceForbiddenError, match="scope_invalid"):
        await execute_product_definition_named_action(
            repo,
            _request(scope=wrong_scope),
            human_actor_authorizer=_Authorizer(),
            recorder=AuditRecorder(),
        )


@pytest.mark.asyncio
async def test_action_purpose_subject_and_tenant_boundaries_fail_closed() -> None:
    repo = FakeProductDefinitionAdoptionRepository()
    await _seed(repo)
    with pytest.raises(ProductIntelligenceValidationError, match="not_supported"):
        await execute_product_definition_named_action(
            repo,
            replace(_request(), action_name="REVIEW_PRODUCT_CONCEPT"),
            human_actor_authorizer=_Authorizer(),
            recorder=AuditRecorder(),
        )

    wrong_purpose = replace(
        _request().scope,
        purpose="service_product_definition_publish",
    )
    with pytest.raises(ProductIntelligenceForbiddenError, match="scope_invalid"):
        await execute_product_definition_named_action(
            repo,
            _request(scope=wrong_purpose),
            human_actor_authorizer=_Authorizer(),
            recorder=AuditRecorder(),
        )

    wrong_subjects = replace(
        _request().scope,
        subject_ids=("concept:one", "assessment:other"),
    )
    with pytest.raises(ProductIntelligenceForbiddenError, match="subject_scope_invalid"):
        await execute_product_definition_named_action(
            repo,
            _request(scope=wrong_subjects),
            human_actor_authorizer=_Authorizer(),
            recorder=AuditRecorder(),
        )

    other_tenant = replace(_request().scope, tenant_id="tenant-b")
    with pytest.raises(ProductIntelligenceNotFoundError, match="product_concept_not_found"):
        await execute_product_definition_named_action(
            repo,
            _request(scope=other_tenant),
            human_actor_authorizer=_Authorizer(),
            recorder=AuditRecorder(),
        )


@pytest.mark.asyncio
async def test_assessment_state_subject_and_extra_arguments_fail_closed() -> None:
    repo = FakeProductDefinitionAdoptionRepository()
    await _seed(repo)
    repo.zones._assessments["assessment:one"] = _assessment(status="SCORED", approved_zone=None)
    with pytest.raises(ProductIntelligenceValidationError, match="approved_zone_assessment"):
        await execute_product_definition_named_action(
            repo, _request(), human_actor_authorizer=_Authorizer(), recorder=AuditRecorder()
        )

    repo.zones._assessments["assessment:one"] = _assessment(subject_ref="concept:other")
    with pytest.raises(ProductIntelligenceValidationError, match="concept_mismatch"):
        await execute_product_definition_named_action(
            repo, _request(), human_actor_authorizer=_Authorizer(), recorder=AuditRecorder()
        )

    with pytest.raises(ProductIntelligenceValidationError, match="arguments_invalid"):
        await execute_product_definition_named_action(
            repo,
            _request(arguments=_arguments(zone="HOMOGENEOUS")),
            human_actor_authorizer=_Authorizer(),
            recorder=AuditRecorder(),
        )


@pytest.mark.asyncio
async def test_sql_handler_persists_definition_and_audit_in_one_commit() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(AuditBase.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        repo = SqlAlchemyProductDefinitionAdoptionRepository(session)
        await repo._products.save_product_concept(_concept())
        await repo._zones.save_zone_assessment(_assessment())
        await session.commit()
        definition, _ = await execute_product_definition_named_action(
            repo,
            _request(idempotency_key="sql-key"),
            human_actor_authorizer=_Authorizer(),
            recorder=AuditRecorder(),
        )

    async with factory() as session:
        reloaded = await SqlAlchemyProductDefinitionAdoptionRepository(
            session
        ).load_product_definition(definition.id, "tenant-a")
        events = await read_all_events(session)
    await engine.dispose()

    assert reloaded.education_spec is not None
    assert reloaded.education_spec.adoption is not None
    assert reloaded.education_spec.adoption.request_id == "named-action-request:one"
    assert events[-1].resource_id == definition.id


@pytest.mark.asyncio
async def test_sql_audit_failure_rolls_back_and_session_remains_reusable() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(AuditBase.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        repo = _FailingSqlAuditRepository(session)
        await repo._products.save_product_concept(_concept())
        await repo._zones.save_zone_assessment(_assessment())
        await session.commit()
        request = _request(idempotency_key="sql-rollback-key")

        with pytest.raises(RuntimeError, match="sql_audit_store_unavailable"):
            await execute_product_definition_named_action(
                repo,
                request,
                human_actor_authorizer=_Authorizer(),
                recorder=AuditRecorder(),
            )

        with pytest.raises(ProductIntelligenceNotFoundError):
            await repo.load_product_definition(
                _definition_id("tenant-a", "sql-rollback-key"),
                "tenant-a",
            )

        repo.fail_audit = False
        definition, replay = await execute_product_definition_named_action(
            repo,
            request,
            human_actor_authorizer=_Authorizer(),
            recorder=AuditRecorder(),
        )
        assert replay is False

    async with factory() as session:
        persisted = await SqlAlchemyProductDefinitionAdoptionRepository(
            session
        ).load_product_definition(definition.id, "tenant-a")
        events = await read_all_events(session)
    await engine.dispose()

    assert persisted.id == definition.id
    assert len(events) == 1
