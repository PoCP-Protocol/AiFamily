"""Explicit synthetic runtime for exercising the production-shaped AI path.

This module is a test/development composition root, not a feature shortcut.
It wires the same context-bound application, provider-neutral router and Model
Gateway used by a real deployment, replacing only the network provider with a
deterministic ``FakeProvider``.  The factory refuses missing scope inputs and
refuses any environment other than ``development`` or ``test``; there is no global family or
tenant fallback.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from backend.intelligence.context_engine.contracts import (
    ContextScope,
    ContextScopeError,
    DataClass,
)
from backend.intelligence.context_engine.store import ContextBroker
from backend.intelligence.experience.api import (
    MultimodalDraftApplication,
    MultimodalDraftRuntime,
)
from backend.intelligence.experience.asset_digest import (
    family_experience_contract_asset_digest,
)
from backend.intelligence.experience.contract_binding import (
    MultimodalContractRegistryBinding,
    ReleaseContractExpectation,
)
from backend.intelligence.experience.execution_materials import (
    InMemoryExecutionMaterialRegistry,
    execution_material_digest,
)
from backend.intelligence.experience.multimodal_application import (
    RoutedMultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_context_application import (
    ContextBoundMultimodalCommand,
    ContextBoundMultimodalDraft,
    ContextBoundMultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_generation import MultimodalExperienceService
from backend.intelligence.experience.multimodal_routing import (
    QWEN_MULTIMODAL_CANDIDATE,
    MultimodalRouter,
)
from backend.intelligence.experience.release_bundle import FamilyExperienceReleaseBundle
from backend.intelligence.experience.release_set import (
    FamilyExperienceReleaseSet,
    build_family_experience_release_set,
)
from backend.intelligence.experience.release_set_deployment import (
    ReleaseSetDeploymentReceipt,
)
from backend.intelligence.experience.run_http import InMemoryExperienceRunLedger
from backend.intelligence.experience.runtime_release_binding import (
    ActiveFamilyExperienceRuntimeBinding,
    StaticActiveFamilyExperienceReleaseResolver,
    validate_active_runtime_binding,
)
from backend.intelligence.experience.standard_assets import (
    FamilyExperienceAssetBundle,
    build_family_experience_assets,
)
from backend.intelligence.experience.standard_contracts import (
    FAMILY_EXPERIENCE_USE_CASE,
    build_family_experience_contract_binding,
)
from backend.intelligence.model_gateway.budget import (
    InMemoryModelBudgetStore,
    ModelBudgetPolicy,
    ModelBudgetRuntime,
    ModelRate,
    ModelRateCard,
    build_budget_account,
)
from backend.intelligence.model_gateway.contracts import (
    KnowledgeExecutionPayload,
    ModelReleaseBinding,
    PromptExecutionPlan,
)
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provenance import (
    InMemoryModelDraftRegistry,
    ModelDraftRegistryPort,
)
from backend.intelligence.model_gateway.provider_registry import (
    ProviderRecord,
    ProviderRegistry,
)
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.intelligence.model_gateway.release_fence import (
    InMemoryModelInvocationFence,
)
from backend.intelligence.prompt_registry.registry import PromptRegistry
from backend.intelligence.safety.runtime import SafetyRuntime
from backend.intelligence.schema_registry.registry import SchemaRegistry

_SYNTHETIC_PURPOSE = FAMILY_EXPERIENCE_USE_CASE
_SYNTHETIC_PROVIDER_ID = "synthetic-deterministic"
_SYNTHETIC_ROUTING_POLICY_VERSION = "synthetic-routing.v1"
_SYNTHETIC_ENVIRONMENTS = frozenset({"development", "test"})


@dataclass(frozen=True, slots=True)
class _ScopeBoundSyntheticApplication:
    """Bind the synthetic application to one explicit scope envelope."""

    scope: ContextScope
    delegate: ContextBoundMultimodalExperienceService
    gateway: ModelGateway
    router: MultimodalRouter
    active_release_resolver: StaticActiveFamilyExperienceReleaseResolver
    prompt_execution_plan: PromptExecutionPlan
    model_draft_subject_id: str | None = None

    async def generate_draft(
        self, command: ContextBoundMultimodalCommand
    ) -> ContextBoundMultimodalDraft:
        if command.scope != self.scope:
            raise ContextScopeError("SYNTHETIC_RUNTIME_SCOPE_MISMATCH")
        budget_runtime = self.gateway.budget_runtime
        safety_runtime = self.gateway.safety_runtime
        if budget_runtime is None or safety_runtime is None:  # pragma: no cover
            raise RuntimeError("synthetic budget or safety runtime is unavailable")
        binding = await self.active_release_resolver.resolve(
            environment=self.gateway.environment,
            use_case=command.scope.purpose,
            data_class=command.scope.data_class.value,
        )
        validate_active_runtime_binding(
            binding,
            router=self.router,
            budget_runtime=budget_runtime,
            safety_runtime=safety_runtime,
            environment=self.gateway.environment,
            use_case=command.scope.purpose,
            data_class=command.scope.data_class.value,
        )
        release_set = binding.release_set
        if (
            command.prompt_version != release_set.prompt_version
            or command.schema_version != release_set.schema_version
        ):
            raise ValueError("ACTIVE_RELEASE_CONTRACT_VERSION_MISMATCH")
        if command.prompt_execution_plan is not None and (
            command.prompt_execution_plan != self.prompt_execution_plan
        ):
            raise ValueError("ACTIVE_RELEASE_PROMPT_EXECUTION_MISMATCH")
        command = replace(
            command,
            release_binding=ModelReleaseBinding(
                release_set_id=release_set.release_set_id,
                deployment_receipt_id=binding.deployment_receipt.receipt_id,
                deployment_sequence=binding.deployment_receipt.sequence,
                runtime_config_digest=release_set.runtime_config_digest,
                control_id=binding.deployment_receipt.control_id,
                provider_bundle_ids=tuple(
                    zip(release_set.provider_ids, release_set.bundle_ids, strict=True)
                ),
            ),
            prompt_execution_plan=self.prompt_execution_plan,
        )
        if self.model_draft_subject_id is not None:
            command = replace(
                command,
                model_draft_subject_id=self.model_draft_subject_id,
            )
        return await self.delegate.generate_draft(command)


@dataclass(frozen=True, slots=True)
class SyntheticRuntimeResolver:
    """Resolve a fresh synthetic runtime for each request path family.

    The resolver intentionally stores no family id.  Tenant and subject scope
    are explicit constructor inputs; ``family_id`` is supplied per call and is
    passed through the same factory validation before a new application graph
    is built.
    """

    tenant_id: str
    subject_ids: tuple[str, ...]
    environment: str = "test"
    run_ledger: InMemoryExperienceRunLedger = field(default_factory=InMemoryExperienceRunLedger)
    model_draft_subject_id: str | None = None
    model_draft_registry: InMemoryModelDraftRegistry | None = None
    context_broker: ContextBroker = field(default_factory=ContextBroker)
    contract_binding: MultimodalContractRegistryBinding | None = None
    budget_store: InMemoryModelBudgetStore | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, str) or not self.tenant_id.strip():
            raise ValueError("tenant_id must be explicit")
        if not isinstance(self.subject_ids, tuple) or not self.subject_ids:
            raise ValueError("subject_ids must be explicit")
        if any(not isinstance(subject, str) or not subject.strip() for subject in self.subject_ids):
            raise ValueError("subject_ids must contain non-empty ids")
        if len(set(self.subject_ids)) != len(self.subject_ids):
            raise ValueError("subject_ids must be unique")
        if self.environment not in _SYNTHETIC_ENVIRONMENTS:
            raise ValueError("synthetic runtime only supports development or test")
        if self.budget_store is None:
            now = datetime.now(UTC)
            policy = _synthetic_budget_policy()
            object.__setattr__(
                self,
                "budget_store",
                InMemoryModelBudgetStore(
                    (
                        build_budget_account(
                            tenant_id=self.tenant_id,
                            environment=self.environment,
                            policy=policy,
                            now=now,
                        ),
                    )
                ),
            )
        if self.model_draft_subject_id is not None:
            if self.model_draft_subject_id not in self.subject_ids:
                raise ValueError("model_draft_subject_id must belong to subject_ids")
            if self.model_draft_registry is None:
                object.__setattr__(self, "model_draft_registry", InMemoryModelDraftRegistry())
        if self.model_draft_registry is not None and self.model_draft_subject_id is None:
            raise ValueError("model_draft_subject_id is required with a model draft registry")

    async def resolve(self, family_id: str) -> MultimodalDraftRuntime:
        """Build a runtime bound to this request's family path."""

        return build_synthetic_runtime(
            family_id=family_id,
            tenant_id=self.tenant_id,
            subject_ids=self.subject_ids,
            environment=self.environment,
            run_ledger=self.run_ledger,
            model_draft_subject_id=self.model_draft_subject_id,
            model_draft_registry=self.model_draft_registry,
            context_broker=self.context_broker,
            contract_binding=self.contract_binding,
            budget_store=self.budget_store,
        )


def build_synthetic_runtime(
    family_id: str,
    tenant_id: str | None = None,
    subject_ids: tuple[str, ...] | None = None,
    *,
    environment: str = "test",
    run_ledger: InMemoryExperienceRunLedger | None = None,
    model_draft_subject_id: str | None = None,
    model_draft_registry: ModelDraftRegistryPort | None = None,
    context_broker: ContextBroker | None = None,
    contract_binding: MultimodalContractRegistryBinding | None = None,
    budget_store: InMemoryModelBudgetStore | None = None,
) -> MultimodalDraftRuntime:
    """Build a production-shaped runtime backed by deterministic test data.

    ``tenant_id`` and ``subject_ids`` deliberately default to ``None`` only so
    omission produces an explicit error.  They are never replaced with a
    process-wide or demo-family value.  ``environment='production'`` is also a
    hard error: synthetic credentials/data must never be accidentally wired to
    production semantics.
    """

    if not isinstance(family_id, str) or not family_id.strip():
        raise ValueError("family_id must be explicit")
    if tenant_id is None or not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("tenant_id must be explicit; synthetic runtime has no global tenant")
    if subject_ids is None:
        raise ValueError("subject_ids must be explicit; synthetic runtime has no global scope")
    if not isinstance(subject_ids, tuple) or not subject_ids:
        raise ValueError("subject_ids must be a non-empty tuple")
    if environment not in _SYNTHETIC_ENVIRONMENTS:
        raise ValueError("synthetic runtime only supports development or test")
    if model_draft_subject_id is not None and model_draft_subject_id not in subject_ids:
        raise ValueError("model_draft_subject_id must belong to subject_ids")
    if model_draft_registry is not None and model_draft_subject_id is None:
        raise ValueError("model_draft_subject_id is required with a model draft registry")

    scope = ContextScope(
        tenant_id=tenant_id,
        region_id="CN",
        family_id=family_id,
        subject_ids=subject_ids,
        purpose=_SYNTHETIC_PURPOSE,
        consent_version="synthetic-consent.v1",
        consent_granted=True,
        data_class=DataClass.SYNTHETIC,
        locale="zh-CN",
        deletion_ref=f"synthetic-delete:{tenant_id}:{family_id}",
        correlation_id=f"synthetic-correlation:{uuid4()}",
        causation_id=f"synthetic-causation:{uuid4()}",
    )

    assets = build_family_experience_assets(
        status="PUBLISHED",
        reviewer="operator:synthetic-release",
        effective_at=datetime.now(UTC) - timedelta(days=1),
        change_reason="Synthetic adapter for production-parity contract tests",
    )
    provider = FakeProvider(
        {
            _SYNTHETIC_PURPOSE: {
                "understanding": "这是由生产同构测试链路生成的合成草案",
                "next_step": "由家庭成员确认后再继续",
                "limitations": ["仅使用隔离的合成数据，不代表真实家庭事实"],
            }
        },
        provider_id=_SYNTHETIC_PROVIDER_ID,
    )
    provider_record = ProviderRecord(
        provider_id=_SYNTHETIC_PROVIDER_ID,
        vendor="aifamily-test",
        model="fake-deterministic",
        model_version="1.0.0",
        status="INTERNAL_APPROVED",
        approved_environments=(environment,),
        sub_delegates=False,
        security_assessment_ref="synthetic-test-only",
        processing_agreement_ref="synthetic-test-only",
        deletion_on_termination_committed=True,
        processing_region="local-test",
    )
    budget_now = datetime.now(UTC)
    budget_policy = _synthetic_budget_policy()
    if budget_store is None:
        budget_store = InMemoryModelBudgetStore(
            (
                build_budget_account(
                    tenant_id=tenant_id,
                    environment=environment,
                    policy=budget_policy,
                    now=budget_now,
                ),
            )
        )
    budget_runtime = ModelBudgetRuntime(
        store=budget_store,
        rate_card=ModelRateCard(
            version="synthetic-family-rate.v1",
            rates=(
                ModelRate(
                    provider_id=_SYNTHETIC_PROVIDER_ID,
                    model="fake-deterministic",
                    prompt_microusd_per_1k=1,
                    completion_microusd_per_1k=1,
                    media_item_microusd=1,
                ),
            ),
            effective_at=budget_now - timedelta(days=1),
            expires_at=budget_now + timedelta(days=365),
        ),
        policy=budget_policy,
        environment=environment,
        clock=lambda: budget_now,
    )
    safety_runtime = SafetyRuntime()
    gateway = ModelGateway(
        {_SYNTHETIC_PROVIDER_ID: provider},
        environment=environment,
        registry=ProviderRegistry((provider_record,)),
        safety_runtime=safety_runtime,
        budget_runtime=budget_runtime,
    )
    profile = replace(
        QWEN_MULTIMODAL_CANDIDATE,
        provider_id=_SYNTHETIC_PROVIDER_ID,
        vendor="aifamily-test",
        model="fake-deterministic",
        model_version="1.0.0",
        status="INTERNAL_APPROVED",
        approved_environments=(environment,),
        approved_data_classes=frozenset({"SYNTHETIC"}),
        sub_delegates=False,
        security_assessment_ref="synthetic-test-only",
        processing_agreement_ref="synthetic-test-only",
        deletion_on_termination_committed=True,
    )
    router = MultimodalRouter(
        (profile,),
        policy_version=_SYNTHETIC_ROUTING_POLICY_VERSION,
    )
    release_set = _build_synthetic_release_set(
        environment=environment,
        provider_record=provider_record,
        router=router,
        budget_runtime=budget_runtime,
        safety_runtime=safety_runtime,
        assets=assets,
        now=budget_now,
    )
    active_binding = ActiveFamilyExperienceRuntimeBinding(
        release_set=release_set,
        deployment_receipt=_synthetic_active_receipt(release_set, budget_now),
    )
    synthetic_model_binding = ModelReleaseBinding(
        release_set_id=release_set.release_set_id,
        deployment_receipt_id=active_binding.deployment_receipt.receipt_id,
        deployment_sequence=active_binding.deployment_receipt.sequence,
        runtime_config_digest=release_set.runtime_config_digest,
        control_id=active_binding.deployment_receipt.control_id,
        provider_bundle_ids=tuple(
            zip(release_set.provider_ids, release_set.bundle_ids, strict=True)
        ),
    )
    gateway = gateway.with_invocation_fence(
        InMemoryModelInvocationFence(synthetic_model_binding)
    )
    routed = RoutedMultimodalExperienceService(
        router=router,
        generation=MultimodalExperienceService(
            gateway,
            registry=model_draft_registry,
        ),
    )
    context_bound = ContextBoundMultimodalExperienceService(
        context=context_broker or ContextBroker(),
        routed=routed,
        registry=model_draft_registry,
    )
    application: MultimodalDraftApplication = _ScopeBoundSyntheticApplication(
        scope=scope,
        delegate=context_bound,
        gateway=gateway,
        router=router,
        active_release_resolver=StaticActiveFamilyExperienceReleaseResolver(active_binding),
        prompt_execution_plan=_prompt_execution_plan(assets, release_set.asset_digest),
        model_draft_subject_id=model_draft_subject_id,
    )
    release_expectation = ReleaseContractExpectation(
        agent_id=release_set.agent_id,
        prompt_ref=release_set.prompt_ref,
        prompt_version=release_set.prompt_version,
        schema_ref=release_set.schema_ref,
        schema_version=release_set.schema_version,
        safety_policy_version=release_set.safety_policy_version,
        knowledge_refs=release_set.knowledge_refs,
        asset_digest=release_set.asset_digest,
    )
    if contract_binding is None:
        contract_binding = build_family_experience_contract_binding(
            prompt_registry=PromptRegistry(bundles=(assets.prompt,)),
            schema_registry=SchemaRegistry(definitions=(assets.schema,)),
            material_resolver=InMemoryExecutionMaterialRegistry(
                policies=(assets.system_policy,),
                knowledge=assets.knowledge,
            ),
        )
    contract_binding = replace(
        contract_binding,
        release_expectation=release_expectation,
        material_resolver=(
            contract_binding.material_resolver
            or InMemoryExecutionMaterialRegistry(
                policies=(assets.system_policy,),
                knowledge=assets.knowledge,
            )
        ),
    )
    return MultimodalDraftRuntime(
        scope=scope,
        application=application,
        environment=environment,
        run_ledger=(run_ledger if run_ledger is not None else InMemoryExperienceRunLedger()),
        contract_binding=contract_binding,
    )


def _build_synthetic_release_set(
    *,
    environment: str,
    provider_record: ProviderRecord,
    router: MultimodalRouter,
    budget_runtime: ModelBudgetRuntime,
    safety_runtime: SafetyRuntime,
    assets: FamilyExperienceAssetBundle,
    now: datetime,
) -> FamilyExperienceReleaseSet:
    asset_digest = family_experience_contract_asset_digest(
        prompt=assets.prompt,
        schema=assets.schema,
        system_policy=assets.system_policy,
        knowledge=assets.knowledge,
    )
    bundle_seed = (
        f"{environment}:{provider_record.provider_id}:{provider_record.model}:"
        f"{provider_record.model_version}:{asset_digest}"
    )
    bundle_id = hashlib.sha256(bundle_seed.encode()).hexdigest()
    bundle = FamilyExperienceReleaseBundle(
        bundle_id=bundle_id,
        candidate_id=f"synthetic:{provider_record.provider_id}:{provider_record.model_version}",
        environment=environment,
        use_case=_SYNTHETIC_PURPOSE,
        agent_id=assets.prompt.agent_id,
        provider_id=provider_record.provider_id,
        model=provider_record.model,
        model_version=provider_record.model_version,
        prompt_ref=assets.prompt.prompt_ref,
        prompt_version=assets.prompt.version,
        schema_ref=assets.schema.schema_ref,
        schema_version=assets.schema.version,
        safety_policy_version=assets.prompt.safety_policy_version,
        routing_policy_version=router.policy_version,
        rate_card_version=budget_runtime.rate_card.version,
        budget_policy_version=budget_runtime.policy.version,
        knowledge_refs=assets.prompt.knowledge_refs,
        data_class="SYNTHETIC",
        report_ref="synthetic:benchmark:production-parity",
        decision_id=hashlib.sha256(f"decision:{bundle_seed}".encode()).hexdigest(),
        control_id=hashlib.sha256(f"control:{bundle_seed}".encode()).hexdigest(),
        approval_signature_ref=hashlib.sha256(
            f"signature:{bundle_seed}".encode()
        ).hexdigest(),
        approval_signature_algorithm="synthetic-test-signature-v1",
        approved_by="operator:synthetic-release",
        approved_at=now,
        asset_digest=asset_digest,
        human_gate_rule="REVIEW_REQUIRED",
    )
    return build_family_experience_release_set(
        bundles=(bundle,),
        router=router,
        budget_runtime=budget_runtime,
        safety_runtime=safety_runtime,
    )


def _prompt_execution_plan(
    assets: FamilyExperienceAssetBundle,
    asset_digest: str,
) -> PromptExecutionPlan:
    return PromptExecutionPlan(
        prompt_ref=assets.prompt.prompt_ref,
        prompt_version=assets.prompt.version,
        template=assets.prompt.template,
        system_policy_ref=assets.prompt.system_policy_ref,
        safety_policy_version=assets.prompt.safety_policy_version,
        knowledge_refs=assets.prompt.knowledge_refs,
        asset_digest=asset_digest,
        system_policy=assets.system_policy.content,
        system_policy_digest=assets.system_policy.content_digest,
        knowledge_materials=tuple(
            KnowledgeExecutionPayload(
                knowledge_ref=item.knowledge_ref,
                content=item.content,
                source_ref=item.source_ref,
                license_ref=item.license_ref,
                evidence_level=item.evidence_level,
                content_digest=item.content_digest,
            )
            for item in assets.knowledge
        ),
        material_digest=execution_material_digest(
            assets.system_policy,
            assets.knowledge,
        ),
    )


def _synthetic_budget_policy() -> ModelBudgetPolicy:
    return ModelBudgetPolicy(
        version="synthetic-family-budget.v1",
        rate_card_version="synthetic-family-rate.v1",
        per_request_limit_microusd=1_000_000,
        period_limit_microusd=100_000_000,
        max_completion_tokens=8_192,
    )


def _synthetic_active_receipt(
    release_set: FamilyExperienceReleaseSet,
    now: datetime,
) -> ReleaseSetDeploymentReceipt:
    receipt_seed = f"active:{release_set.release_set_id}"
    return ReleaseSetDeploymentReceipt(
        sequence=1,
        receipt_id=hashlib.sha256(receipt_seed.encode()).hexdigest(),
        idempotency_key=receipt_seed,
        release_set_id=release_set.release_set_id,
        target_release_set_id=None,
        environment=release_set.environment,
        use_case=release_set.use_case,
        data_class=release_set.data_class,
        operation="APPLY",
        phase="ACTIVE",
        rollout_percent=100,
        control_id=hashlib.sha256(f"control:{receipt_seed}".encode()).hexdigest(),
        actor_id="operator:synthetic-release",
        applied_config_digest=release_set.runtime_config_digest,
        acknowledged_release_set_id=release_set.release_set_id,
        external_ref=f"synthetic-deployment:{release_set.release_set_id}",
        created_at=now,
    )


__all__ = ["SyntheticRuntimeResolver", "build_synthetic_runtime"]
