"""Server-owned authorization boundary for multimodal object references.

Clients may name an opaque object reference and declare expected integrity
metadata, but only the server-side metadata port establishes ownership,
existence, purpose, MIME type, size, digest and deletion state.  The returned
``MediaInput`` is therefore safe to pass into the existing Model Gateway; this
module is not another model runtime.

Deletion is adapted into the canonical durable deletion worker as its MEDIA
projection.  The adapter completes only after object bytes, metadata, input
snapshots, derived artifacts, indexes and provider-side adapters each return a
correlated receipt.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from backend.intelligence.context_engine.deletion import SubjectDeletionCommand
from backend.intelligence.context_engine.durable_deletion import (
    ProjectionDeletionReceipt,
    ProjectionKind,
)
from backend.intelligence.model_gateway.contracts import MediaInput


class MediaInputBoundaryError(ValueError):
    """A media reference cannot cross into Model Gateway."""


class MediaObjectState(StrEnum):
    ACTIVE = "ACTIVE"
    DELETION_PENDING = "DELETION_PENDING"
    DELETED = "DELETED"


@dataclass(frozen=True, slots=True)
class MediaObjectMetadata:
    object_ref: str
    tenant_id: str
    family_id: str
    purpose: str
    mime_type: str
    sha256: str
    size_bytes: int
    exists: bool
    state: MediaObjectState = MediaObjectState.ACTIVE

    def __post_init__(self) -> None:
        required = (
            self.object_ref,
            self.tenant_id,
            self.family_id,
            self.purpose,
            self.mime_type,
            self.sha256,
        )
        if any(not isinstance(value, str) or not value.strip() for value in required):
            raise MediaInputBoundaryError("MEDIA_OBJECT_METADATA_REQUIRED")
        if self.size_bytes < 0:
            raise MediaInputBoundaryError("MEDIA_OBJECT_SIZE_INVALID")
        if not isinstance(self.exists, bool):
            raise MediaInputBoundaryError("MEDIA_OBJECT_EXISTENCE_INVALID")
        try:
            object.__setattr__(self, "state", MediaObjectState(self.state))
        except ValueError as exc:
            raise MediaInputBoundaryError("MEDIA_OBJECT_STATE_INVALID") from exc


class MediaObjectMetadataPort(Protocol):
    """Durable, server-side metadata authority; never backed by request JSON."""

    def resolve(self, object_ref: str) -> MediaObjectMetadata: ...


@dataclass(frozen=True, slots=True)
class MediaObjectClaim:
    object_ref: str
    media_type: str
    mime_type: str
    sha256: str


class GovernedMediaInputAuthorizer:
    """Turn verified opaque references into provider-neutral ``MediaInput``."""

    _OBJECT_REF = re.compile(r"^object:[A-Za-z0-9][A-Za-z0-9._:/-]{0,248}$")
    _SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
    _ALLOWED_IMAGE_MIME = frozenset(
        {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
    )

    def __init__(
        self,
        metadata: MediaObjectMetadataPort,
        *,
        maximum_items: int = 8,
        maximum_item_bytes: int = 10 * 1024 * 1024,
        maximum_total_bytes: int = 25 * 1024 * 1024,
    ) -> None:
        if not callable(getattr(metadata, "resolve", None)):
            raise TypeError("metadata must implement MediaObjectMetadataPort")
        if minimum := min(maximum_items, maximum_item_bytes, maximum_total_bytes):
            if minimum < 0:  # pragma: no cover - keeps the validation expression total
                raise ValueError("media limits must be positive")
        else:
            raise ValueError("media limits must be positive")
        self._metadata = metadata
        self._maximum_items = maximum_items
        self._maximum_item_bytes = maximum_item_bytes
        self._maximum_total_bytes = maximum_total_bytes

    def authorize(
        self,
        claims: Iterable[MediaObjectClaim],
        *,
        tenant_id: str,
        family_id: str,
        purpose: str,
    ) -> tuple[MediaInput, ...]:
        items = tuple(claims)
        if not items or len(items) > self._maximum_items:
            raise MediaInputBoundaryError("MEDIA_ITEM_COUNT_INVALID")
        authorized: list[MediaInput] = []
        total_bytes = 0
        for claim in items:
            if not isinstance(claim, MediaObjectClaim):
                raise MediaInputBoundaryError("MEDIA_OBJECT_CLAIM_REQUIRED")
            if not self._OBJECT_REF.fullmatch(claim.object_ref):
                raise MediaInputBoundaryError("MEDIA_OBJECT_REF_INVALID")
            if claim.media_type != "IMAGE":
                raise MediaInputBoundaryError("MEDIA_TYPE_UNSUPPORTED")
            if claim.mime_type.lower() not in self._ALLOWED_IMAGE_MIME:
                raise MediaInputBoundaryError("MEDIA_MIME_UNSUPPORTED")
            if not self._SHA256.fullmatch(claim.sha256):
                raise MediaInputBoundaryError("MEDIA_SHA256_INVALID")

            metadata = self._metadata.resolve(claim.object_ref)
            if metadata.object_ref != claim.object_ref or not metadata.exists:
                raise MediaInputBoundaryError("MEDIA_OBJECT_NOT_FOUND")
            if metadata.state is not MediaObjectState.ACTIVE:
                raise MediaInputBoundaryError("MEDIA_OBJECT_DELETED_OR_PENDING")
            if (
                metadata.tenant_id != tenant_id
                or metadata.family_id != family_id
                or metadata.purpose != purpose
            ):
                raise MediaInputBoundaryError("MEDIA_OBJECT_SCOPE_MISMATCH")
            if metadata.mime_type.lower() != claim.mime_type.lower():
                raise MediaInputBoundaryError("MEDIA_MIME_MISMATCH")
            if metadata.sha256.lower() != claim.sha256.lower():
                raise MediaInputBoundaryError("MEDIA_SHA256_MISMATCH")
            if metadata.size_bytes > self._maximum_item_bytes:
                raise MediaInputBoundaryError("MEDIA_ITEM_TOO_LARGE")
            total_bytes += metadata.size_bytes
            if total_bytes > self._maximum_total_bytes:
                raise MediaInputBoundaryError("MEDIA_TOTAL_TOO_LARGE")
            authorized.append(
                MediaInput(
                    media_type="IMAGE",
                    uri=metadata.object_ref,
                    mime_type=metadata.mime_type.lower(),
                    sha256=metadata.sha256.lower(),
                )
            )
        return tuple(authorized)


class MediaDeletionLayer(StrEnum):
    OBJECT = "OBJECT"
    METADATA = "METADATA"
    INPUT_SNAPSHOT = "INPUT_SNAPSHOT"
    DERIVED = "DERIVED"
    INDEX = "INDEX"
    PROVIDER_ADAPTER = "PROVIDER_ADAPTER"


REQUIRED_MEDIA_DELETION_LAYERS = frozenset(MediaDeletionLayer)


@dataclass(frozen=True, slots=True)
class MediaLayerDeletionReceipt:
    layer: MediaDeletionLayer
    tenant_id: str
    subject_id: str
    command_id: str
    correlation_id: str
    causation_id: str
    deleted_count: int
    confirmed: bool
    audit_ref: str
    provenance_ref: str
    deletion_receipt_ref: str


class MediaDeletionLayerPort(Protocol):
    layer: MediaDeletionLayer

    def delete_subject(self, command: SubjectDeletionCommand) -> MediaLayerDeletionReceipt: ...


class GovernedMediaProjectionDeletionAdapter:
    """MEDIA adapter for the existing durable deletion worker."""

    projection = ProjectionKind.MEDIA

    def __init__(self, layers: Iterable[MediaDeletionLayerPort]) -> None:
        by_layer: dict[MediaDeletionLayer, MediaDeletionLayerPort] = {}
        for port in layers:
            try:
                layer = MediaDeletionLayer(port.layer)
            except (AttributeError, ValueError) as exc:
                raise MediaInputBoundaryError("MEDIA_DELETION_LAYER_INVALID") from exc
            if layer in by_layer:
                raise MediaInputBoundaryError("MEDIA_DELETION_LAYER_DUPLICATED")
            by_layer[layer] = port
        if set(by_layer) != REQUIRED_MEDIA_DELETION_LAYERS:
            raise MediaInputBoundaryError("MEDIA_DELETION_LAYERS_MISSING")
        self._layers = tuple(by_layer[layer] for layer in MediaDeletionLayer)

    def delete_subject(self, command: SubjectDeletionCommand) -> ProjectionDeletionReceipt:
        receipts = tuple(port.delete_subject(command) for port in self._layers)
        for receipt in receipts:
            if (
                not isinstance(receipt, MediaLayerDeletionReceipt)
                or receipt.tenant_id != command.tenant_id
                or receipt.subject_id != command.subject_id
                or receipt.command_id != command.command_id
                or receipt.correlation_id != command.correlation_id
                or receipt.causation_id != command.causation_id
                or not receipt.confirmed
                or not receipt.audit_ref
                or not receipt.provenance_ref
                or not receipt.deletion_receipt_ref
            ):
                raise MediaInputBoundaryError("MEDIA_DELETION_RECEIPT_INVALID")
        material = "|".join(
            [command.command_id, *(receipt.deletion_receipt_ref for receipt in receipts)]
        )
        return ProjectionDeletionReceipt(
            receipt_id="media:" + hashlib.sha256(material.encode()).hexdigest(),
            projection=ProjectionKind.MEDIA,
            tenant_id=command.tenant_id,
            subject_id=command.subject_id,
            command_id=command.command_id,
            correlation_id=command.correlation_id,
            causation_id=command.causation_id,
            deleted_count=sum(receipt.deleted_count for receipt in receipts),
            confirmed=True,
            completed_at=datetime.now(UTC),
        )


__all__ = [
    "GovernedMediaInputAuthorizer",
    "GovernedMediaProjectionDeletionAdapter",
    "MediaDeletionLayer",
    "MediaDeletionLayerPort",
    "MediaInputBoundaryError",
    "MediaLayerDeletionReceipt",
    "MediaObjectClaim",
    "MediaObjectMetadata",
    "MediaObjectMetadataPort",
    "MediaObjectState",
    "REQUIRED_MEDIA_DELETION_LAYERS",
]
