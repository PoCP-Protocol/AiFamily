"""Scoped, draft-only storage for Model Gateway provenance.

The gateway owns the canonical ``AiProvenance`` value object in ``contracts``.
This module is the narrow persistence seam for a generated ``ModelDraft``: it
keeps the exact tenant/family/subject scope and never promotes a draft into a
business fact.  The in-memory adapter is for synthetic/test composition roots;
the SQLAlchemy adapter is the durable seam consumed by API/workflow code.

The evidence-level ``Provenance`` in ``backend.packages.contracts.evidence`` is
a separate domain vocabulary and is deliberately not redefined here.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import sqlalchemy as sa
from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.model_gateway.contracts import (
    AiProvenance,
    ModelDraft,
    TokenUsage,
)


class ModelDraftRegistryError(ValueError):
    """Raised when a draft registry operation violates its safety contract."""


class ModelDraftNotFound(LookupError):
    """Raised when a reference is absent or outside the requested scope."""


class ModelDraftRegistryBase(DeclarativeBase):
    """SQLAlchemy metadata boundary owned by this AI-runtime seam."""


class ModelDraftRow(ModelDraftRegistryBase):
    """A persisted, draft-only result and its complete scope envelope."""

    __tablename__ = "ai_model_drafts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provenance_ref",
            name="uq_ai_model_drafts_tenant_provenance",
        ),
        sa.CheckConstraint("status = 'DRAFT'", name="ck_ai_model_drafts_draft_only"),
        sa.CheckConstraint(
            "may_mutate_business_state = false",
            name="ck_ai_model_drafts_cannot_mutate",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    draft_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    provenance_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    family_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    subject_person_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(96), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    provider_id: Mapped[str] = mapped_column(String(160), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    model_version: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(160), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(160), nullable=False)
    context_snapshot_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    use_case: Mapped[str] = mapped_column(String(160), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    data_class: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    output_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    provenance_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    may_mutate_business_state: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass(frozen=True, slots=True)
class ModelDraftScope:
    """The exact tenant/family/subject scope required for a draft."""

    tenant_id: str
    family_id: str
    subject_person_id: str
    purpose: str
    correlation_id: str

    def __post_init__(self) -> None:
        values = (
            self.tenant_id,
            self.family_id,
            self.subject_person_id,
            self.purpose,
            self.correlation_id,
        )
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ModelDraftRegistryError("MODEL_DRAFT_SCOPE_REQUIRED")


@dataclass(frozen=True, slots=True)
class StoredModelDraft:
    """A stored draft envelope without exposing a SQLAlchemy row."""

    draft_id: str
    provenance_ref: str
    scope: ModelDraftScope
    draft: ModelDraft
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ModelDraftIdentity:
    """Stable draft/provenance references derived from one runtime id."""

    draft_id: str
    provenance_ref: str

    @classmethod
    def from_run_id(cls, run_id: str) -> ModelDraftIdentity:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ModelDraftRegistryError("MODEL_DRAFT_RUN_ID_REQUIRED")
        value = run_id.strip()
        if len(value) > 128:
            raise ModelDraftRegistryError("MODEL_DRAFT_RUN_ID_TOO_LONG")
        return cls(draft_id=f"draft:{value}", provenance_ref=f"model-draft:{value}")


class ModelDraftRegistryPort(Protocol):
    """Application port for resolving drafts; implementations own storage."""

    async def save(
        self,
        *,
        draft_id: str,
        provenance_ref: str,
        scope: ModelDraftScope,
        draft: ModelDraft,
        created_at: datetime | None = None,
    ) -> StoredModelDraft: ...

    async def resolve(
        self,
        provenance_ref: str,
        *,
        tenant_id: str,
        family_id: str,
        subject_person_id: str,
        purpose: str,
        correlation_id: str,
    ) -> ModelDraft: ...

    async def resolve_stored(
        self,
        provenance_ref: str,
        *,
        tenant_id: str,
        family_id: str,
        subject_person_id: str,
        purpose: str,
        correlation_id: str,
    ) -> StoredModelDraft: ...


_DATA_CLASSES = frozenset(
    {"SYNTHETIC", "OPERATIONAL_TEXT", "FAMILY_PRIVATE_TEXT", "MINOR_PERSONAL_DATA"}
)
_FORBIDDEN_FACT_KEYS = frozenset(
    {"family_score", "family_rank", "ranking", "authoritative_fact", "canonical_state"}
)
_DRAFT_STATUS_KEYS = frozenset({"status", "draft_status"})


def _json_ready(value: object, *, path: str) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ModelDraftRegistryError(f"{path} mapping keys must be strings")
            result[key] = _json_ready(item, path=f"{path}.{key}")
        return result
    if isinstance(value, (list, tuple)):
        return [_json_ready(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ModelDraftRegistryError(f"{path} contains a non-JSON value")


def _json_object(value: object, *, path: str) -> dict[str, Any]:
    ready = _json_ready(value, path=path)
    if not isinstance(ready, dict):
        raise ModelDraftRegistryError(f"{path} must be a JSON object")
    try:
        encoded = json.dumps(ready, ensure_ascii=False, allow_nan=False, sort_keys=True)
        decoded = json.loads(encoded)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ModelDraftRegistryError(f"{path} is not valid JSON") from exc
    if not isinstance(decoded, dict):  # pragma: no cover
        raise ModelDraftRegistryError(f"{path} must be a JSON object")
    return decoded


def _assert_safe_output(value: object, *, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in _FORBIDDEN_FACT_KEYS:
                raise ModelDraftRegistryError(f"{path}.{key} cannot become a business fact")
            if isinstance(key, str) and key.lower() in _DRAFT_STATUS_KEYS and item != "DRAFT":
                raise ModelDraftRegistryError("MODEL_DRAFT_STATUS_MUST_REMAIN_DRAFT")
            _assert_safe_output(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_safe_output(item, path=f"{path}[{index}]")


def _utc(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ModelDraftRegistryError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelDraftRegistryError(f"{field_name} is required")
    return value


def _provenance_payload(provenance: AiProvenance) -> dict[str, Any]:
    token_usage = None
    if provenance.token_usage is not None:
        token_usage = {
            "prompt_tokens": provenance.token_usage.prompt_tokens,
            "completion_tokens": provenance.token_usage.completion_tokens,
            "total_tokens": provenance.token_usage.total_tokens,
        }
    return _json_object(
        {
            "provider_id": provenance.provider_id,
            "model": provenance.model,
            "model_version": provenance.model_version,
            "prompt_version": provenance.prompt_version,
            "schema_version": provenance.schema_version,
            "context_snapshot_ref": provenance.context_snapshot_ref,
            "latency_ms": provenance.latency_ms,
            "data_class": provenance.data_class,
            "use_case": provenance.use_case,
            "confidence": provenance.confidence,
            "token_usage": token_usage,
            "generated_at": _utc(provenance.generated_at, field_name="generated_at").isoformat(),
        },
        path="provenance_payload",
    )


def _provenance_from_payload(value: object) -> AiProvenance:
    payload = _json_object(value, path="provenance_payload")
    raw_token_usage = payload.get("token_usage")
    token_usage = None
    if raw_token_usage is not None:
        if not isinstance(raw_token_usage, Mapping):
            raise ModelDraftRegistryError("MODEL_DRAFT_PROVENANCE_SHAPE_INVALID")
        token_usage = TokenUsage(
            prompt_tokens=raw_token_usage.get("prompt_tokens"),
            completion_tokens=raw_token_usage.get("completion_tokens"),
            total_tokens=raw_token_usage.get("total_tokens"),
        )
    raw_generated_at = payload.get("generated_at")
    if not isinstance(raw_generated_at, str):
        raise ModelDraftRegistryError("MODEL_DRAFT_PROVENANCE_SHAPE_INVALID")
    try:
        generated_at = datetime.fromisoformat(raw_generated_at)
        data_class = payload.get("data_class")
        if data_class not in _DATA_CLASSES:
            raise ModelDraftRegistryError("MODEL_DRAFT_PROVENANCE_SHAPE_INVALID")
        return AiProvenance(
            provider_id=_text(payload.get("provider_id"), "provider_id"),
            model=_text(payload.get("model"), "model"),
            model_version=_text(payload.get("model_version"), "model_version"),
            prompt_version=_text(payload.get("prompt_version"), "prompt_version"),
            schema_version=_text(payload.get("schema_version"), "schema_version"),
            context_snapshot_ref=_text(payload.get("context_snapshot_ref"), "context_snapshot_ref"),
            latency_ms=payload.get("latency_ms"),
            data_class=data_class,  # type: ignore[arg-type]
            use_case=_text(payload.get("use_case"), "use_case"),
            confidence=payload.get("confidence"),
            token_usage=token_usage,
            generated_at=generated_at,
        )
    except ModelDraftRegistryError:
        raise
    except (TypeError, ValueError) as exc:
        raise ModelDraftRegistryError("MODEL_DRAFT_PROVENANCE_SHAPE_INVALID") from exc


def _stored_from_row(row: ModelDraftRow) -> StoredModelDraft:
    if row.status != "DRAFT" or row.may_mutate_business_state is not False:
        raise ModelDraftRegistryError("MODEL_DRAFT_PERSISTED_STATE_INVALID")
    try:
        provenance = _provenance_from_payload(row.provenance_payload)
        scalar_fields = (
            (row.provider_id, provenance.provider_id),
            (row.model, provenance.model),
            (row.model_version, provenance.model_version),
            (row.prompt_version, provenance.prompt_version),
            (row.schema_version, provenance.schema_version),
            (row.context_snapshot_ref, provenance.context_snapshot_ref),
            (row.use_case, provenance.use_case),
            (row.latency_ms, provenance.latency_ms),
            (row.data_class, provenance.data_class),
            (row.confidence, provenance.confidence),
        )
        if any(left != right for left, right in scalar_fields) or _utc(
            row.generated_at, field_name="generated_at"
        ) != _utc(provenance.generated_at, field_name="generated_at"):
            raise ModelDraftRegistryError("MODEL_DRAFT_PROVENANCE_SCALAR_MISMATCH")
        output = _json_object(row.output_payload, path="output_payload")
        _assert_safe_output(output, path="output_payload")
        return StoredModelDraft(
            draft_id=row.draft_id,
            provenance_ref=row.provenance_ref,
            scope=ModelDraftScope(
                tenant_id=row.tenant_id,
                family_id=row.family_id,
                subject_person_id=row.subject_person_id,
                purpose=row.purpose,
                correlation_id=row.correlation_id,
            ),
            draft=ModelDraft(output=output, provenance=provenance),
            created_at=_utc(row.created_at, field_name="created_at"),
        )
    except ModelDraftRegistryError:
        raise
    except (TypeError, ValueError) as exc:
        raise ModelDraftRegistryError("MODEL_DRAFT_PERSISTED_SHAPE_INVALID") from exc


def _same_record(left: StoredModelDraft, right: StoredModelDraft) -> bool:
    return (
        left.draft_id == right.draft_id
        and left.provenance_ref == right.provenance_ref
        and left.scope == right.scope
        and left.draft == right.draft
    )


def _validated_draft(draft: object) -> ModelDraft:
    if not isinstance(draft, ModelDraft):
        raise ModelDraftRegistryError("MODEL_DRAFT_REQUIRED")
    if draft.status != "DRAFT" or draft.may_mutate_business_state is not False:
        raise ModelDraftRegistryError("MODEL_DRAFT_MUST_REMAIN_DRAFT")
    output = _json_object(draft.output, path="output_payload")
    _assert_safe_output(output, path="output_payload")
    return ModelDraft(output=output, provenance=draft.provenance)


class InMemoryModelDraftRegistry:
    """Process-local registry for synthetic/test composition roots."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], StoredModelDraft] = {}

    async def save(
        self,
        *,
        draft_id: str,
        provenance_ref: str,
        scope: ModelDraftScope,
        draft: ModelDraft,
        created_at: datetime | None = None,
    ) -> StoredModelDraft:
        if not isinstance(scope, ModelDraftScope):
            raise ModelDraftRegistryError("MODEL_DRAFT_SCOPE_REQUIRED")
        draft_id = _text(draft_id, "draft_id")
        provenance_ref = _text(provenance_ref, "provenance_ref")
        incoming = StoredModelDraft(
            draft_id=draft_id,
            provenance_ref=provenance_ref,
            scope=scope,
            draft=_validated_draft(draft),
            created_at=_utc(created_at or datetime.now(UTC), field_name="created_at"),
        )
        key = (scope.tenant_id, draft_id)
        existing = self._records.get(key)
        if existing is not None:
            if not _same_record(existing, incoming):
                raise ModelDraftRegistryError("MODEL_DRAFT_REPLAY_MISMATCH")
            return existing
        if any(
            item.scope.tenant_id == scope.tenant_id and item.provenance_ref == provenance_ref
            for item in self._records.values()
        ):
            raise ModelDraftRegistryError("MODEL_DRAFT_PROVENANCE_REF_COLLISION")
        self._records[key] = incoming
        return incoming

    async def resolve(
        self,
        provenance_ref: str,
        *,
        tenant_id: str,
        family_id: str,
        subject_person_id: str,
        purpose: str,
        correlation_id: str,
    ) -> ModelDraft:
        return (
            await self.resolve_stored(
                provenance_ref,
                tenant_id=tenant_id,
                family_id=family_id,
                subject_person_id=subject_person_id,
                purpose=purpose,
                correlation_id=correlation_id,
            )
        ).draft

    async def resolve_stored(
        self,
        provenance_ref: str,
        *,
        tenant_id: str,
        family_id: str,
        subject_person_id: str,
        purpose: str,
        correlation_id: str,
    ) -> StoredModelDraft:
        scope = ModelDraftScope(
            tenant_id=tenant_id,
            family_id=family_id,
            subject_person_id=subject_person_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        provenance_ref = _text(provenance_ref, "provenance_ref")
        stored = next(
            (
                item
                for item in self._records.values()
                if item.scope.tenant_id == scope.tenant_id and item.provenance_ref == provenance_ref
            ),
            None,
        )
        if stored is None or stored.scope != scope:
            raise ModelDraftNotFound(provenance_ref)
        return stored


class SqlAlchemyModelDraftRegistry:
    """Async durable registry used by API and workflow consumers."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(
        self,
        *,
        draft_id: str,
        provenance_ref: str,
        scope: ModelDraftScope,
        draft: ModelDraft,
        created_at: datetime | None = None,
    ) -> StoredModelDraft:
        if not isinstance(scope, ModelDraftScope):
            raise ModelDraftRegistryError("MODEL_DRAFT_SCOPE_REQUIRED")
        draft_id = _text(draft_id, "draft_id")
        provenance_ref = _text(provenance_ref, "provenance_ref")
        normalised_draft = _validated_draft(draft)
        created = _utc(created_at or datetime.now(UTC), field_name="created_at")
        incoming = StoredModelDraft(
            draft_id=draft_id,
            provenance_ref=provenance_ref,
            scope=scope,
            draft=normalised_draft,
            created_at=created,
        )
        row = await self._session.get(
            ModelDraftRow,
            {"tenant_id": scope.tenant_id, "draft_id": draft_id},
        )
        if row is not None:
            existing = _stored_from_row(row)
            if not _same_record(existing, incoming):
                raise ModelDraftRegistryError("MODEL_DRAFT_REPLAY_MISMATCH")
            return existing
        existing_ref = await self._session.scalar(
            select(ModelDraftRow).where(
                ModelDraftRow.tenant_id == scope.tenant_id,
                ModelDraftRow.provenance_ref == provenance_ref,
            )
        )
        if existing_ref is not None:
            raise ModelDraftRegistryError("MODEL_DRAFT_PROVENANCE_REF_COLLISION")

        provenance = normalised_draft.provenance
        row = ModelDraftRow(
            tenant_id=scope.tenant_id,
            draft_id=draft_id,
            provenance_ref=provenance_ref,
            family_id=scope.family_id,
            subject_person_id=scope.subject_person_id,
            purpose=scope.purpose,
            correlation_id=scope.correlation_id,
            provider_id=provenance.provider_id,
            model=provenance.model,
            model_version=provenance.model_version,
            prompt_version=provenance.prompt_version,
            schema_version=provenance.schema_version,
            context_snapshot_ref=provenance.context_snapshot_ref,
            use_case=provenance.use_case,
            latency_ms=provenance.latency_ms,
            data_class=provenance.data_class,
            confidence=provenance.confidence,
            generated_at=_utc(provenance.generated_at, field_name="generated_at"),
            output_payload=normalised_draft.output,
            provenance_payload=_provenance_payload(provenance),
            status="DRAFT",
            may_mutate_business_state=False,
            created_at=created,
        )
        self._session.add(row)
        await self._session.flush()
        return _stored_from_row(row)

    async def resolve(
        self,
        provenance_ref: str,
        *,
        tenant_id: str,
        family_id: str,
        subject_person_id: str,
        purpose: str,
        correlation_id: str,
    ) -> ModelDraft:
        return (
            await self.resolve_stored(
                provenance_ref,
                tenant_id=tenant_id,
                family_id=family_id,
                subject_person_id=subject_person_id,
                purpose=purpose,
                correlation_id=correlation_id,
            )
        ).draft

    async def resolve_stored(
        self,
        provenance_ref: str,
        *,
        tenant_id: str,
        family_id: str,
        subject_person_id: str,
        purpose: str,
        correlation_id: str,
    ) -> StoredModelDraft:
        scope = ModelDraftScope(
            tenant_id=tenant_id,
            family_id=family_id,
            subject_person_id=subject_person_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        row = await self._session.scalar(
            select(ModelDraftRow).where(
                ModelDraftRow.tenant_id == scope.tenant_id,
                ModelDraftRow.provenance_ref == _text(provenance_ref, "provenance_ref"),
            )
        )
        if row is None:
            raise ModelDraftNotFound(provenance_ref)
        stored = _stored_from_row(row)
        if stored.scope != scope:
            raise ModelDraftNotFound(provenance_ref)
        return stored


__all__ = [
    "AiProvenance",
    "InMemoryModelDraftRegistry",
    "ModelDraftIdentity",
    "ModelDraftNotFound",
    "ModelDraftRegistryBase",
    "ModelDraftRegistryError",
    "ModelDraftRegistryPort",
    "ModelDraftRow",
    "ModelDraftScope",
    "SqlAlchemyModelDraftRegistry",
    "StoredModelDraft",
]
