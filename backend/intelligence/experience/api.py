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

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.intelligence.context_engine.contracts import ContextScope
from backend.intelligence.experience.async_ledger_bridge import (
    AsyncExperienceRunLedgerPort,
    dispatch_ledger_call,
)
from backend.intelligence.experience.multimodal_context_application import (
    ContextBoundMultimodalCommand,
    ContextBoundMultimodalDraft,
)
from backend.intelligence.experience.multimodal_routing import (
    MultimodalRouteError,
    MultimodalRouteRequest,
    RouteStrategy,
)
from backend.intelligence.experience.run_http import (
    DraftPreflight,
    ExperienceRunLedger,
    InteractionReceipt,
    InteractionType,
    RunHttpConflictError,
    RunHttpError,
    RunReplaySnapshot,
    RunScope,
    fingerprint_request,
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


class RunDecisionRequest(BaseModel):
    """Human decision over a DRAFT; it never carries provider controls."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["confirm", "rewrite", "reject"]
    draft_version: str | None = Field(default=None, min_length=1, max_length=128)
    replacement_text: str | None = Field(default=None, min_length=1, max_length=8_000)
    reason: str | None = Field(default=None, min_length=1, max_length=2_000)


class RunFeedbackRequest(BaseModel):
    """User feedback associated with a run and optional real event refs."""

    model_config = ConfigDict(extra="forbid")

    signal: Literal["helpful", "not_helpful", "request_human"]
    reason: str | None = Field(default=None, min_length=1, max_length=2_000)
    draft_version: str | None = Field(default=None, min_length=1, max_length=128)
    attempt_id: str | None = Field(default=None, min_length=1, max_length=128)
    candidate_id: str | None = Field(default=None, min_length=1, max_length=160)
    model_version: str | None = Field(default=None, min_length=1, max_length=160)
    benchmark_report_ref: str | None = Field(default=None, min_length=1, max_length=256)
    real_event_refs: tuple[str, ...] = Field(default=(), max_length=64)


class RunHumanReviewRequest(BaseModel):
    """Explicit escalation request; the server creates a review entry."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=2_000)
    impact_scope: str | None = Field(default=None, min_length=1, max_length=512)


class RunDeleteRequest(BaseModel):
    """Deletion reason without accepting media bytes or scope overrides."""

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, min_length=1, max_length=2_000)


class RunInteractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: str
    interaction_ref: str
    idempotency_replayed: bool


class RunReplayEntryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    interaction_type: str
    sequence: int
    payload: dict[str, Any]
    occurred_at: datetime


class RunReplayResponse(BaseModel):
    """Read-only ledger projection; no provider invocation is possible."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: Literal["DRAFT"]
    state: str
    event_sequence: int
    deletion_state: Literal["active", "deleted"]
    draft_payload: dict[str, Any] | None
    artifact_refs: tuple[str, ...]
    entries: tuple[RunReplayEntryResponse, ...]


class MultimodalDraftResponse(BaseModel):
    """A draft-only response; it cannot be treated as a business fact.

    ``draft_id`` and ``provenance_ref`` are server-generated when the
    composition root installs a registry.  A ``null`` pair honestly signals a
    contract-only runtime; such a response cannot be submitted to FGCN as a
    durable provenance record.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    draft_id: str | None
    provenance_ref: str | None
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
    run_ledger: ExperienceRunLedger | AsyncExperienceRunLedgerPort | None = None

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


def _run_scope(runtime: MultimodalDraftRuntime) -> RunScope:
    return RunScope(
        tenant_id=runtime.scope.tenant_id,
        family_id=runtime.scope.family_id,
        subject_ids=runtime.scope.subject_ids,
    )


def _require_run_ledger(
    runtime: MultimodalDraftRuntime,
) -> ExperienceRunLedger | AsyncExperienceRunLedgerPort:
    if runtime.run_ledger is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="experience_run_runtime_not_configured",
        )
    return runtime.run_ledger


def _require_idempotency_key(value: str | None) -> str:
    if value is None or not value.strip() or len(value) > 256:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Idempotency-Key header is required",
        )
    return value.strip()


def _map_run_error(error: RunHttpError) -> HTTPException:
    if error.code == "RUN_NOT_FOUND":
        code = status.HTTP_404_NOT_FOUND
    elif error.code in {"RUN_SCOPE_MISMATCH", "SCOPE_REQUIRED", "SUBJECT_SCOPE_REQUIRED"}:
        code = status.HTTP_403_FORBIDDEN
    elif error.code == "RUN_DELETED":
        code = status.HTTP_410_GONE
    elif isinstance(error, RunHttpConflictError):
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    return HTTPException(status_code=code, detail=error.code)


def _interaction_response(receipt: InteractionReceipt) -> RunInteractionResponse:
    return RunInteractionResponse(
        run_id=receipt.run_id,
        status=receipt.status,
        interaction_ref=receipt.interaction.event_id,
        idempotency_replayed=receipt.idempotency_replayed,
    )


def _draft_request_fingerprint(
    *, runtime: MultimodalDraftRuntime, body: MultimodalDraftRequest
) -> str:
    """Digest generation intent without including secrets or raw media bytes."""

    return fingerprint_request(
        {
            "run_id": body.run_id,
            "prompt_version": body.prompt_version,
            "schema_version": body.schema_version,
            "payload": body.payload,
            "output_schema": body.output_schema,
            "modalities": body.modalities,
            "estimated_input_tokens": body.estimated_input_tokens,
            "strategy": body.strategy,
            "max_latency_ms": body.max_latency_ms,
            "max_cost_microusd": body.max_cost_microusd,
            "input_refs": body.input_refs,
            "media_inputs": tuple(
                {
                    "media_type": item.media_type,
                    "mime_type": item.mime_type,
                    "sha256": item.sha256,
                }
                for item in body.media_inputs
            ),
            "session_id": body.session_id,
            "environment": runtime.environment,
            "purpose": runtime.scope.purpose,
            "data_class": runtime.scope.data_class.value,
        }
    )


async def _release_draft_preflight(
    ledger: ExperienceRunLedger | AsyncExperienceRunLedgerPort | None,
    reservation: DraftPreflight | None,
) -> None:
    if ledger is None or reservation is None:
        return
    try:
        await dispatch_ledger_call(ledger, "release_create", reservation=reservation)
    except RunHttpError:
        # Preserve the original provider/validation failure.  A durable
        # implementation must make release idempotent and transaction-safe.
        return


def _replay_response(snapshot: RunReplaySnapshot) -> RunReplayResponse:
    return RunReplayResponse(
        run_id=snapshot.run_id,
        status=snapshot.status,
        state=snapshot.state.value,
        event_sequence=snapshot.event_sequence,
        deletion_state=snapshot.deletion_state,
        draft_payload=(
            dict(snapshot.draft_payload) if snapshot.draft_payload is not None else None
        ),
        artifact_refs=snapshot.artifact_refs,
        entries=tuple(
            RunReplayEntryResponse(
                event_id=entry.event_id,
                interaction_type=entry.interaction_type.value,
                sequence=entry.sequence,
                payload=dict(entry.payload),
                occurred_at=entry.occurred_at,
            )
            for entry in snapshot.entries
        ),
    )


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
        except PermissionError as error:
            # Scope resolution deliberately distinguishes authentication from
            # authorization/consent.  Do not collapse a missing principal into
            # a family denial: callers need a stable 401 to initiate login,
            # while an authenticated but out-of-scope or revoked request stays
            # a non-disclosing 403.
            if error.args and error.args[0] == "AUTHENTICATED_PRINCIPAL_UNAVAILABLE":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="authentication_required",
                    headers={"WWW-Authenticate": "Bearer"},
                ) from error
            if error.args and error.args[0] == "CONSENT_REQUIRED":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="CONSENT_REQUIRED",
                ) from error
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="family_access_denied",
            ) from error
        except Exception as error:  # noqa: BLE001 — resolver boundary fails closed
            # Missing configuration and infrastructure failures remain a
            # fail-closed 503; do not expose resolver internals to clients.
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
        # Registry-backed runtimes may expose durable draft identity. Keep
        # the HTTP contract honest for legacy/test runtimes without it.
        draft_id=getattr(experience, "draft_id", None),
        provenance_ref=getattr(experience, "provenance_ref", None),
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
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
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
    ledger = runtime.run_ledger
    reservation: DraftPreflight | None = None
    create_idempotency_key: str | None = None
    if ledger is not None:
        if not all(
            callable(getattr(ledger, method_name, None))
            for method_name in ("preflight_create", "finalize_create", "release_create")
        ):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="experience_run_preflight_not_configured",
            )
        create_idempotency_key = _require_idempotency_key(idempotency_key or body.run_id)
        try:
            reservation = await dispatch_ledger_call(
                ledger,
                "preflight_create",
                scope=_run_scope(runtime),
                run_id=body.run_id,
                request_ref=body.run_id,
                request_fingerprint=_draft_request_fingerprint(runtime=runtime, body=body),
                idempotency_key=create_idempotency_key,
            )
        except RunHttpError as error:
            raise _map_run_error(error) from error
        if reservation.status == "replay":
            if (
                reservation.snapshot is not None
                and reservation.snapshot.deletion_state == "deleted"
            ):
                raise _map_run_error(RunHttpError("RUN_DELETED"))
            if reservation.response_payload is None:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="DRAFT_REPLAY_RESPONSE_UNAVAILABLE",
                )
            try:
                return MultimodalDraftResponse.model_validate(dict(reservation.response_payload))
            except (TypeError, ValueError) as error:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="DRAFT_REPLAY_RESPONSE_INVALID",
                ) from error
        if reservation.status != "reserved":
            raise _map_run_error(RunHttpConflictError("DRAFT_CREATE_IN_PROGRESS"))
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
        await _release_draft_preflight(ledger, reservation)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=error.reason
        ) from error
    except ModelGatewayError as error:
        await _release_draft_preflight(ledger, reservation)
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
        await _release_draft_preflight(ledger, reservation)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    try:
        response = _to_response(result)
    except (TypeError, ValueError) as error:
        await _release_draft_preflight(ledger, reservation)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="DRAFT_RESPONSE_INVALID",
        ) from error
    if ledger is not None and reservation is not None and create_idempotency_key is not None:
        try:
            await dispatch_ledger_call(
                ledger,
                "finalize_create",
                reservation=reservation,
                draft_payload=result.output,
                artifact_refs=tuple(
                    f"media:sha256:{item.sha256}" for item in body.media_inputs
                ),
                response_payload=response.model_dump(mode="json"),
            )
        except RunHttpError as error:
            raise _map_run_error(error) from error
    return response


async def _runtime_for_run(
    family_id: str,
    runtime: MultimodalDraftRuntime | None,
    resolver: MultimodalDraftRuntimeResolver | None,
) -> MultimodalDraftRuntime:
    resolved = await _resolve_request_runtime(family_id, runtime, resolver)
    _assert_family_scope(resolved, family_id)
    return resolved


@router.post(
    "/{family_id}/experience/multimodal/runs/{run_id}/decisions",
    response_model=RunInteractionResponse,
    status_code=status.HTTP_200_OK,
)
async def decide_multimodal_run(
    family_id: str,
    run_id: str,
    body: RunDecisionRequest,
    runtime: MultimodalDraftRuntime | None = Depends(get_multimodal_draft_runtime),
    resolver: MultimodalDraftRuntimeResolver | None = Depends(
        get_multimodal_draft_runtime_resolver
    ),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> RunInteractionResponse:
    """Record a human decision without promoting a draft into domain facts."""

    resolved = await _runtime_for_run(family_id, runtime, resolver)
    ledger = _require_run_ledger(resolved)
    decision = {"confirm": "accepted", "rewrite": "rewrite", "reject": "rejected"}[
        body.decision
    ]
    payload: dict[str, Any] = {"decision": decision}
    if body.draft_version is not None:
        payload["draft_version"] = body.draft_version
    if body.replacement_text is not None:
        payload["replacement_text"] = body.replacement_text
    if body.reason is not None:
        payload["reason"] = body.reason
    try:
        receipt = await dispatch_ledger_call(
            ledger,
            "append_interaction",
            scope=_run_scope(resolved),
            run_id=run_id,
            interaction_type=InteractionType.DECISION,
            payload=payload,
            idempotency_key=_require_idempotency_key(idempotency_key),
        )
    except RunHttpError as error:
        raise _map_run_error(error) from error
    return _interaction_response(receipt)


@router.post(
    "/{family_id}/experience/multimodal/runs/{run_id}/feedback",
    response_model=RunInteractionResponse,
    status_code=status.HTTP_200_OK,
)
async def record_multimodal_feedback(
    family_id: str,
    run_id: str,
    body: RunFeedbackRequest,
    runtime: MultimodalDraftRuntime | None = Depends(get_multimodal_draft_runtime),
    resolver: MultimodalDraftRuntimeResolver | None = Depends(
        get_multimodal_draft_runtime_resolver
    ),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> RunInteractionResponse:
    """Record feedback as an append-only run interaction."""

    resolved = await _runtime_for_run(family_id, runtime, resolver)
    ledger = _require_run_ledger(resolved)
    payload: dict[str, Any] = {"signal": body.signal}
    for field_name in (
        "reason",
        "draft_version",
        "attempt_id",
        "candidate_id",
        "model_version",
        "benchmark_report_ref",
    ):
        value = getattr(body, field_name)
        if value is not None:
            payload[field_name] = value
    if body.real_event_refs:
        payload["real_event_refs"] = list(body.real_event_refs)
    try:
        receipt = await dispatch_ledger_call(
            ledger,
            "append_interaction",
            scope=_run_scope(resolved),
            run_id=run_id,
            interaction_type=InteractionType.FEEDBACK,
            payload=payload,
            idempotency_key=_require_idempotency_key(idempotency_key),
        )
    except RunHttpError as error:
        raise _map_run_error(error) from error
    return _interaction_response(receipt)


@router.post(
    "/{family_id}/experience/multimodal/runs/{run_id}/human-review",
    response_model=RunInteractionResponse,
    status_code=status.HTTP_200_OK,
)
async def request_multimodal_human_review(
    family_id: str,
    run_id: str,
    body: RunHumanReviewRequest,
    runtime: MultimodalDraftRuntime | None = Depends(get_multimodal_draft_runtime),
    resolver: MultimodalDraftRuntimeResolver | None = Depends(
        get_multimodal_draft_runtime_resolver
    ),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> RunInteractionResponse:
    """Escalate one run to a human reviewer without an AI decision."""

    resolved = await _runtime_for_run(family_id, runtime, resolver)
    ledger = _require_run_ledger(resolved)
    payload: dict[str, Any] = {"reason": body.reason, "status": "human_review"}
    if body.impact_scope is not None:
        payload["impact_scope"] = body.impact_scope
    try:
        receipt = await dispatch_ledger_call(
            ledger,
            "append_interaction",
            scope=_run_scope(resolved),
            run_id=run_id,
            interaction_type=InteractionType.HUMAN_REVIEW,
            payload=payload,
            idempotency_key=_require_idempotency_key(idempotency_key),
        )
    except RunHttpError as error:
        raise _map_run_error(error) from error
    return _interaction_response(receipt)


@router.delete(
    "/{family_id}/experience/multimodal/runs/{run_id}",
    response_model=RunInteractionResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_multimodal_run(
    family_id: str,
    run_id: str,
    body: RunDeleteRequest | None = None,
    runtime: MultimodalDraftRuntime | None = Depends(get_multimodal_draft_runtime),
    resolver: MultimodalDraftRuntimeResolver | None = Depends(
        get_multimodal_draft_runtime_resolver
    ),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> RunInteractionResponse:
    """Record a deletion request and scrub draft/artifact replay material."""

    resolved = await _runtime_for_run(family_id, runtime, resolver)
    ledger = _require_run_ledger(resolved)
    payload: dict[str, Any] = {
        "deletion_ref": f"delete:{resolved.scope.tenant_id}:{family_id}:{run_id}",
        "status": "deleted",
    }
    if body is not None and body.reason is not None:
        payload["reason"] = body.reason
    try:
        receipt = await dispatch_ledger_call(
            ledger,
            "append_interaction",
            scope=_run_scope(resolved),
            run_id=run_id,
            interaction_type=InteractionType.DELETE,
            payload=payload,
            idempotency_key=_require_idempotency_key(idempotency_key),
        )
    except RunHttpError as error:
        raise _map_run_error(error) from error
    return _interaction_response(receipt)


@router.get(
    "/{family_id}/experience/multimodal/runs/{run_id}/replay",
    response_model=RunReplayResponse,
    status_code=status.HTTP_200_OK,
)
async def replay_multimodal_run(
    family_id: str,
    run_id: str,
    runtime: MultimodalDraftRuntime | None = Depends(get_multimodal_draft_runtime),
    resolver: MultimodalDraftRuntimeResolver | None = Depends(
        get_multimodal_draft_runtime_resolver
    ),
) -> RunReplayResponse:
    """Return an immutable run projection; this endpoint never calls Gateway."""

    resolved = await _runtime_for_run(family_id, runtime, resolver)
    ledger = _require_run_ledger(resolved)
    try:
        snapshot = await dispatch_ledger_call(
            ledger, "replay", scope=_run_scope(resolved), run_id=run_id
        )
    except RunHttpError as error:
        raise _map_run_error(error) from error
    return _replay_response(snapshot)


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
    "RunDecisionRequest",
    "RunDeleteRequest",
    "RunFeedbackRequest",
    "RunHumanReviewRequest",
    "RunInteractionResponse",
    "RunReplayEntryResponse",
    "RunReplayResponse",
    "create_multimodal_draft",
    "decide_multimodal_run",
    "get_multimodal_draft_runtime",
    "get_multimodal_draft_runtime_resolver",
    "delete_multimodal_run",
    "record_multimodal_feedback",
    "replay_multimodal_run",
    "request_multimodal_human_review",
    "router",
]
