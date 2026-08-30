from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.experience.contracts import (
    DeletionRef,
    ExperienceEvent,
    ExperienceEventType,
    ExperienceNode,
    ExperienceProvenance,
    ExperienceScope,
    MemoryLevel,
    MemoryRef,
    MemoryScope,
    ProvenanceKind,
    ScopeMismatchError,
)
from backend.intelligence.knowledge.contracts import KnowledgeClaim, KnowledgeSource
from backend.intelligence.knowledge.registry import KnowledgeRegistry
from backend.intelligence.model_gateway import FakeProvider, ModelGateway, ModelGatewayError
from backend.intelligence.principal.contracts import (
    PrincipalCapability,
    PrincipalEntryPoint,
    PrincipalRouteRequest,
)
from backend.intelligence.principal.router import (
    PrincipalCapabilityRouter,
    registered_capabilities,
)
from backend.intelligence.principal.runtime import (
    PrincipalDraft,
    PrincipalRuntime,
    PrincipalRuntimeError,
    PrincipalRuntimeRequest,
)
from backend.packages.contracts.evidence import Provenance
from backend.platform.idempotency.keys import IdempotencyKey


def _request(
    capability: PrincipalCapability,
    *,
    entry_point: PrincipalEntryPoint = PrincipalEntryPoint.ASK_PRINCIPAL,
    data_class: str = "FAMILY_PRIVATE_TEXT",
    family_id: str | None = "family-1",
    consent_granted: bool = True,
    locale: str = "zh-CN",
    content_locale: str | None = None,
    model_locale: str | None = None,
    policy_locale: str | None = None,
    region: str = "CN",
    tenant_policy_version: str = "tenant-policy.v1",
    tenant_id: str = "tenant-1",
    subject_id: str | None = "person-1",
    purpose: str = "family_growth_support",
) -> PrincipalRouteRequest:
    return PrincipalRouteRequest(
        request_id="request-1",
        tenant_id=tenant_id,
        actor_type="guardian",
        entry_point=entry_point,
        capability=capability,
        purpose=purpose,
        data_class=data_class,  # type: ignore[arg-type]
        context_snapshot_ref="context:1",
        consent_granted=consent_granted,
        global_id="principal-request-1",
        consent_version="consent.v1",
        correlation_id="correlation-1",
        causation_id="causation-1",
        family_id=family_id,
        subject_id=subject_id,
        locale=locale,
        content_locale=content_locale,
        model_locale=model_locale,
        policy_locale=policy_locale,
        region=region,
        tenant_policy_version=tenant_policy_version,
    )


def test_principal_routes_family_capability_without_granting_fact_write() -> None:
    decision = PrincipalCapabilityRouter().resolve(_request(PrincipalCapability.GROWTH_PLAN_DRAFT))

    assert decision.profile_id == "growth_planning"
    assert decision.agent_id == "growth_planner"
    assert decision.human_gate.value == "EXPLICIT_CONFIRMATION"
    assert decision.may_mutate_business_state is False
    assert decision.soul_ref.identity_cloning is False
    assert decision.global_id == "principal-request-1"
    assert decision.consent_version == "consent.v1"
    assert decision.correlation_id == "correlation-1"
    assert decision.causation_id == "causation-1"
    assert decision.locale == "zh-CN"
    assert decision.region == "CN"


def test_principal_routes_internal_service_design_without_family_scope() -> None:
    decision = PrincipalCapabilityRouter().resolve(
        _request(
            PrincipalCapability.SERVICE_PRODUCT_COMPILE,
            entry_point=PrincipalEntryPoint.PRODUCT_DESIGN_WORKBENCH,
            data_class="OPERATIONAL_TEXT",
            family_id=None,
        )
    )

    assert decision.profile_id == "service_product_architect"
    assert "compile_service_blueprint" in decision.allowed_tools
    assert decision.output_type.value == "Draft"


def test_principal_requires_consent_for_family_private_or_minor_data() -> None:
    with pytest.raises(ValueError, match="CONSENT_REQUIRED"):
        _request(PrincipalCapability.FAMILY_ASSISTANT_CONVERSATION, consent_granted=False)


def test_principal_rejects_minor_data_for_internal_design_profiles() -> None:
    request = _request(
        PrincipalCapability.SERVICE_PRODUCT_SIMULATION,
        entry_point=PrincipalEntryPoint.PRODUCT_DESIGN_WORKBENCH,
        data_class="MINOR_PERSONAL_DATA",
        family_id=None,
    )
    with pytest.raises(ValueError, match="SCOPE_DENIED"):
        PrincipalCapabilityRouter().resolve(request)


def test_route_set_is_explicit_and_no_capability_is_implicitly_accepted() -> None:
    assert PrincipalCapability.OPERATIONS_INSIGHT in registered_capabilities()
    with pytest.raises(ValueError, match="ROUTE_NOT_REGISTERED"):
        PrincipalCapabilityRouter().resolve(
            _request("unregistered")  # type: ignore[arg-type]
        )


def test_principal_carries_locale_and_tenant_policy_without_cross_tenant_fallback() -> None:
    decision = PrincipalCapabilityRouter().resolve(
        _request(
            PrincipalCapability.FAMILY_ASSISTANT_CONVERSATION,
            locale="en-US",
            content_locale="zh-CN",
            model_locale="en-US",
            policy_locale="en-US",
            region="US",
            tenant_policy_version="tenant-policy.v3",
        )
    )

    assert decision.locale == "en-US"
    assert decision.content_locale == "zh-CN"
    assert decision.model_locale == "en-US"
    assert decision.policy_locale == "en-US"
    assert decision.region == "US"
    assert decision.tenant_policy_version == "tenant-policy.v3"


def test_principal_rejects_malformed_locale_or_region() -> None:
    with pytest.raises(ValueError, match="LOCALE_UNSUPPORTED"):
        _request(PrincipalCapability.FAMILY_ASSISTANT_CONVERSATION, locale="bad locale")


def test_principal_rejects_missing_global_provenance_boundary() -> None:
    with pytest.raises(ValueError, match="identity and purpose"):
        replace(_request(PrincipalCapability.FAMILY_ASSISTANT_CONVERSATION), global_id="")


def _knowledge_registry(*, purpose: str = "family_growth_support") -> KnowledgeRegistry:
    source = KnowledgeSource(
        source_id="source:family-growth",
        title="Reviewed family growth guidance",
        license_ref="license:internal",
        owner="family-education",
        scope="family_growth_reviewed",
        verified=True,
    )
    claim = KnowledgeClaim(
        claim_id="claim:family-growth-1",
        text="A bounded, reviewed guidance claim.",
        source_id=source.source_id,
        provenance=Provenance(level="E6", source_ref=source.source_id),
        scope="family_growth_reviewed",
        status="REVIEWED",
        allowed_purposes=(purpose,),
    )
    registry = KnowledgeRegistry(sources=(source,), claims=(claim,))
    registry.transition_claim(claim.claim_id, "PUBLISHED")
    return registry


def _runtime_request(
    *,
    route_request: PrincipalRouteRequest | None = None,
    knowledge_purpose: str = "family_growth_support",
    experience_event: ExperienceEvent | None = None,
    memory_refs: tuple[MemoryRef, ...] = (),
) -> PrincipalRuntimeRequest:
    return PrincipalRuntimeRequest(
        route_request=route_request
        or _request(
            PrincipalCapability.EXPERIENCE_CURATION,
            data_class="OPERATIONAL_TEXT",
        ),
        prompt="Suggest one kind next step for the family.",
        knowledge_scope="family_growth_reviewed",
        knowledge_purpose=knowledge_purpose,
        output_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "candidate_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["message", "candidate_ids"],
            "additionalProperties": False,
        },
        experience_event=experience_event,
        memory_refs=memory_refs,
    )


def _runtime(
    *,
    response: dict[str, object] | None = None,
) -> tuple[PrincipalRuntime, FakeProvider]:
    provider = FakeProvider(
        {
            PrincipalCapability.EXPERIENCE_CURATION.value: response
            or {"message": "Try a ten-minute check-in.", "candidate_ids": ["action:check-in"]}
        }
    )
    gateway = ModelGateway({"fake-deterministic": provider}, environment="test")
    return (
        PrincipalRuntime(
            gateway=gateway,
            knowledge_registry=_knowledge_registry(),
            provider_id="fake-deterministic",
        ),
        provider,
    )


def _experience_scope(
    *,
    tenant_id: str = "tenant-1",
    family_id: str = "family-1",
    subject_ids: tuple[str, ...] = ("person-1",),
    purpose: str = "family_growth_support",
    consent_version: str = "consent.v1",
    consent_granted: bool = True,
    data_class: str = "OPERATIONAL_TEXT",
) -> ExperienceScope:
    return ExperienceScope(
        global_id="event-global-1",
        tenant_id=tenant_id,
        region_id="CN",
        family_id=family_id,
        subject_ids=subject_ids,
        purpose=purpose,
        consent_version=consent_version,
        consent_granted=consent_granted,
        data_class=data_class,  # type: ignore[arg-type]
        locale="zh-CN",
        content_locale="zh-CN",
        model_locale="zh-CN",
        policy_locale="zh-CN",
        deletion_ref=DeletionRef("delete:event-1", "experience.v1"),
        correlation_id="correlation-1",
        causation_id="causation-1",
    )


def _event(*, scope: ExperienceScope) -> ExperienceEvent:
    return ExperienceEvent(
        event_id="event:entry-1",
        event_type=ExperienceEventType.CONTENT_SELECTED,
        node=ExperienceNode.N3,
        scope=scope,
        idempotency_key=IdempotencyKey(scope.tenant_id, "event-entry-1"),
        provenance=ExperienceProvenance(
            provenance_ref="prov:event-1",
            source_refs=("user:guardian-1",),
            kind=ProvenanceKind.USER,
            policy_version="experience-policy.v1",
        ),
        actor_id="guardian-1",
    )


def _memory_ref(
    *,
    tenant_id: str = "tenant-1",
    family_id: str = "family-1",
    subject_ids: tuple[str, ...] = ("person-1",),
    purpose: str = "family_growth_support",
) -> MemoryRef:
    return MemoryRef(
        memory_id="memory:check-in-1",
        memory_ref="memory-store:check-in-1",
        tenant_id=tenant_id,
        region_id="CN",
        family_id=family_id,
        subject_ids=subject_ids,
        memory_scope=MemoryScope.CHILD,
        level=MemoryLevel.M1_SESSION,
        purpose=purpose,
        consent_version="consent.v1",
        consent_granted=True,
        data_class="MINOR_PERSONAL_DATA",
        locale="zh-CN",
        provenance=ExperienceProvenance(
            provenance_ref="prov:memory-1",
            source_refs=("event:entry-1",),
            kind=ProvenanceKind.USER,
            policy_version="memory-policy.v1",
        ),
        deletion_ref=DeletionRef("delete:memory-1", "memory.v1"),
        source_ref="event:entry-1",
        correlation_id="correlation-1",
        causation_id="causation-1",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )


def test_experience_curator_route_carries_scope_and_confirmation_gate() -> None:
    decision = PrincipalCapabilityRouter().resolve(
        _request(PrincipalCapability.EXPERIENCE_CURATION, data_class="OPERATIONAL_TEXT")
    )

    assert decision.profile_id == "experience_curator"
    assert decision.output_type.value == "Recommendation"
    assert decision.human_gate.value == "EXPLICIT_CONFIRMATION"
    assert decision.tenant_id == "tenant-1"
    assert decision.family_id == "family-1"
    assert decision.subject_id == "person-1"
    assert decision.purpose == "family_growth_support"
    assert decision.consent_granted is True


def test_memory_candidate_route_is_explicit_and_human_gated() -> None:
    decision = PrincipalCapabilityRouter().resolve(
        _request(PrincipalCapability.MEMORY_CANDIDATE_DRAFT, data_class="OPERATIONAL_TEXT")
    )

    assert decision.profile_id == "experience_curator"
    assert "draft_memory_candidate" in decision.allowed_tools
    assert decision.output_type.value == "Draft"
    assert decision.risk_level.value == "HIGH"
    assert decision.may_mutate_business_state is False


@pytest.mark.asyncio
async def test_principal_runtime_routes_knowledge_and_gateway_to_an_immutable_draft() -> None:
    runtime, provider = _runtime()
    event = _event(scope=_experience_scope())

    draft = await runtime.draft(_runtime_request(experience_event=event))

    assert isinstance(draft, PrincipalDraft)
    assert draft.status == "DRAFT"
    assert draft.output["candidate_ids"] == ["action:check-in"]
    assert draft.knowledge_claim_ids == ("claim:family-growth-1",)
    assert draft.route.profile_id == "experience_curator"
    assert draft.tenant_id == "tenant-1"
    assert draft.family_id == "family-1"
    assert draft.subject_id == "person-1"
    assert draft.purpose == "family_growth_support"
    assert draft.experience_event_id == "event:entry-1"
    assert draft.may_mutate_business_state is False
    assert draft.requires_human_confirmation is True
    assert draft.model_provenance.provider_id == "fake-deterministic"
    assert len(provider.invocations) == 1
    assert provider.invocations[0].input_refs == ("claim:family-growth-1",)
    assert provider.invocations[0].payload["experience_event"] == {
        "event_id": "event:entry-1",
        "event_type": "content_selected",
        "node": "N3",
    }


@pytest.mark.asyncio
async def test_principal_runtime_scopes_memory_without_forwarding_raw_memory() -> None:
    runtime, provider = _runtime()

    draft = await runtime.draft(_runtime_request(memory_refs=(_memory_ref(),)))

    assert draft.memory_ref_ids == ("memory:check-in-1",)
    payload = provider.invocations[0].payload
    assert payload["memory_refs"] == [
        {"memory_id": "memory:check-in-1", "memory_scope": "child", "level": "M1"}
    ]
    assert "memory-store:check-in-1" not in repr(payload)


@pytest.mark.asyncio
async def test_principal_runtime_rejects_cross_tenant_event_before_provider() -> None:
    runtime, provider = _runtime()
    event = _event(scope=_experience_scope(tenant_id="tenant-foreign"))

    with pytest.raises(ScopeMismatchError, match="CROSS_TENANT_EXPERIENCE_CONTEXT"):
        await runtime.draft(_runtime_request(experience_event=event))

    assert provider.invocations == []


@pytest.mark.asyncio
async def test_principal_runtime_rejects_cross_subject_event_and_purpose_mismatch() -> None:
    runtime, provider = _runtime()
    subject_event = _event(scope=_experience_scope(subject_ids=("person-other",)))

    with pytest.raises(ScopeMismatchError, match="CROSS_SUBJECT_EXPERIENCE_CONTEXT"):
        await runtime.draft(_runtime_request(experience_event=subject_event))
    assert provider.invocations == []

    purpose_event = _event(scope=_experience_scope(purpose="other_purpose"))
    with pytest.raises(ValueError, match="EXPERIENCE_PURPOSE_MISMATCH"):
        await runtime.draft(_runtime_request(experience_event=purpose_event))
    assert provider.invocations == []


@pytest.mark.asyncio
async def test_principal_runtime_rejects_cross_tenant_memory_before_provider() -> None:
    runtime, provider = _runtime()

    with pytest.raises(ScopeMismatchError, match="CROSS_TENANT_MEMORY_READ"):
        await runtime.draft(
            _runtime_request(memory_refs=(_memory_ref(tenant_id="tenant-foreign"),))
        )

    assert provider.invocations == []


@pytest.mark.asyncio
async def test_principal_runtime_fails_closed_when_knowledge_is_out_of_purpose() -> None:
    runtime, provider = _runtime()

    with pytest.raises(PrincipalRuntimeError, match="KNOWLEDGE_NOT_AVAILABLE"):
        await runtime.draft(
            _runtime_request(knowledge_purpose="purpose-without-reviewed-claim")
        )

    assert provider.invocations == []


@pytest.mark.asyncio
async def test_principal_runtime_leaves_private_data_at_gateway_admission_boundary() -> None:
    runtime, provider = _runtime()
    request = _runtime_request(
        route_request=_request(
            PrincipalCapability.EXPERIENCE_CURATION,
            data_class="FAMILY_PRIVATE_TEXT",
        )
    )

    with pytest.raises(ModelGatewayError) as error:
        await runtime.draft(request)

    assert error.value.kind == "POLICY_REJECTED"
    assert provider.invocations == []


@pytest.mark.asyncio
async def test_principal_draft_cannot_be_promoted_by_changing_status() -> None:
    runtime, _ = _runtime()
    draft = await runtime.draft(_runtime_request())

    with pytest.raises(PrincipalRuntimeError, match="DRAFT_STATUS"):
        replace(draft, status="PROMOTED")  # type: ignore[arg-type]
