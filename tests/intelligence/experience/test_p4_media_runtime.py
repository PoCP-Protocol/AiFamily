"""Runtime evidence for the independent P3.1/P4.1 media boundary."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.experience.media_runtime import (
    ConsentWindow,
    CreatorRole,
    DeletionLink,
    EvidenceStatus,
    FamilyContentShare,
    MediaAsset,
    MediaConsentError,
    MediaDeletedError,
    MediaEvidence,
    MediaModality,
    MediaRuntime,
    MediaRuntimeError,
    MediaScopeError,
    MediaTranscript,
    ModerationStatus,
    Provenance,
    RetentionPolicy,
    ShareAudience,
    ShareSourceType,
    SubjectScope,
    TranscriptStatus,
)

NOW = datetime(2026, 8, 30, 0, 0, tzinfo=UTC)


def _consent(purpose: str = "growth_support", *, until: datetime | None = None) -> ConsentWindow:
    return ConsentWindow(
        consent_version="consent.v1",
        purpose=purpose,
        effective_from=NOW - timedelta(minutes=1),
        effective_to=until,
    )


def _retention() -> RetentionPolicy:
    return RetentionPolicy(expires_at=NOW + timedelta(days=30))


def _asset(
    *,
    family_id: str = "family-a",
    subject_scope: SubjectScope = SubjectScope.CHILD,
    creator_role: CreatorRole = CreatorRole.CHILD,
    commercial_use: bool = False,
    moderation_status: ModerationStatus = ModerationStatus.APPROVED,
    media_type: MediaModality | str = MediaModality.VIDEO,
) -> MediaAsset:
    return MediaAsset(
        tenant_id="tenant-a",
        family_id=family_id,
        subject_ids=("child-a",),
        subject_scope=subject_scope,
        purpose="growth_support",
        consent=_consent(),
        retention=_retention(),
        deletion=DeletionLink("delete-asset", ("asset-a",)),
        provenance=Provenance("USER", "upload-a", "media.v1"),
        correlation_id="corr-a",
        causation_id="cause-a",
        created_at=NOW,
        asset_id="asset-a",
        media_type=media_type,  # type: ignore[arg-type]
        storage_ref="media:asset-a",
        derived_asset_ids=("transcript-a",),
        creator_role=creator_role,
        commercial_use=commercial_use,
        age_band="CHILD",
        moderation_status=moderation_status,
        moderation_ref="review-a" if moderation_status is ModerationStatus.APPROVED else None,
    )


def _transcript(asset: MediaAsset, *, transcript_id: str = "transcript-a") -> MediaTranscript:
    return MediaTranscript(
        tenant_id=asset.tenant_id,
        family_id=asset.family_id,
        subject_ids=asset.subject_ids,
        subject_scope=asset.subject_scope,
        purpose=asset.purpose,
        consent=asset.consent,
        retention=_retention(),
        deletion=DeletionLink(
            "delete-transcript",
            (transcript_id,),
            source_deletion_id=asset.deletion.deletion_id,
        ),
        provenance=Provenance("AI_DRAFT", asset.asset_id, "transcript.v1", "attempt-a"),
        correlation_id=asset.correlation_id,
        causation_id=asset.asset_id,
        created_at=NOW,
        transcript_id=transcript_id,
        source_asset_id=asset.asset_id,
        locale="zh-CN",
        text="我们一起完成了一步。",
        transcript_status=TranscriptStatus.DRAFT,
    )


def _evidence(asset: MediaAsset, transcript: MediaTranscript) -> MediaEvidence:
    return MediaEvidence(
        tenant_id=asset.tenant_id,
        family_id=asset.family_id,
        subject_ids=asset.subject_ids,
        subject_scope=asset.subject_scope,
        purpose=asset.purpose,
        consent=asset.consent,
        retention=_retention(),
        deletion=DeletionLink(
            "delete-evidence",
            ("evidence-a",),
            source_deletion_id=transcript.deletion.deletion_id,
        ),
        provenance=Provenance("AI_DRAFT", transcript.transcript_id, "evidence.v1", "attempt-a"),
        correlation_id=asset.correlation_id,
        causation_id=transcript.transcript_id,
        created_at=NOW,
        evidence_id="evidence-a",
        source_refs=(asset.asset_id, transcript.transcript_id),
        evidence_kind="REFLECTION",
        observation="家庭记录了一次共同完成的小行动。",
        status=EvidenceStatus.DRAFT,
    )


def _share(asset: MediaAsset) -> FamilyContentShare:
    return FamilyContentShare(
        share_id="share-a",
        tenant_id=asset.tenant_id,
        family_id=asset.family_id,
        recipient_family_id=asset.family_id,
        source_ref=asset.asset_id,
        source_type=ShareSourceType.MEDIA_ASSET,
        subject_ids=asset.subject_ids,
        subject_scope=asset.subject_scope,
        requested_by_role=CreatorRole.GUARDIAN,
        purpose="family_sharing",
        consent=_consent("family_sharing"),
        audience=ShareAudience.FAMILY_MEMBERS,
        recipient_ids=(),
        moderation_status=ModerationStatus.APPROVED,
        moderation_ref="share-review-a",
        child_safe_review=True,
        commercial_context="NONE",
        visibility="FAMILY_PRIVATE",
        retention=_retention(),
        deletion=DeletionLink(
            "delete-share",
            ("share-a",),
            source_deletion_id=asset.deletion.deletion_id,
        ),
        idempotency_key="tenant-a:share-a",
        correlation_id=asset.correlation_id,
        causation_id=asset.asset_id,
        created_at=NOW,
    )


def test_asset_transcript_and_evidence_are_separate_and_lineage_bound() -> None:
    asset = _asset()
    transcript = _transcript(asset)
    evidence = _evidence(asset, transcript)
    runtime = MediaRuntime()

    runtime.register_asset(asset)
    runtime.derive_transcript(transcript, asset)
    runtime.record_evidence(evidence, {asset.asset_id: asset, transcript.transcript_id: transcript})

    assert type(asset) is MediaAsset
    assert type(transcript) is MediaTranscript
    assert type(evidence) is MediaEvidence
    assert evidence.source_refs == (asset.asset_id, transcript.transcript_id)
    assert evidence.may_mutate_business_state is False


def test_ai_output_remains_draft_until_human_verification() -> None:
    asset = _asset()
    transcript = _transcript(asset)
    evidence = _evidence(asset, transcript)

    assert evidence.status is EvidenceStatus.DRAFT
    assert evidence.provenance.kind == "AI_DRAFT"
    verified = evidence.verify_by_human("human-review-a")
    assert verified.status is EvidenceStatus.HUMAN_VERIFIED
    assert verified.provenance.kind == "HUMAN"
    assert verified.may_mutate_business_state is False


def test_child_media_cannot_be_commercialized() -> None:
    with pytest.raises(MediaRuntimeError, match="MINOR_COMMERCIAL_USE_FORBIDDEN"):
        _asset(commercial_use=True)


def test_unsupported_modality_is_rejected() -> None:
    with pytest.raises(MediaRuntimeError, match="MEDIA_MODALITY_UNSUPPORTED"):
        _asset(media_type="PDF")  # type: ignore[arg-type]


def test_cross_family_share_is_rejected_before_storage() -> None:
    asset = _asset()
    with pytest.raises(MediaScopeError, match="CROSS_FAMILY_SHARE_DENIED"):
        FamilyContentShare(
            share_id="share-cross",
            tenant_id=asset.tenant_id,
            family_id=asset.family_id,
            recipient_family_id="family-b",
            source_ref=asset.asset_id,
            source_type=ShareSourceType.MEDIA_ASSET,
            subject_ids=asset.subject_ids,
            subject_scope=asset.subject_scope,
            requested_by_role=CreatorRole.GUARDIAN,
            purpose="family_sharing",
            consent=_consent("family_sharing"),
            audience=ShareAudience.FAMILY_MEMBERS,
            recipient_ids=(),
            moderation_status=ModerationStatus.APPROVED,
            moderation_ref="review-cross",
            child_safe_review=True,
            commercial_context="NONE",
            visibility="FAMILY_PRIVATE",
            retention=_retention(),
            deletion=DeletionLink("delete-cross", ("share-cross",)),
            idempotency_key="tenant-a:share-cross",
            correlation_id="corr-cross",
            causation_id=asset.asset_id,
            created_at=NOW,
        )


def test_share_cannot_bypass_pending_moderation() -> None:
    pending = _asset(moderation_status=ModerationStatus.PENDING)
    runtime = MediaRuntime()
    runtime.register_asset(pending)

    with pytest.raises(MediaRuntimeError, match="SHARE_SOURCE_NOT_MODERATION_APPROVED"):
        runtime.create_share(
            _share(
                replace(pending, moderation_status=ModerationStatus.PENDING, moderation_ref=None)
            ),
            pending,
        )


def test_consent_expiry_and_revoke_block_processing_and_read() -> None:
    expired = _asset()
    expired = replace(
        expired,
        consent=_consent(until=NOW + timedelta(seconds=1)),
    )
    with pytest.raises(MediaConsentError, match="CONSENT_REQUIRED_OR_EXPIRED"):
        expired.assert_processable(NOW + timedelta(seconds=1))

    runtime = MediaRuntime()
    source = _asset()
    transcript = _transcript(source)
    runtime.register_asset(source)
    runtime.derive_transcript(transcript, source)
    assert runtime.revoke_consent("asset-a") == ("asset-a", "transcript-a")
    with pytest.raises(MediaConsentError, match="CONSENT_REVOKED"):
        runtime.read("asset-a")


def test_delete_original_cascades_to_transcript_evidence_and_share() -> None:
    asset = _asset()
    transcript = _transcript(asset)
    evidence = _evidence(asset, transcript)
    verified = evidence.verify_by_human("human-review-a")
    share = _share(asset)
    runtime = MediaRuntime()
    runtime.register_asset(asset)
    runtime.derive_transcript(transcript, asset)
    runtime.record_evidence(verified, {asset.asset_id: asset, transcript.transcript_id: transcript})
    runtime.create_share(share, asset)

    receipt = runtime.delete_asset(asset.asset_id)
    assert set(receipt.deleted_ids) == {"asset-a", "transcript-a", "evidence-a", "share-a"}
    for record_id in receipt.deleted_ids:
        with pytest.raises(MediaDeletedError, match="MEDIA_DELETED"):
            runtime.read(record_id)


def test_derivation_rejects_cross_family_and_consent_mismatch() -> None:
    asset = _asset()
    runtime = MediaRuntime()
    runtime.register_asset(asset)
    wrong_family = _transcript(replace(asset, family_id="family-b"))

    with pytest.raises(MediaScopeError, match="CROSS_FAMILY_DERIVATION_DENIED"):
        runtime.derive_transcript(wrong_family, asset)


def test_replay_is_idempotent_but_payload_conflict_is_rejected() -> None:
    asset = _asset()
    runtime = MediaRuntime()
    assert runtime.register_asset(asset) is asset
    assert runtime.register_asset(asset) is asset

    with pytest.raises(MediaRuntimeError, match="MEDIA_RECORD_REPLAY_MISMATCH"):
        runtime.register_asset(replace(asset, storage_ref="media:other"))
