"""Model Gateway — the single point at which AiFamily may reach a model provider.

Why this package exists at all (R7 / R10, `governance/REPOSITORY_CONSTITUTION.md`):
domains must not call providers, and provider credentials must be read in exactly
one place. `tests/architecture/test_no_direct_provider_calls.py` and
`tests/architecture/test_compliance_constraints.py::test_no_direct_provider_sdk_outside_model_gateway`
both carve out `backend/intelligence/model_gateway` as the *only* allowed path —
so this package is not merely a convenience wrapper, it is the enforcement point.

Why it is also a compliance boundary (not just an architectural one):
`docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` §7 records that calling an
external LLM is 委托第三方处理 under 《儿童个人信息网络保护规定》第16条, which
forbids 转委托 (sub-delegation). Most LLM vendors re-subcontract to third-party
clouds. That makes "which provider may see which data class" a legal question
answered before the call, which is why `ProviderRegistry` admission is part of the
call path and cannot be bypassed.

What this package never does (R9 / `docs/05_ai/AI_NATIVE_PRINCIPLES.md` §2):
it does not produce business entities. Every result is a `ModelDraft` whose
`may_mutate_business_state` is a read-only `False` — a type-level fact, not a
docstring promise. Nothing here imports a business-domain repository; the only
way a draft becomes a canonical fact is a domain's own Named Action with a human
actor.

Public surface is deliberately small: build a `ModelGateway`, call
`generate_structured`, receive a `ModelDraft` or raise `ModelGatewayError`.
"""

from __future__ import annotations

from backend.intelligence.model_gateway.attempt_persistence import (
    AttemptPersistenceBase,
    ModelAttemptRow,
    SessionPerCallAttemptSink,
    SqlAlchemyAttemptSink,
)
from backend.intelligence.model_gateway.attempts import (
    AttemptOutcome,
    AttemptSink,
    InMemoryAttemptSink,
    NullAttemptSink,
)
from backend.intelligence.model_gateway.composition import (
    build_http_openai_compatible_gateway_from_registry,
    build_openai_compatible_gateway_from_registry,
    build_secret_manager_openai_compatible_gateway_from_registry,
)
from backend.intelligence.model_gateway.contracts import (
    AiProvenance,
    DataClass,
    MediaInput,
    ModelDraft,
    ModelReleaseBinding,
    PolicyContext,
    PromptExecutionPlan,
    StructuredRequest,
    TokenUsage,
)
from backend.intelligence.model_gateway.credentials import (
    CredentialLease,
    CredentialLeaseMetadata,
    CredentialRevocationChecker,
    HttpProviderCredentialPort,
    ProviderCredentialPort,
    SecretManagerCredentialPort,
)
from backend.intelligence.model_gateway.errors import (
    INFRA_FAILURE_KINDS,
    FailureKind,
    ModelGatewayError,
)
from backend.intelligence.model_gateway.gateway import (
    GATEWAY_POLICY,
    ModelGateway,
    build_gateway,
)
from backend.intelligence.model_gateway.provenance import (
    InMemoryModelDraftRegistry,
    ModelDraftIdentity,
    ModelDraftNotFound,
    ModelDraftRegistryBase,
    ModelDraftRegistryError,
    ModelDraftRegistryPort,
    ModelDraftRow,
    ModelDraftScope,
    SqlAlchemyModelDraftRegistry,
    StoredModelDraft,
)
from backend.intelligence.model_gateway.provider_registry import (
    ProviderRecord,
    ProviderRegistry,
    ProviderStatus,
    load_provider_registry,
)
from backend.intelligence.model_gateway.providers.base import ProviderAdapter, ProviderResponse
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.intelligence.model_gateway.providers.openai_compatible import (
    OpenAICompatibleProvider,
    build_openai_compatible_provider,
    build_openai_compatible_provider_from_lease,
)
from backend.intelligence.model_gateway.usage import CostRate, UsageSummary, aggregate_attempts

__all__ = [
    "GATEWAY_POLICY",
    "INFRA_FAILURE_KINDS",
    "AiProvenance",
    "AttemptOutcome",
    "AttemptSink",
    "AttemptPersistenceBase",
    "ModelAttemptRow",
    "SessionPerCallAttemptSink",
    "SqlAlchemyAttemptSink",
    "DataClass",
    "FailureKind",
    "FakeProvider",
    "InMemoryAttemptSink",
    "ModelDraft",
    "InMemoryModelDraftRegistry",
    "ModelDraftIdentity",
    "ModelDraftNotFound",
    "ModelDraftRegistryBase",
    "ModelDraftRegistryError",
    "ModelDraftRegistryPort",
    "ModelDraftRow",
    "ModelDraftScope",
    "MediaInput",
    "ModelReleaseBinding",
    "ModelGateway",
    "ModelGatewayError",
    "NullAttemptSink",
    "OpenAICompatibleProvider",
    "PolicyContext",
    "PromptExecutionPlan",
    "ProviderAdapter",
    "ProviderRecord",
    "ProviderRegistry",
    "ProviderResponse",
    "ProviderStatus",
    "StructuredRequest",
    "SqlAlchemyModelDraftRegistry",
    "StoredModelDraft",
    "TokenUsage",
    "CostRate",
    "UsageSummary",
    "aggregate_attempts",
    "build_gateway",
    "build_openai_compatible_gateway_from_registry",
    "build_http_openai_compatible_gateway_from_registry",
    "build_secret_manager_openai_compatible_gateway_from_registry",
    "build_openai_compatible_provider",
    "build_openai_compatible_provider_from_lease",
    "CredentialLease",
    "CredentialLeaseMetadata",
    "CredentialRevocationChecker",
    "ProviderCredentialPort",
    "HttpProviderCredentialPort",
    "SecretManagerCredentialPort",
    "load_provider_registry",
]
