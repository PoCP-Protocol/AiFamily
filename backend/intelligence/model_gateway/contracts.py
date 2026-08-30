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


@dataclass(frozen=True, slots=True)
class TokenUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


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
