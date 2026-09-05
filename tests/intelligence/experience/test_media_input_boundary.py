from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from backend.intelligence.context_engine.deletion import SubjectDeletionCommand
from backend.intelligence.experience.media_input_boundary import (
    GovernedMediaInputAuthorizer,
    GovernedMediaProjectionDeletionAdapter,
    MediaDeletionLayer,
    MediaInputBoundaryError,
    MediaLayerDeletionReceipt,
    MediaObjectClaim,
    MediaObjectMetadata,
    MediaObjectState,
)

SHA = "a" * 64


class MetadataStore:
    def __init__(self, metadata: MediaObjectMetadata) -> None:
        self.metadata = metadata

    def resolve(self, object_ref: str) -> MediaObjectMetadata:
        if object_ref != self.metadata.object_ref:
            raise MediaInputBoundaryError("MEDIA_OBJECT_NOT_FOUND")
        return self.metadata


def _metadata(**changes: object) -> MediaObjectMetadata:
    values: dict[str, object] = {
        "object_ref": "object:tenant-a/family-a/image-1",
        "tenant_id": "tenant-a",
        "family_id": "family-a",
        "purpose": "growth_support",
        "mime_type": "image/png",
        "sha256": SHA,
        "size_bytes": 1024,
        "exists": True,
    }
    values.update(changes)
    return MediaObjectMetadata(**values)  # type: ignore[arg-type]


def _claim(**changes: object) -> MediaObjectClaim:
    values = {
        "object_ref": "object:tenant-a/family-a/image-1",
        "media_type": "IMAGE",
        "mime_type": "image/png",
        "sha256": SHA,
    }
    values.update(changes)
    return MediaObjectClaim(**values)  # type: ignore[arg-type]


def _authorize(store: MetadataStore, *claims: MediaObjectClaim):  # type: ignore[no-untyped-def]
    return GovernedMediaInputAuthorizer(store).authorize(
        claims,
        tenant_id="tenant-a",
        family_id="family-a",
        purpose="growth_support",
    )


def test_server_metadata_authorizes_only_matching_object_reference() -> None:
    authorized = _authorize(MetadataStore(_metadata()), _claim())

    assert len(authorized) == 1
    assert authorized[0].uri == "object:tenant-a/family-a/image-1"
    assert authorized[0].sha256 == SHA


@pytest.mark.parametrize(
    "object_ref",
    [
        "data:image/png;base64,AAAA",
        "file:///tmp/child.png",
        "https://example.invalid/child.png",
        "AAAA" * 40,
    ],
)
def test_inline_file_web_and_non_object_references_are_rejected(object_ref: str) -> None:
    with pytest.raises(MediaInputBoundaryError, match="MEDIA_OBJECT_REF_INVALID"):
        _authorize(MetadataStore(_metadata()), _claim(object_ref=object_ref))


@pytest.mark.parametrize(
    ("metadata", "claim", "error"),
    [
        (_metadata(family_id="family-b"), _claim(), "SCOPE_MISMATCH"),
        (_metadata(exists=False), _claim(), "NOT_FOUND"),
        (_metadata(sha256="b" * 64), _claim(), "SHA256_MISMATCH"),
        (_metadata(mime_type="image/jpeg"), _claim(), "MIME_MISMATCH"),
        (_metadata(size_bytes=11 * 1024 * 1024), _claim(), "ITEM_TOO_LARGE"),
        (_metadata(), _claim(mime_type="image/svg+xml"), "MIME_UNSUPPORTED"),
    ],
)
def test_scope_existence_integrity_mime_and_size_are_server_enforced(
    metadata: MediaObjectMetadata,
    claim: MediaObjectClaim,
    error: str,
) -> None:
    with pytest.raises(MediaInputBoundaryError, match=error):
        _authorize(MetadataStore(metadata), claim)


def test_persisted_deletion_state_denies_after_authorizer_restart() -> None:
    store = MetadataStore(_metadata())
    assert _authorize(store, _claim())

    store.metadata = replace(store.metadata, state=MediaObjectState.DELETED, exists=False)
    restarted_authorizer = GovernedMediaInputAuthorizer(store)

    with pytest.raises(MediaInputBoundaryError, match="NOT_FOUND|DELETED_OR_PENDING"):
        restarted_authorizer.authorize(
            (_claim(),),
            tenant_id="tenant-a",
            family_id="family-a",
            purpose="growth_support",
        )


class LayerPort:
    def __init__(self, layer: MediaDeletionLayer) -> None:
        self.layer = layer

    def delete_subject(self, command: SubjectDeletionCommand) -> MediaLayerDeletionReceipt:
        return MediaLayerDeletionReceipt(
            layer=self.layer,
            tenant_id=command.tenant_id,
            subject_id=command.subject_id,
            command_id=command.command_id,
            correlation_id=command.correlation_id,
            causation_id=command.causation_id,
            deleted_count=1,
            confirmed=True,
            audit_ref=f"audit:{self.layer.value}",
            provenance_ref=f"provenance:{self.layer.value}",
            deletion_receipt_ref=f"deletion:{self.layer.value}",
        )


def _command() -> SubjectDeletionCommand:
    return SubjectDeletionCommand(
        command_id="delete-command-1",
        tenant_id="tenant-a",
        family_id="family-a",
        subject_id="child-a",
        deletion_ref="delete:child-a",
        requested_by="guardian-a",
        idempotency_key="delete-child-a",
        correlation_id="correlation-delete-a",
        causation_id="request-delete-a",
        requested_at=datetime(2026, 9, 5, tzinfo=UTC),
    )


def test_media_projection_deletion_fans_out_to_every_required_layer() -> None:
    adapter = GovernedMediaProjectionDeletionAdapter(
        LayerPort(layer) for layer in MediaDeletionLayer
    )

    receipt = adapter.delete_subject(_command())

    assert receipt.confirmed is True
    assert receipt.deleted_count == len(MediaDeletionLayer)
    assert receipt.projection.value == "MEDIA"


def test_media_deletion_rejects_missing_layer_or_uncorrelated_receipt() -> None:
    with pytest.raises(MediaInputBoundaryError, match="LAYERS_MISSING"):
        GovernedMediaProjectionDeletionAdapter(
            LayerPort(layer)
            for layer in MediaDeletionLayer
            if layer is not MediaDeletionLayer.INDEX
        )

    class WrongFamilyLayer(LayerPort):
        def delete_subject(self, command: SubjectDeletionCommand) -> MediaLayerDeletionReceipt:
            return replace(super().delete_subject(command), tenant_id="tenant-other")

    ports = [LayerPort(layer) for layer in MediaDeletionLayer]
    ports[0] = WrongFamilyLayer(MediaDeletionLayer.OBJECT)
    with pytest.raises(MediaInputBoundaryError, match="RECEIPT_INVALID"):
        GovernedMediaProjectionDeletionAdapter(ports).delete_subject(_command())
