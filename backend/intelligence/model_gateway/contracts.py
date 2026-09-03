"""Request / provenance / draft types.

Three design decisions here are load-bearing and each traces to a written
constraint rather than to taste:

**`DataClass` is on the request, not on the provider.** Admission asks "may this
provider process *this* data class", and the only party that knows the class is
the caller. Making it a required field means a caller cannot accidentally send
minor data under default settings — there is no default. This is the
《儿童个人信息网络保护规定》第16条 "不得超出授权范围" check expressed in a type.

**`AiProvenance` has no optional identity fields.** PIPL 第24条 gives an
individual the right to an explanation of an automated decision, and
`docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` §2 draws the direct
consequence: recording model / model_version / prompt_version /
context_snapshot_ref / confidence is 强制, not best practice. A provenance object
that can be constructed with half its fields missing would let an unexplainable
recommendation reach a family, so the constructor refuses.

**`ModelDraft.may_mutate_business_state` is a property returning `False`.** Not a
field with a `False` default — a default can be overridden at construction; a
frozen dataclass field can still be replaced via `dataclasses.replace`. A
property with no setter cannot be `True` for any instance, which is what
`AI_NATIVE_PRINCIPLES.md` §3.5 and `MIGRATION_PLAN_V2.md` §0 mean by
"`may_mutate_business_state = false`" being a fact about the runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal

DataClass = Literal[
    "SYNTHETIC",
    "OPERATIONAL_TEXT",
    "FAMILY_PRIVATE_TEXT",
    "MINOR_PERSONAL_DATA",
]
"""What kind of data the request payload contains.

* `SYNTHETIC` — fixtures/demo content. Note R5: synthetic data is never a
  business capability, so a draft derived from it must not be presented as one.
* `OPERATIONAL_TEXT` — platform-internal, no family or minor subject.
* `FAMILY_PRIVATE_TEXT` — family-authored content with no minor subject.
* `MINOR_PERSONAL_DATA` — any information about a person under 18. Under PIPL
  第28条 everything about an under-14 subject is sensitive personal information
  by category, without item-by-item judgement, so this class is deliberately
  coarse: the gateway does not attempt to decide that some minor data is less
  sensitive than other minor data.
"""

DraftStatus = Literal["DRAFT"]
"""The only status a gateway output may carry. There is no gateway-side
transition out of it: promotion happens in a business domain's Named Action with
a human actor (R8/R9), never here.
"""


MediaType = Literal["IMAGE", "AUDIO", "VIDEO", "DOCUMENT"]


@dataclass(frozen=True, slots=True)
class MediaInput:
    """A governed media reference passed to a multimodal model.

    The URI is a short-lived object-store URL or provider-approved data URL;
    raw media bytes never enter the request ledger. ``sha256`` lets an audit
    replay identify the exact asset without copying personal media into logs.
    """

    media_type: MediaType
    uri: str
    mime_type: str
    sha256: str

    def __post_init__(self) -> None:
        if not all((self.uri, self.mime_type, self.sha256)):
            raise ValueError("MediaInput uri, mime_type and sha256 are required")


@dataclass(frozen=True, slots=True)
class PolicyContext:
    """The caller's acknowledgement of the R9 contract, carried with the request.

    Both flags are fixed. They exist as explicit fields rather than as implicit
    assumptions because the source repository's request type carried the same two
    literals (`human_confirmation_required: true`, `may_mutate_business_state:
    false`) and that turned out to be the clearest place to state them — the
    request itself records that the caller was told.
    """

    human_confirmation_required: Literal[True] = True
    may_mutate_business_state: Literal[False] = False


@dataclass(frozen=True, slots=True)
class ModelReleaseBinding:
    """Content-addressed deployment authorization carried to every model attempt."""

    release_set_id: str
    deployment_receipt_id: str
    deployment_sequence: int
    runtime_config_digest: str
    control_id: str
    provider_bundle_ids: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        required = (
            self.release_set_id,
            self.deployment_receipt_id,
            self.runtime_config_digest,
            self.control_id,
        )
        if not all(value.strip() for value in required):
            raise ValueError("ModelReleaseBinding identity is required")
        if self.deployment_sequence <= 0:
            raise ValueError("ModelReleaseBinding deployment sequence must be positive")
        if not self.provider_bundle_ids:
            raise ValueError("ModelReleaseBinding provider bundles are required")
        providers = []
        for provider_id, bundle_id in self.provider_bundle_ids:
            if not provider_id.strip() or not bundle_id.strip():
                raise ValueError("ModelReleaseBinding provider bundle is invalid")
            providers.append(provider_id)
        if len(set(providers)) != len(providers):
            raise ValueError("ModelReleaseBinding provider ids must be unique")

    def bundle_id_for(self, provider_id: str) -> str:
        for candidate, bundle_id in self.provider_bundle_ids:
            if candidate == provider_id:
                return bundle_id
        raise ValueError("provider is not authorized by ModelReleaseBinding")


@dataclass(frozen=True, slots=True)
class KnowledgeExecutionPayload:
    knowledge_ref: str
    content: str
    source_ref: str
    license_ref: str
    evidence_level: str
    content_digest: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (
                self.knowledge_ref,
                self.content,
                self.source_ref,
                self.license_ref,
                self.evidence_level,
                self.content_digest,
            )
        ):
            raise ValueError("KnowledgeExecutionPayload reviewed fields are required")


@dataclass(frozen=True, slots=True)
class PromptExecutionPlan:
    """Reviewed prompt content supplied by the server-owned contract registry."""

    prompt_ref: str
    prompt_version: str
    template: str
    system_policy_ref: str
    safety_policy_version: str
    knowledge_refs: tuple[str, ...]
    asset_digest: str
    system_policy: str = ""
    system_policy_digest: str = ""
    knowledge_materials: tuple[KnowledgeExecutionPayload, ...] = ()
    material_digest: str = ""

    def __post_init__(self) -> None:
        required = (
            self.prompt_ref,
            self.prompt_version,
            self.template,
            self.system_policy_ref,
            self.safety_policy_version,
            self.asset_digest,
        )
        if not all(isinstance(value, str) and value.strip() for value in required):
            raise ValueError("PromptExecutionPlan reviewed content is required")
        if any(not ref.strip() for ref in self.knowledge_refs):
            raise ValueError("PromptExecutionPlan knowledge refs cannot be blank")
        if len(set(self.knowledge_refs)) != len(self.knowledge_refs):
            raise ValueError("PromptExecutionPlan knowledge refs must be unique")
        if self.knowledge_materials and tuple(
            item.knowledge_ref for item in self.knowledge_materials
        ) != self.knowledge_refs:
            raise ValueError("PromptExecutionPlan knowledge material order mismatch")
        has_any_material = bool(
            self.system_policy
            or self.system_policy_digest
            or self.knowledge_materials
            or self.material_digest
        )
        if has_any_material and not self.has_reviewed_materials:
            raise ValueError("PromptExecutionPlan execution materials are incomplete")

    @property
    def has_reviewed_materials(self) -> bool:
        return bool(
            self.system_policy.strip()
            and self.system_policy_digest.strip()
            and self.material_digest.strip()
            and len(self.knowledge_materials) == len(self.knowledge_refs)
        )


@dataclass(frozen=True, slots=True)
class StructuredRequest:
    """One structured-generation request.

    `output_schema` is required: unstructured free text has no schema to validate
    against, and a gateway that cannot validate cannot fail closed on a bad
    response — it can only hand raw model prose to the caller, which is the
    degradation this gateway exists to prevent.
    """

    use_case: str
    prompt_version: str
    schema_version: str
    data_class: DataClass
    payload: dict[str, Any]
    output_schema: dict[str, Any]
    context_snapshot_ref: str
    input_refs: tuple[str, ...] = ()
    media_inputs: tuple[MediaInput, ...] = ()
    request_id: str | None = None
    session_id: str | None = None
    policy_context: PolicyContext = field(default_factory=PolicyContext)
    tenant_id: str | None = None
    family_id: str | None = None
    release_binding: ModelReleaseBinding | None = None
    prompt_execution_plan: PromptExecutionPlan | None = None

    def __post_init__(self) -> None:
        missing = [
            name
            for name, value in (
                ("use_case", self.use_case),
                ("prompt_version", self.prompt_version),
                ("schema_version", self.schema_version),
                ("context_snapshot_ref", self.context_snapshot_ref),
            )
            if not value
        ]
        if missing:
            # Every one of these ends up in the provenance record. Allowing a
            # blank here would produce a draft that cannot be explained later,
            # which is the PIPL 第24条 failure the provenance requirement exists
            # to prevent — so it is rejected at the request boundary instead.
            raise ValueError(f"StructuredRequest is missing required field(s): {missing}")
        if not self.output_schema:
            raise ValueError(
                "StructuredRequest.output_schema is required — without a schema the "
                "gateway cannot fail closed on a malformed model response"
            )
        if (self.tenant_id is None) != (self.family_id is None):
            raise ValueError("StructuredRequest.tenant_id and family_id must be supplied together")
        if self.tenant_id is not None and (
            not self.tenant_id.strip() or not self.family_id or not self.family_id.strip()
        ):
            raise ValueError("StructuredRequest tenant/family scope values must be non-empty")
        if self.prompt_execution_plan is not None:
            if not isinstance(self.prompt_execution_plan, PromptExecutionPlan):
                raise ValueError("StructuredRequest prompt execution plan is invalid")
            if self.prompt_execution_plan.prompt_version != self.prompt_version:
                raise ValueError("StructuredRequest prompt execution plan version mismatch")
        if self.release_binding is not None and self.prompt_execution_plan is None:
            raise ValueError("release-bound requests require a PromptExecutionPlan")
        if (
            self.release_binding is not None
            and self.prompt_execution_plan is not None
            and not self.prompt_execution_plan.has_reviewed_materials
        ):
            raise ValueError("release-bound requests require reviewed execution materials")


@dataclass(frozen=True, slots=True)
class TokenUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

    def __post_init__(self) -> None:
        values = {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }
        for name, value in values.items():
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise ValueError(f"TokenUsage.{name} must be a non-negative integer or None")
            if value is not None and value < 0:
                raise ValueError(f"TokenUsage.{name} must be a non-negative integer or None")
        if (
            self.total_tokens is not None
            and self.prompt_tokens is not None
            and self.completion_tokens is not None
            and self.total_tokens < self.prompt_tokens + self.completion_tokens
        ):
            raise ValueError("TokenUsage.total_tokens cannot be below prompt + completion")


@dataclass(frozen=True, slots=True)
class AiProvenance:
    """The explanation record. Mandatory, and complete or not at all.

    Field set is fixed by `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` §2
    and `docs/05_ai/AI_NATIVE_PRINCIPLES.md` §2: model, model_version,
    prompt_version, context_snapshot_ref, confidence, latency_ms, provider_id.
    `data_class` is added on top because "which data class was sent to which
    provider" is the record needed to answer a §7 (不得转委托) audit question
    after the fact, and reconstructing it from logs later is not possible.

    `confidence` is `float | None` rather than `float`: many providers report no
    calibrated confidence, and inventing one would be a fabricated number in a
    compliance record. `None` honestly means "the provider did not report one";
    a made-up 0.9 would not.
    """

    provider_id: str
    model: str
    model_version: str
    prompt_version: str
    schema_version: str
    context_snapshot_ref: str
    latency_ms: int
    data_class: DataClass
    use_case: str
    confidence: float | None = None
    token_usage: TokenUsage | None = None
    release_set_id: str | None = None
    bundle_id: str | None = None
    deployment_receipt_id: str | None = None
    runtime_config_digest: str | None = None
    deployment_sequence: int | None = None
    control_id: str | None = None
    fence_claim_id: str | None = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    REQUIRED_IDENTITY_FIELDS: ClassVar[tuple[str, ...]] = (
        "provider_id",
        "model",
        "model_version",
        "prompt_version",
        "schema_version",
        "context_snapshot_ref",
        "use_case",
    )

    def __post_init__(self) -> None:
        missing = [name for name in self.REQUIRED_IDENTITY_FIELDS if not getattr(self, name, None)]
        if missing:
            raise ValueError(
                "AiProvenance is incomplete, missing "
                f"{missing}. PIPL 第24条 requires an automated decision to be "
                "explainable; a partial provenance record cannot explain one."
            )
        if self.latency_ms < 0:
            raise ValueError("AiProvenance.latency_ms must not be negative")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("AiProvenance.confidence must lie in [0.0, 1.0] when reported")
        release_refs = (
            self.release_set_id,
            self.bundle_id,
            self.deployment_receipt_id,
            self.runtime_config_digest,
            self.control_id,
            self.fence_claim_id,
        )
        has_release_evidence = any(release_refs) or self.deployment_sequence is not None
        if has_release_evidence and (
            self.deployment_sequence is None
            or self.deployment_sequence <= 0
            or not all(
            isinstance(value, str) and value.strip() for value in release_refs
            )
        ):
            raise ValueError("AiProvenance release binding must be complete or absent")


@dataclass(frozen=True, slots=True)
class ModelDraft:
    """A validated model output, and nothing more.

    This is intentionally *not* a business entity and cannot be turned into one
    here. It carries `output` (schema-validated data), `provenance` (why it says
    what it says) and a status that has exactly one legal value.

    A domain that wants to act on it must map it into its own aggregate through
    its own Named Action, with a human actor, producing an `AuditEvent` (R6).
    That mapping lives in the domain, not in this package — which is also why
    nothing under `backend/intelligence/` imports a domain repository.
    """

    output: dict[str, Any]
    provenance: AiProvenance
    status: DraftStatus = "DRAFT"

    @property
    def may_mutate_business_state(self) -> bool:
        """Always `False`, by construction rather than by convention.

        There is no setter and no backing field, so no instance of this class can
        report `True` — `dataclasses.replace` cannot reach it either. This is the
        type-level form of the AI Runtime isolation rule.
        """
        return False

    @property
    def requires_human_confirmation(self) -> bool:
        return True
