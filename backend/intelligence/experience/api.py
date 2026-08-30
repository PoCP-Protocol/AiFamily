"""HTTP contract for the governed multimodal experience draft flow.

The router is mounted by the ``family_api`` composition root.  Its default
dependency still raises ``503`` until that root provides an authenticated,
consent-checked ``ContextScope`` and the context-bound application service.
This keeps the route visible in OpenAPI while preserving a fail-closed runtime
when production wiring is absent.

The request body contains only generation intent and already-authorized media
references.  Tenant/family/subject scope, purpose, consent, environment and
the expiring context snapshot are supplied by the injected runtime.  Provider
identifiers, SDK configuration and secrets are deliberately not part of the
transport contract; model invocation remains behind Model Gateway.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.intelligence.context_engine.contracts import ContextScope
from backend.intelligence.experience.multimodal_context_application import (
    ContextBoundMultimodalCommand,
    ContextBoundMultimodalDraft,
)
from backend.intelligence.experience.multimodal_routing import (
    MultimodalRouteError,
    MultimodalRouteRequest,
    RouteStrategy,
)
from backend.intelligence.model_gateway.contracts import MediaInput
from backend.intelligence.model_gateway.errors import ModelGatewayError

_MODALITY_VALUES = Literal["TEXT", "IMAGE", "AUDIO", "VIDEO"]
_MEDIA_TYPE_VALUES = Literal["IMAGE", "AUDIO", "VIDEO", "DOCUMENT"]
_OPAQUE_REF_RE = re.compile(
    r"^(?:media|asset|object|opaque|fixture):[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$",
    re.IGNORECASE,
)
_BARE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")
_INLINE_BASE64_RE = re.compile(r"^[A-Za-z0-9+/=_-]{128,}$")
_FORBIDDEN_CLIENT_KEYS = frozenset(
    {
        "tenant_id",
        "family_id",
        "subject_id",
        "subject_ids",
        "purpose",
        "consent",
        "consent_granted",
        "consent_version",
        "context_snapshot_ref",
        "environment",
        "provider",
        "provider_id",
        "provider_sdk",
        "api_key",
        "access_token",
        "secret",
    }
)


def _reject_forbidden_keys(value: object, *, path: str = "payload") -> None:
    """Reject scope/provider controls hidden inside an arbitrary payload.

    A payload is model input, not a configuration escape hatch.  Recursively
    rejecting reserved keys prevents a client from smuggling a provider or a
    forged snapshot through a nested object while leaving ordinary content
    values untouched.
    """

    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in _FORBIDDEN_CLIENT_KEYS:
                raise ValueError(f"{path}.{key} is controlled by the server")
            _reject_forbidden_keys(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_forbidden_keys(item, path=f"{path}[{index}]")


class MediaInputBody(BaseModel):
    """Reference to an authorized object; raw media bytes never cross this API."""

    model_config = ConfigDict(extra="forbid")

    media_type: _MEDIA_TYPE_VALUES
    uri: str = Field(min_length=1, max_length=2_048)
    mime_type: str = Field(min_length=1, max_length=128)
    sha256: str = Field(min_length=1, max_length=128)

    @field_validator("uri")
    @classmethod
    def validate_uri(cls, value: str) -> str:
        """Accept references only; never accept inline media or data URLs."""

        candidate = value.strip()
        lowered = candidate.lower()
        if not candidate:
            raise ValueError("media uri must not be blank")
        if lowered.startswith(("data:", "data%3a")):
            raise ValueError("media uri must be an authorized reference, not a data URL")
        if "base64" in lowered or _INLINE_BASE64_RE.fullmatch(candidate):
            raise ValueError("inline base64 media is not accepted")

        parsed = urlsplit(candidate)
        if parsed.scheme:
            if parsed.scheme.lower() == "https":
                if not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError("https media uri must contain a host without credentials")
                return candidate
            if _OPAQUE_REF_RE.fullmatch(candidate):
                return candidate
            raise ValueError("media uri must use https or an approved opaque reference")

        if len(candidate) > 256:
            raise ValueError("opaque media reference is too long for an inline value")
        if _BARE_REF_RE.fullmatch(candidate):
            return candidate
        raise ValueError("media uri must use https or an approved opaque reference")

    def to_domain(self) -> MediaInput:
        return MediaInput(
            media_type=self.media_type,
            uri=self.uri,
            mime_type=self.mime_type,
            sha256=self.sha256,
        )


class MultimodalDraftRequest(BaseModel):
    """Client-controlled generation intent for one context-bound draft.

    Scope, purpose, consent, environment and context snapshot are intentionally
    absent.  They are trusted runtime inputs, resolved by dependency injection.
    ``extra='forbid'`` makes accidental client-side scope/provider fields a
    visible contract error instead of silently ignoring them.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=128)
    prompt_version: str = Field(min_length=1, max_length=128)
    schema_version: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(min_length=1)
    modalities: tuple[_MODALITY_VALUES, ...] = Field(min_length=1, max_length=4)
    estimated_input_tokens: int = Field(gt=0, le=2_000_000)
    strategy: RouteStrategy = "balanced"
    max_latency_ms: int | None = Field(default=None, gt=0)
    max_cost_microusd: int | None = Field(default=None, ge=0)
    input_refs: tuple[str, ...] = Field(default=(), max_length=64)
    media_inputs: tuple[MediaInputBody, ...] = Field(default=(), max_length=8)
    session_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_payload_and_modalities(self) -> MultimodalDraftRequest:
        if len(set(self.modalities)) != len(self.modalities):
            raise ValueError("modalities must contain unique values")
        if any(not reference.strip() for reference in self.input_refs):
            raise ValueError("input_refs must contain non-empty references")
        if len(set(self.input_refs)) != len(self.input_refs):
            raise ValueError("input_refs must not contain duplicates")
        _reject_forbidden_keys(self.payload)
        _reject_forbidden_keys(self.output_schema, path="output_schema")
        return self


class DraftScopeResponse(BaseModel):
    """The server-resolved scope echoed for explainability and UI isolation."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    region_id: str
    family_id: str
    subject_ids: tuple[str, ...]
    purpose: str
    consent_version: str
    consent_granted: Literal[True]
    data_class: str
    locale: str


class DraftProvenanceResponse(BaseModel):
    """Safe model provenance; no prompt, media bytes or credentials."""

    model_config = ConfigDict(extra="forbid")

    provider_id: str
    model: str
    model_version: str
    prompt_version: str
    schema_version: str
    context_snapshot_ref: str
    latency_ms: int
    data_class: str
    use_case: str
    confidence: float | None
    generated_at: datetime


class DraftRouteResponse(BaseModel):
    """Explainable routing metadata returned after gateway admission."""

    model_config = ConfigDict(extra="forbid")

    provider_id: str
    vendor: str
    model: str
    model_version: str
    strategy: RouteStrategy
    estimated_latency_ms: int
    estimated_cost_microusd: int
    fallback_provider_ids: tuple[str, ...]


class MultimodalDraftResponse(BaseModel):
    """A draft-only response; it cannot be treated as a business fact."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: Literal["DRAFT"]
    output: dict[str, Any]
    requires_human_confirmation: Literal[True]
    scope: DraftScopeResponse
    context_snapshot_ref: str
    context_snapshot_expires_at: datetime
    provenance: DraftProvenanceResponse
    route: DraftRouteResponse


class MultimodalDraftApplication(Protocol):
    """Minimal application port used by the HTTP adapter.

    Implementations must create the context snapshot and call Model Gateway;
    this port deliberately exposes neither provider adapters nor credentials.
    """

    async def generate_draft(
        self, command: ContextBoundMultimodalCommand
    ) -> ContextBoundMultimodalDraft: ...


class MultimodalDraftRuntimeResolver(Protocol):
    """Resolve one request's trusted runtime from authenticated path scope.

    A production composition root implements this port with identity,
    authorization and consent checks.  The request body is never passed to the
    resolver, so clients cannot select another tenant, family or subject set.
    """

    async def resolve(self, family_id: str) -> MultimodalDraftRuntime: ...


@dataclass(frozen=True, slots=True)
class MultimodalDraftRuntime:
    """Trusted inputs resolved by the composition root, never by request JSON."""

    scope: ContextScope
    application: MultimodalDraftApplication
    environment: str

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ContextScope):
            raise TypeError("multimodal runtime requires an explicit ContextScope")
        self.scope.assert_active()
        if not self.environment.strip():
            raise ValueError("multimodal runtime environment is required")


def get_multimodal_draft_runtime() -> MultimodalDraftRuntime | None:
    """Optional static runtime override retained for tests/composition roots.

    Returning ``None`` lets a request-level resolver take precedence.  The
    endpoint itself returns 503 when neither this dependency nor a resolver is
    installed, preserving fail-closed behaviour without making FastAPI execute
    an unused dependency before it can resolve a family-specific runtime.
    """

    return None


def get_multimodal_draft_runtime_resolver() -> MultimodalDraftRuntimeResolver | None:
    """No identity/consent resolver is wired by default; endpoint returns 503."""

    return None


router = APIRouter(prefix="/families", tags=["experience"])


def _assert_family_scope(runtime: MultimodalDraftRuntime, family_id: str) -> None:
    if runtime.scope.family_id != family_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="family_access_denied")


async def _resolve_request_runtime(
    family_id: str,
    runtime: MultimodalDraftRuntime | None,
    resolver: MultimodalDraftRuntimeResolver | None,
) -> MultimodalDraftRuntime:
    """Choose server-provided runtime, rejecting missing/ambiguous wiring."""

    if runtime is not None and resolver is not None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="multimodal_experience_runtime_ambiguous",
        )
    if resolver is not None:
        try:
            resolved = await resolver.resolve(family_id)
        except HTTPException:
            raise
        except Exception as error:  # noqa: BLE001 — resolver boundary fails closed
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="multimodal_experience_runtime_unavailable",
            ) from error
        if not isinstance(resolved, MultimodalDraftRuntime):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="multimodal_experience_runtime_invalid",
            )
        return resolved
    if runtime is not None:
        return runtime
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="multimodal_experience_runtime_not_configured",
    )


def _to_response(result: ContextBoundMultimodalDraft) -> MultimodalDraftResponse:
    snapshot = result.snapshot
    routed = result.routed
    experience = routed.experience
    draft = experience.draft
    route = routed.route
    scope = snapshot.scope
    provenance = draft.provenance
    route_provenance = route.provenance_input
    return MultimodalDraftResponse(
        run_id=experience.run_id,
        status=draft.status,
        output=dict(draft.output),
        requires_human_confirmation=draft.requires_human_confirmation,
        scope=DraftScopeResponse(
            tenant_id=scope.tenant_id,
            region_id=scope.region_id,
            family_id=scope.family_id,
            subject_ids=scope.subject_ids,
            purpose=scope.purpose,
            consent_version=scope.consent_version,
            consent_granted=True,
            data_class=scope.data_class.value,
            locale=scope.effective_content_locale,
        ),
        context_snapshot_ref=snapshot.snapshot_ref,
        context_snapshot_expires_at=snapshot.expires_at,
        provenance=DraftProvenanceResponse(
            provider_id=provenance.provider_id,
            model=provenance.model,
            model_version=provenance.model_version,
            prompt_version=provenance.prompt_version,
            schema_version=provenance.schema_version,
            context_snapshot_ref=provenance.context_snapshot_ref,
            latency_ms=provenance.latency_ms,
            data_class=str(provenance.data_class),
            use_case=provenance.use_case,
            confidence=provenance.confidence,
            generated_at=provenance.generated_at,
        ),
        route=DraftRouteResponse(
            provider_id=route.selected.provider_id,
            vendor=route.selected.vendor,
            model=route.selected.model,
            model_version=route.selected.model_version,
            strategy=route_provenance.strategy,
            estimated_latency_ms=route.estimated_latency_ms,
            estimated_cost_microusd=route.estimated_cost_microusd,
            fallback_provider_ids=route.fallback_provider_ids,
        ),
    )


@router.post(
    "/{family_id}/experience/multimodal/drafts",
    response_model=MultimodalDraftResponse,
    status_code=status.HTTP_200_OK,
)
async def create_multimodal_draft(
    family_id: str,
    body: MultimodalDraftRequest,
    runtime: MultimodalDraftRuntime | None = Depends(get_multimodal_draft_runtime),
    resolver: MultimodalDraftRuntimeResolver | None = Depends(
        get_multimodal_draft_runtime_resolver
    ),
) -> MultimodalDraftResponse:
    """Generate one governed draft from a server-bound context snapshot."""

    runtime = await _resolve_request_runtime(family_id, runtime, resolver)
    _assert_family_scope(runtime, family_id)
    route_request = MultimodalRouteRequest(
        use_case=runtime.scope.purpose,
        data_class=runtime.scope.data_class.value,
        modalities=body.modalities,
        environment=runtime.environment,
        estimated_input_tokens=body.estimated_input_tokens,
        strategy=body.strategy,
        max_latency_ms=body.max_latency_ms,
        max_cost_microusd=body.max_cost_microusd,
    )
    try:
        command = ContextBoundMultimodalCommand(
            run_id=body.run_id,
            route_request=route_request,
            scope=runtime.scope,
            prompt_version=body.prompt_version,
            schema_version=body.schema_version,
            payload=dict(body.payload),
            output_schema=dict(body.output_schema),
            input_refs=body.input_refs,
            media_inputs=tuple(item.to_domain() for item in body.media_inputs),
            session_id=body.session_id,
        )
        result = await runtime.application.generate_draft(command)
    except MultimodalRouteError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=error.reason
        ) from error
    except ModelGatewayError as error:
        # Never expose provider text or request payloads through HTTP.  The
        # gateway's closed failure taxonomy is the only stable detail allowed
        # across this boundary; retryability is represented by the status.
        error_status = (
            status.HTTP_504_GATEWAY_TIMEOUT
            if error.kind == "TIMEOUT"
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        raise HTTPException(status_code=error_status, detail=error.kind) from error
    except (ValueError, TypeError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    return _to_response(result)


__all__ = [
    "DraftProvenanceResponse",
    "DraftRouteResponse",
    "DraftScopeResponse",
    "MediaInputBody",
    "MultimodalDraftApplication",
    "MultimodalDraftRequest",
    "MultimodalDraftResponse",
    "MultimodalDraftRuntime",
    "MultimodalDraftRuntimeResolver",
    "create_multimodal_draft",
    "get_multimodal_draft_runtime",
    "get_multimodal_draft_runtime_resolver",
    "router",
]
