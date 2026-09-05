from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.context_engine.contracts import (
    ContextContractError,
    ContextScope,
    ContextScopeError,
    DataClass,
    StateObservation,
)
from backend.intelligence.context_engine.store import ContextBroker
from backend.intelligence.knowledge.registry import KnowledgeRegistry
from backend.intelligence.model_gateway import FakeProvider, ModelGateway
from backend.intelligence.principal.contracts import (
    PrincipalCapability,
    PrincipalEntryPoint,
    PrincipalRouteRequest,
)
from backend.intelligence.principal.runtime import (
    PrincipalRuntime,
    PrincipalRuntimeRequest,
)


def route(
    *,
    snapshot_ref: str,
    tenant_id: str = "tenant-1",
    family_id: str | None = "family-1",
    subject_id: str | None = "person-1",
    purpose: str = "family_growth_support",
    consent_granted: bool = True,
    data_class: str = "OPERATIONAL_TEXT",
) -> PrincipalRouteRequest:
    return PrincipalRouteRequest(
        request_id="request-context-1",
        tenant_id=tenant_id,
        actor_type="guardian",
        entry_point=PrincipalEntryPoint.ASK_PRINCIPAL,
        capability=PrincipalCapability.EXPERIENCE_CURATION,
        purpose=purpose,
        data_class=data_class,  # type: ignore[arg-type]
        context_snapshot_ref=snapshot_ref,
        consent_granted=consent_granted,
        global_id="global-context-1",
        consent_version="consent.v1",
        correlation_id="correlation-context-1",
        causation_id="causation-context-1",
        family_id=family_id,
        subject_id=subject_id,
        locale="zh-CN",
        content_locale="zh-CN",
        model_locale="zh-CN",
        policy_locale="zh-CN",
        region="CN",
    )


def context_scope(
    *,
    tenant_id: str = "tenant-1",
    family_id: str = "family-1",
    subject_ids: tuple[str, ...] = ("person-1",),
    purpose: str = "family_growth_support",
    data_class: DataClass = DataClass.OPERATIONAL_TEXT,
) -> ContextScope:
    return ContextScope(
        tenant_id=tenant_id,
        region_id="CN",
        family_id=family_id,
        subject_ids=subject_ids,
        purpose=purpose,
        consent_version="consent.v1",
        consent_granted=True,
        data_class=data_class,
        locale="zh-CN",
        deletion_ref="delete:context-family-1",
        correlation_id="correlation-context-1",
        causation_id="causation-context-1",
    )


def append_observation(broker: ContextBroker, *, scope: ContextScope) -> None:
    now = datetime.now(UTC)
    broker.append(
        StateObservation(
            observation_id=f"observation:{scope.tenant_id}:{scope.family_id}",
            tenant_id=scope.tenant_id,
            family_id=scope.family_id,
            subject_id=scope.subject_ids[0],
            dimension="rhythm",
            observed_value="family has a ten-minute evening window",
            evidence_refs=("check-in:1",),
            provenance="family:guardian-note",
            observed_at=now - timedelta(minutes=1),
            data_class=scope.data_class,
            purpose=scope.purpose,
            consent_version=scope.consent_version,
            consent_granted=True,
            region_id=scope.region_id,
            locale=scope.locale,
            deletion_ref="delete:context-family-1",
            correlation_id=scope.correlation_id,
            causation_id=scope.causation_id,
            expires_at=now + timedelta(hours=1),
            retention_policy="context.v1",
        )
    )


def principal_request(
    route_request: PrincipalRouteRequest,
    *,
    require_knowledge: bool = False,
) -> PrincipalRuntimeRequest:
    return PrincipalRuntimeRequest(
        route_request=route_request,
        prompt="Offer one kind next step.",
        knowledge_scope="family_growth_reviewed",
        knowledge_purpose="family_growth_support",
        require_knowledge=require_knowledge,
        output_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "candidate_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["message", "candidate_ids"],
        },
    )


def runtime(*, broker: ContextBroker | None) -> tuple[PrincipalRuntime, FakeProvider]:
    provider = FakeProvider(
        {
            PrincipalCapability.EXPERIENCE_CURATION.value: {
                "message": "Try a ten-minute check-in.",
                "candidate_ids": ["action:check-in"],
            }
        }
    )
    return (
        PrincipalRuntime(
            gateway=ModelGateway({"fake-deterministic": provider}, environment="test"),
            knowledge_registry=KnowledgeRegistry(),
            context_broker=broker,
            provider_id="fake-deterministic",
        ),
        provider,
    )


def snapshot_for(broker: ContextBroker, *, scope: ContextScope) -> str:
    append_observation(broker, scope=scope)
    return broker.snapshot(scope=scope).snapshot_ref


@pytest.mark.asyncio
async def test_principal_reads_context_snapshot_projection_before_gateway() -> None:
    broker = ContextBroker()
    snapshot_ref = snapshot_for(broker, scope=context_scope())
    principal, provider = runtime(broker=broker)

    draft = await principal.draft(principal_request(route(snapshot_ref=snapshot_ref)))

    projection = provider.invocations[0].payload["context_projection"]
    assert draft.output["candidate_ids"] == ["action:check-in"]
    assert projection["snapshot_ref"] == snapshot_ref
    assert projection["tenant_id"] == "tenant-1"
    assert projection["family_id"] == "family-1"
    assert projection["subject_ids"] == ["person-1"]
    assert projection["purpose"] == "family_growth_support"
    assert projection["observations"][0]["observation_id"] == "observation:tenant-1:family-1"
    assert provider.invocations[0].context_snapshot_ref == snapshot_ref


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("route_overrides", "error", "message"),
    [
        ({"tenant_id": "tenant-foreign"}, ContextScopeError, "CROSS_TENANT_CONTEXT_SNAPSHOT"),
        ({"family_id": "family-foreign"}, ContextScopeError, "CROSS_FAMILY_CONTEXT_SNAPSHOT"),
        ({"subject_id": "person-foreign"}, ContextScopeError, "CROSS_SUBJECT_CONTEXT_SNAPSHOT"),
        ({"purpose": "other-purpose"}, ContextContractError, "CONTEXT_PURPOSE_MISMATCH"),
        ({"consent_granted": False}, ContextContractError, "CONSENT_REVOKED"),
    ],
)
async def test_principal_context_rejects_scope_mismatch_before_model(
    route_overrides: dict[str, object],
    error: type[ValueError],
    message: str,
) -> None:
    broker = ContextBroker()
    snapshot_ref = snapshot_for(broker, scope=context_scope())
    principal, provider = runtime(broker=broker)

    with pytest.raises(error, match=message):
        await principal.draft(
            principal_request(route(snapshot_ref=snapshot_ref, **route_overrides))
        )

    assert provider.invocations == []


@pytest.mark.asyncio
async def test_principal_context_rejects_expired_snapshot_before_model() -> None:
    broker = ContextBroker()
    scope = context_scope()
    append_observation(broker, scope=scope)
    now = datetime.now(UTC)
    snapshot_ref = broker.snapshot(
        scope=scope,
        now=now - timedelta(seconds=2),
        snapshot_ttl=timedelta(seconds=1),
    ).snapshot_ref
    principal, provider = runtime(broker=broker)

    with pytest.raises(ContextContractError, match="CONTEXT_SNAPSHOT_EXPIRED"):
        await principal.draft(principal_request(route(snapshot_ref=snapshot_ref)))

    assert provider.invocations == []


@pytest.mark.asyncio
async def test_principal_context_rejects_deleted_snapshot_before_model() -> None:
    broker = ContextBroker()
    scope = context_scope()
    snapshot_ref = snapshot_for(broker, scope=scope)
    broker.delete_subject(scope.tenant_id, scope.subject_ids[0])
    principal, provider = runtime(broker=broker)

    with pytest.raises(ContextContractError, match="CONTEXT_SNAPSHOT_NOT_FOUND"):
        await principal.draft(principal_request(route(snapshot_ref=snapshot_ref)))

    assert provider.invocations == []


@pytest.mark.asyncio
async def test_principal_without_broker_marks_context_unavailable_without_fabrication() -> None:
    principal, provider = runtime(broker=None)

    draft = await principal.draft(principal_request(route(snapshot_ref="context:not-injected")))

    assert draft.output["candidate_ids"] == ["action:check-in"]
    assert provider.invocations[0].payload["context_projection"] == {
        "status": "UNAVAILABLE",
        "reason": "CONTEXT_PROJECTION_UNAVAILABLE",
    }
