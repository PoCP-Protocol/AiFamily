"""Explicit synthetic runtime for exercising the production-shaped AI path.

This module is a test/development composition root, not a feature shortcut.
It wires the same context-bound application, provider-neutral router and Model
Gateway used by a real deployment, replacing only the network provider with a
deterministic ``FakeProvider``.  The factory refuses missing scope inputs and
refuses any environment other than ``test``; there is no global family or
tenant fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
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
from backend.intelligence.experience.run_http import InMemoryExperienceRunLedger
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import (
    ProviderRecord,
    ProviderRegistry,
)
from backend.intelligence.model_gateway.providers.fake import FakeProvider

_SYNTHETIC_PURPOSE = "family-image-summary"
_SYNTHETIC_PROVIDER_ID = "synthetic-deterministic"


@dataclass(frozen=True, slots=True)
class _ScopeBoundSyntheticApplication:
    """Bind the synthetic application to one explicit scope envelope."""

    scope: ContextScope
    delegate: ContextBoundMultimodalExperienceService

    async def generate_draft(
        self, command: ContextBoundMultimodalCommand
    ) -> ContextBoundMultimodalDraft:
        if command.scope != self.scope:
            raise ContextScopeError("SYNTHETIC_RUNTIME_SCOPE_MISMATCH")
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

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, str) or not self.tenant_id.strip():
            raise ValueError("tenant_id must be explicit")
        if not isinstance(self.subject_ids, tuple) or not self.subject_ids:
            raise ValueError("subject_ids must be explicit")
        if any(not isinstance(subject, str) or not subject.strip() for subject in self.subject_ids):
            raise ValueError("subject_ids must contain non-empty ids")
        if len(set(self.subject_ids)) != len(self.subject_ids):
            raise ValueError("subject_ids must be unique")
        if self.environment != "test":
            raise ValueError("synthetic runtime only supports the test environment")

    async def resolve(self, family_id: str) -> MultimodalDraftRuntime:
        """Build a runtime bound to this request's family path."""

        return build_synthetic_runtime(
            family_id=family_id,
            tenant_id=self.tenant_id,
            subject_ids=self.subject_ids,
            environment=self.environment,
            run_ledger=self.run_ledger,
        )


def build_synthetic_runtime(
    family_id: str,
    tenant_id: str | None = None,
    subject_ids: tuple[str, ...] | None = None,
    *,
    environment: str = "test",
    run_ledger: InMemoryExperienceRunLedger | None = None,
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
    if environment != "test":
        raise ValueError("synthetic runtime only supports the test environment")

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

    provider = FakeProvider(
        {
            _SYNTHETIC_PURPOSE: {
                "headline": "合成运行时草案",
                "next_step": "由家庭成员确认后再继续",
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
    gateway = ModelGateway(
        {_SYNTHETIC_PROVIDER_ID: provider},
        environment=environment,
        registry=ProviderRegistry((provider_record,)),
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
    routed = RoutedMultimodalExperienceService(
        router=MultimodalRouter((profile,)),
        generation=MultimodalExperienceService(gateway),
    )
    context_bound = ContextBoundMultimodalExperienceService(context=ContextBroker(), routed=routed)
    application: MultimodalDraftApplication = _ScopeBoundSyntheticApplication(
        scope=scope, delegate=context_bound
    )
    return MultimodalDraftRuntime(
        scope=scope,
        application=application,
        environment=environment,
        run_ledger=(
            run_ledger if run_ledger is not None else InMemoryExperienceRunLedger()
        ),
    )


__all__ = ["SyntheticRuntimeResolver", "build_synthetic_runtime"]
