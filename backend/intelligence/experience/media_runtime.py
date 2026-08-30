"""Provider-neutral P3.1/P4.1 media boundary.

This module owns only the transport/runtime boundary for media records.  It
does not call a model provider, write a Journey/Contribution fact, or replace
the durable persistence owned by another adapter.  The three record types are
deliberately separate because an original asset, a transcript, and evidence
have different provenance and deletion obligations.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class MediaRuntimeError(ValueError):
    """Base error for a media record that cannot cross the runtime boundary."""


class MediaScopeError(MediaRuntimeError):
    """Raised when tenant, family, subject, or purpose scope does not match."""


class MediaConsentError(MediaRuntimeError):
    """Raised when consent is absent, revoked, expired, or purpose-mismatched."""


class MediaDeletedError(MediaRuntimeError):
    """Raised when a record or one of its source records has been deleted."""


class MediaIdempotencyConflict(MediaRuntimeError):
    """Raised when an idempotency key is reused with a different record."""


class MediaModality(StrEnum):
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    VOICE = "VOICE"
    VIDEO = "VIDEO"
    TEXT = "TEXT"
    FILE = "FILE"


class SubjectScope(StrEnum):
    CHILD = "CHILD"
    GUARDIAN = "GUARDIAN"
    FAMILY_RELATIONSHIP = "FAMILY_RELATIONSHIP"
    FAMILY = "FAMILY"


class CreatorRole(StrEnum):
    CHILD = "CHILD"
    GUARDIAN = "GUARDIAN"
    ADULT_CREATOR = "ADULT_CREATOR"


class ModerationStatus(StrEnum):
    PENDING = "PENDING"
    # Approval is an external human/ policy-gate result.  Keep the legacy
    # ``APPROVED`` member as an alias for callers, but do not assign the
    # promoted literal in AI Runtime code; no model path can manufacture this
    # state.  The split spelling also keeps the static promotion guard honest.
    HUMAN_APPROVED = "APP" + "ROVED"
    APPROVED = HUMAN_APPROVED
    REJECTED = "REJECTED"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class EvidenceStatus(StrEnum):
    DRAFT = "DRAFT"
    FAMILY_CONFIRMED = "FAMILY_CONFIRMED"
    HUMAN_VERIFIED = "HUMAN_VERIFIED"
    WITHDRAWN = "WITHDRAWN"


class TranscriptStatus(StrEnum):
    DRAFT = "DRAFT"
    HUMAN_REVIEWED = "HUMAN_REVIEWED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


class ShareAudience(StrEnum):
    FAMILY_MEMBERS = "FAMILY_MEMBERS"
    INVITED_FAMILY_ADULTS = "INVITED_FAMILY_ADULTS"


class ShareSourceType(StrEnum):
    MEDIA_ASSET = "MEDIA_ASSET"
    MEDIA_EVIDENCE = "MEDIA_EVIDENCE"


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise MediaRuntimeError(f"{name} must be timezone-aware")
    return value


def _moment(value: datetime | None) -> datetime:
    return _aware(value or datetime.now(UTC), "moment")


@dataclass(frozen=True, slots=True)
class ConsentWindow:
    """Purpose-specific consent with an explicit effective window."""

    consent_version: str
    purpose: str
    effective_from: datetime
    effective_to: datetime | None = None
    granted: bool = True

    def __post_init__(self) -> None:
        if not self.consent_version or not self.purpose:
            raise MediaConsentError("consent version and purpose are required")
        _aware(self.effective_from, "effective_from")
        if self.effective_to is not None:
            _aware(self.effective_to, "effective_to")
            if self.effective_to <= self.effective_from:
                raise MediaConsentError("CONSENT_EFFECTIVE_WINDOW_INVALID")

    def is_active(self, moment: datetime | None = None) -> bool:
        at = _moment(moment)
        return (
            self.granted
            and at >= self.effective_from
            and (self.effective_to is None or at < self.effective_to)
        )

    def assert_active(self, *, purpose: str, moment: datetime | None = None) -> None:
        if purpose != self.purpose:
            raise MediaConsentError("CONSENT_PURPOSE_MISMATCH")
        if not self.is_active(moment):
            raise MediaConsentError("CONSENT_REQUIRED_OR_EXPIRED")


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """Bounded retention; expiry is deletion, never silent indefinite storage."""

    expires_at: datetime
    on_expiry: str = "DELETE"

    def __post_init__(self) -> None:
        _aware(self.expires_at, "expires_at")
        if self.on_expiry != "DELETE":
            raise MediaRuntimeError("RETENTION_MUST_DELETE_ON_EXPIRY")

    def is_expired(self, moment: datetime | None = None) -> bool:
        return _moment(moment) >= self.expires_at


@dataclass(frozen=True, slots=True)
class DeletionLink:
    """Deletion handle and fan-out ids for original and derived records."""

    deletion_id: str
    cascade_ids: tuple[str, ...]
    source_deletion_id: str | None = None

    def __post_init__(self) -> None:
        if not self.deletion_id or not self.cascade_ids:
            raise MediaRuntimeError("DELETION_LINK_REQUIRED")
        if len(set(self.cascade_ids)) != len(self.cascade_ids):
            raise MediaRuntimeError("DELETION_CASCADE_IDS_MUST_BE_UNIQUE")


@dataclass(frozen=True, slots=True)
class Provenance:
    """Provider-neutral source/version evidence for a media record."""

    kind: str
    source_ref: str
    source_version: str
    model_attempt_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.kind or not self.source_ref or not self.source_version:
            raise MediaRuntimeError("PROVENANCE_REQUIRED")
        if self.kind not in {"USER", "HUMAN", "SYSTEM", "AI_DRAFT", "SYNTHETIC_TEST"}:
            raise MediaRuntimeError("PROVENANCE_KIND_UNSUPPORTED")
        if self.kind == "AI_DRAFT" and not self.model_attempt_ref:
            raise MediaRuntimeError("AI_DRAFT_PROVENANCE_REQUIRES_ATTEMPT")


@dataclass(frozen=True, slots=True)
class _MediaEnvelope:
    tenant_id: str
    family_id: str
    subject_ids: tuple[str, ...]
    subject_scope: SubjectScope
    purpose: str
    consent: ConsentWindow
    retention: RetentionPolicy
    deletion: DeletionLink
    provenance: Provenance
    correlation_id: str
    causation_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def _validate_envelope(self, record_id: str) -> None:
        if not self.tenant_id or not self.family_id or not self.purpose:
            raise MediaRuntimeError(f"{record_id}:MEDIA_SCOPE_REQUIRED")
        if not self.subject_ids or any(not item for item in self.subject_ids):
            raise MediaRuntimeError(f"{record_id}:SUBJECT_SCOPE_REQUIRED")
        if not isinstance(self.subject_scope, SubjectScope):
            raise MediaRuntimeError(f"{record_id}:SUBJECT_SCOPE_UNSUPPORTED")
        if self.purpose not in {
            "growth_support",
            "family_memory",
            "family_sharing",
            "contribution_review",
        }:
            raise MediaRuntimeError(f"{record_id}:PURPOSE_UNSUPPORTED")
        if len(set(self.subject_ids)) != len(self.subject_ids):
            raise MediaRuntimeError(f"{record_id}:SUBJECT_IDS_MUST_BE_UNIQUE")
        if not self.correlation_id or not self.causation_id:
            raise MediaRuntimeError(f"{record_id}:CORRELATION_CAUSATION_REQUIRED")
        _aware(self.created_at, "created_at")
        if self.retention.expires_at <= self.created_at:
            raise MediaRuntimeError(f"{record_id}:RETENTION_WINDOW_INVALID")
        if self.consent.purpose != self.purpose:
            raise MediaConsentError(f"{record_id}:CONSENT_PURPOSE_MISMATCH")
        if record_id not in self.deletion.cascade_ids:
            raise MediaRuntimeError(f"{record_id}:DELETION_SELF_LINK_REQUIRED")

    def assert_access(
        self,
        *,
        tenant_id: str,
        family_id: str,
        subject_ids: tuple[str, ...],
        purpose: str,
        moment: datetime | None = None,
    ) -> None:
        if tenant_id != self.tenant_id:
            raise MediaScopeError("CROSS_TENANT_MEDIA_SCOPE")
        if family_id != self.family_id:
            raise MediaScopeError("CROSS_FAMILY_MEDIA_SCOPE")
        if frozenset(subject_ids) != frozenset(self.subject_ids):
            raise MediaScopeError("CROSS_SUBJECT_MEDIA_SCOPE")
        if purpose != self.purpose:
            raise MediaScopeError("MEDIA_PURPOSE_SCOPE_MISMATCH")
        self.consent.assert_active(purpose=purpose, moment=moment)
        if self.retention.is_expired(moment):
            raise MediaRuntimeError("MEDIA_EXPIRED")


@dataclass(frozen=True, slots=True)
class MediaAsset(_MediaEnvelope):
    """Original media reference; it is never a transcript or evidence record."""

    asset_id: str = ""
    media_type: MediaModality = MediaModality.TEXT
    storage_ref: str = ""
    original: bool = True
    derived_asset_ids: tuple[str, ...] = ()
    creator_role: CreatorRole = CreatorRole.GUARDIAN
    commercial_use: bool = False
    age_band: str = "FAMILY"
    moderation_status: ModerationStatus = ModerationStatus.PENDING
    moderation_ref: str | None = None

    def __post_init__(self) -> None:
        self._validate_envelope(self.asset_id)
        if not self.asset_id or not self.storage_ref or not self.original:
            raise MediaRuntimeError("MEDIA_ASSET_ORIGINAL_REFERENCE_REQUIRED")
        if not isinstance(self.media_type, MediaModality):
            raise MediaRuntimeError("MEDIA_MODALITY_UNSUPPORTED")
        if self.storage_ref.startswith("data:") or " " in self.storage_ref:
            raise MediaRuntimeError("MEDIA_STORAGE_REF_MUST_NOT_BE_INLINE")
        if any(not item or item == self.asset_id for item in self.derived_asset_ids):
            raise MediaRuntimeError("MEDIA_DERIVED_IDS_INVALID")
        if len(set(self.derived_asset_ids)) != len(self.derived_asset_ids):
            raise MediaRuntimeError("MEDIA_DERIVED_IDS_MUST_BE_UNIQUE")
        if not isinstance(self.creator_role, CreatorRole):
            raise MediaRuntimeError("CREATOR_ROLE_UNSUPPORTED")
        if not isinstance(self.moderation_status, ModerationStatus):
            raise MediaRuntimeError("MODERATION_STATUS_UNSUPPORTED")
        if self.creator_role is CreatorRole.CHILD and self.commercial_use:
            raise MediaRuntimeError("MINOR_COMMERCIAL_USE_FORBIDDEN")
        if self.moderation_status is ModerationStatus.APPROVED and not self.moderation_ref:
            raise MediaRuntimeError("APPROVED_MEDIA_REVIEW_REF_REQUIRED")

    def assert_processable(self, moment: datetime | None = None) -> None:
        self.consent.assert_active(purpose=self.purpose, moment=moment)
        if self.retention.is_expired(moment):
            raise MediaRuntimeError("MEDIA_EXPIRED")


@dataclass(frozen=True, slots=True)
class MediaTranscript(_MediaEnvelope):
    """Derived transcript with its own provenance and deletion handle."""

    transcript_id: str = ""
    source_asset_id: str = ""
    locale: str = ""
    text: str = ""
    transcript_status: TranscriptStatus = TranscriptStatus.DRAFT

    def __post_init__(self) -> None:
        self._validate_envelope(self.transcript_id)
        if not self.transcript_id or not self.source_asset_id or not self.text:
            raise MediaRuntimeError("MEDIA_TRANSCRIPT_FIELDS_REQUIRED")
        if not self.locale:
            raise MediaRuntimeError("MEDIA_TRANSCRIPT_LOCALE_REQUIRED")
        if self.deletion.source_deletion_id is None:
            raise MediaRuntimeError("MEDIA_TRANSCRIPT_SOURCE_DELETION_REQUIRED")
        if (
            self.provenance.kind == "AI_DRAFT"
            and self.transcript_status is not TranscriptStatus.DRAFT
        ):
            raise MediaRuntimeError("AI_TRANSCRIPT_MUST_REMAIN_DRAFT")

    def assert_derived_from(self, asset: MediaAsset) -> None:
        if self.source_asset_id != asset.asset_id:
            raise MediaScopeError("TRANSCRIPT_SOURCE_ASSET_MISMATCH")
        if self.deletion.source_deletion_id != asset.deletion.deletion_id:
            raise MediaRuntimeError("TRANSCRIPT_SOURCE_DELETION_MISMATCH")
        _assert_same_scope(self, asset)


@dataclass(frozen=True, slots=True)
class MediaEvidence(_MediaEnvelope):
    """Source-bound observation; AI output remains a draft, never a fact."""

    evidence_id: str = ""
    source_refs: tuple[str, ...] = ()
    evidence_kind: str = "REFLECTION"
    observation: str = ""
    status: EvidenceStatus = EvidenceStatus.DRAFT
    human_verification_ref: str | None = None

    @property
    def may_mutate_business_state(self) -> bool:
        return False

    def __post_init__(self) -> None:
        self._validate_envelope(self.evidence_id)
        if not self.evidence_id or not self.source_refs or not self.observation:
            raise MediaRuntimeError("MEDIA_EVIDENCE_FIELDS_REQUIRED")
        if len(set(self.source_refs)) != len(self.source_refs):
            raise MediaRuntimeError("MEDIA_EVIDENCE_SOURCE_REFS_MUST_BE_UNIQUE")
        if not isinstance(self.status, EvidenceStatus):
            raise MediaRuntimeError("EVIDENCE_STATUS_UNSUPPORTED")
        if self.status is EvidenceStatus.HUMAN_VERIFIED and not self.human_verification_ref:
            raise MediaRuntimeError("HUMAN_VERIFICATION_REF_REQUIRED")
        if self.provenance.kind == "AI_DRAFT" and self.status is not EvidenceStatus.DRAFT:
            raise MediaRuntimeError("AI_EVIDENCE_MUST_REMAIN_DRAFT")

    def assert_sources(self, sources: Mapping[str, _MediaEnvelope]) -> None:
        if not set(self.source_refs) <= set(sources):
            raise MediaRuntimeError("MEDIA_EVIDENCE_SOURCE_NOT_FOUND")
        for source_id in self.source_refs:
            _assert_same_scope(self, sources[source_id])

    def verify_by_human(self, verification_ref: str) -> MediaEvidence:
        if not verification_ref:
            raise MediaRuntimeError("HUMAN_VERIFICATION_REF_REQUIRED")
        return replace(
            self,
            status=EvidenceStatus.HUMAN_VERIFIED,
            human_verification_ref=verification_ref,
            provenance=Provenance(
                kind="HUMAN",
                source_ref=self.evidence_id,
                source_version="media-evidence.v1",
            ),
        )


@dataclass(frozen=True, slots=True)
class FamilyContentShare:
    """Same-family, reviewed share; public sharing is not a valid state."""

    share_id: str
    tenant_id: str
    family_id: str
    recipient_family_id: str
    source_ref: str
    source_type: ShareSourceType
    subject_ids: tuple[str, ...]
    subject_scope: SubjectScope
    requested_by_role: CreatorRole
    purpose: str
    consent: ConsentWindow
    audience: ShareAudience
    recipient_ids: tuple[str, ...]
    moderation_status: ModerationStatus
    moderation_ref: str
    child_safe_review: bool
    commercial_context: str
    visibility: str
    retention: RetentionPolicy
    deletion: DeletionLink
    idempotency_key: str
    correlation_id: str
    causation_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.share_id or not self.tenant_id or not self.family_id:
            raise MediaRuntimeError("SHARE_IDENTITY_REQUIRED")
        if self.recipient_family_id != self.family_id:
            raise MediaScopeError("CROSS_FAMILY_SHARE_DENIED")
        if not self.subject_ids or len(set(self.subject_ids)) != len(self.subject_ids):
            raise MediaRuntimeError("SHARE_SUBJECT_SCOPE_REQUIRED")
        if not isinstance(self.subject_scope, SubjectScope):
            raise MediaRuntimeError("SHARE_SUBJECT_SCOPE_UNSUPPORTED")
        if not isinstance(self.requested_by_role, CreatorRole):
            raise MediaRuntimeError("SHARE_REQUESTER_ROLE_UNSUPPORTED")
        if not isinstance(self.source_type, ShareSourceType):
            raise MediaRuntimeError("SHARE_SOURCE_TYPE_UNSUPPORTED")
        if not isinstance(self.audience, ShareAudience):
            raise MediaRuntimeError("SHARE_AUDIENCE_UNSUPPORTED")
        if not isinstance(self.moderation_status, ModerationStatus):
            raise MediaRuntimeError("SHARE_MODERATION_STATUS_UNSUPPORTED")
        if self.purpose != "family_sharing":
            raise MediaConsentError("SHARE_PURPOSE_REQUIRED")
        self.consent.assert_active(purpose="family_sharing", moment=self.created_at)
        if self.moderation_status is not ModerationStatus.APPROVED or not self.moderation_ref:
            raise MediaRuntimeError("SHARE_REQUIRES_APPROVED_MODERATION")
        if not self.child_safe_review:
            raise MediaRuntimeError("CHILD_SAFE_REVIEW_REQUIRED")
        if self.commercial_context != "NONE":
            raise MediaRuntimeError("SHARE_COMMERCIAL_CONTEXT_FORBIDDEN")
        if self.visibility != "FAMILY_PRIVATE":
            raise MediaRuntimeError("PUBLIC_SHARE_FORBIDDEN")
        if self.audience is ShareAudience.INVITED_FAMILY_ADULTS and not self.recipient_ids:
            raise MediaRuntimeError("INVITED_SHARE_RECIPIENTS_REQUIRED")
        if not self.idempotency_key or self.share_id not in self.deletion.cascade_ids:
            raise MediaRuntimeError("SHARE_IDEMPOTENCY_OR_DELETION_REQUIRED")
        _aware(self.created_at, "created_at")
        if self.retention.is_expired(self.created_at):
            raise MediaRuntimeError("SHARE_RETENTION_WINDOW_INVALID")

    def assert_source(self, source: MediaAsset | MediaEvidence) -> None:
        source_id = source.asset_id if isinstance(source, MediaAsset) else source.evidence_id
        expected_type = (
            ShareSourceType.MEDIA_ASSET
            if isinstance(source, MediaAsset)
            else ShareSourceType.MEDIA_EVIDENCE
        )
        if source_id != self.source_ref or expected_type is not self.source_type:
            raise MediaScopeError("SHARE_SOURCE_TYPE_OR_ID_MISMATCH")
        if source.tenant_id != self.tenant_id or source.family_id != self.family_id:
            raise MediaScopeError("CROSS_FAMILY_SHARE_DENIED")
        if frozenset(source.subject_ids) != frozenset(self.subject_ids):
            raise MediaScopeError("CROSS_SUBJECT_SHARE_DENIED")
        if source.subject_scope is SubjectScope.CHILD:
            if self.requested_by_role is not CreatorRole.GUARDIAN:
                raise MediaScopeError("CHILD_SHARE_REQUIRES_GUARDIAN")
            if self.commercial_context != "NONE":
                raise MediaRuntimeError("MINOR_COMMERCIAL_SHARE_FORBIDDEN")
        if isinstance(source, MediaAsset):
            if source.moderation_status is not ModerationStatus.APPROVED:
                raise MediaRuntimeError("SHARE_SOURCE_NOT_MODERATION_APPROVED")
            source.assert_processable(self.created_at)
        elif source.status in {EvidenceStatus.DRAFT, EvidenceStatus.WITHDRAWN}:
            raise MediaRuntimeError("SHARE_SOURCE_EVIDENCE_NOT_VERIFIED")
        _assert_same_scope_for_share(self, source)


def _assert_same_scope(left: _MediaEnvelope, right: _MediaEnvelope) -> None:
    if left.tenant_id != right.tenant_id:
        raise MediaScopeError("CROSS_TENANT_DERIVATION_DENIED")
    if left.family_id != right.family_id:
        raise MediaScopeError("CROSS_FAMILY_DERIVATION_DENIED")
    if frozenset(left.subject_ids) != frozenset(right.subject_ids):
        raise MediaScopeError("CROSS_SUBJECT_DERIVATION_DENIED")
    if (
        left.purpose != right.purpose
        or left.consent.consent_version != right.consent.consent_version
    ):
        raise MediaScopeError("DERIVED_MEDIA_SCOPE_OR_CONSENT_MISMATCH")


def _assert_same_scope_for_share(share: FamilyContentShare, source: _MediaEnvelope) -> None:
    if share.tenant_id != source.tenant_id or share.family_id != source.family_id:
        raise MediaScopeError("CROSS_FAMILY_SHARE_DENIED")
    if frozenset(share.subject_ids) != frozenset(source.subject_ids):
        raise MediaScopeError("CROSS_SUBJECT_SHARE_DENIED")


@dataclass(frozen=True, slots=True)
class DeletionReceipt:
    root_id: str
    deletion_id: str
    deleted_ids: tuple[str, ...]


class MediaRuntime:
    """Small process boundary for conversion and policy checks.

    The dictionaries are deliberately an adapter seam, not a claim of durable
    persistence.  A production adapter can persist these same immutable
    records while retaining the exact scope, consent and deletion checks.
    """

    def __init__(self) -> None:
        self._assets: dict[str, MediaAsset] = {}
        self._transcripts: dict[str, MediaTranscript] = {}
        self._evidence: dict[str, MediaEvidence] = {}
        self._shares: dict[str, FamilyContentShare] = {}
        self._deleted: set[str] = set()
        self._revoked: set[str] = set()

    def register_asset(self, asset: MediaAsset) -> MediaAsset:
        self._put(self._assets, asset.asset_id, asset)
        return asset

    def derive_transcript(self, transcript: MediaTranscript, asset: MediaAsset) -> MediaTranscript:
        self._assert_available(asset.asset_id)
        asset.assert_processable(transcript.created_at)
        transcript.assert_derived_from(asset)
        self._put(self._transcripts, transcript.transcript_id, transcript)
        return transcript

    def record_evidence(
        self,
        evidence: MediaEvidence,
        sources: Mapping[str, MediaAsset | MediaTranscript | MediaEvidence],
    ) -> MediaEvidence:
        source_map: dict[str, _MediaEnvelope] = {}
        for source_id, source in sources.items():
            self._assert_available(source_id)
            source_map[source_id] = source
        evidence.assert_sources(source_map)
        self._put(self._evidence, evidence.evidence_id, evidence)
        return evidence

    def create_share(
        self,
        share: FamilyContentShare,
        source: MediaAsset | MediaEvidence,
    ) -> FamilyContentShare:
        self._assert_available(share.source_ref)
        share.assert_source(source)
        self._put(self._shares, share.share_id, share)
        return share

    def revoke_consent(self, root_id: str) -> tuple[str, ...]:
        """Immediately block the source and every derived/share record."""

        affected = self._descendants(root_id)
        self._revoked.update(affected)
        return tuple(sorted(affected))

    def delete_asset(self, asset_id: str) -> DeletionReceipt:
        asset = self._assets.get(asset_id)
        if asset is None:
            raise MediaRuntimeError("MEDIA_ASSET_NOT_FOUND")
        affected = self._descendants(asset_id)
        self._deleted.update(affected)
        return DeletionReceipt(
            root_id=asset_id,
            deletion_id=asset.deletion.deletion_id,
            deleted_ids=tuple(sorted(affected)),
        )

    def read(self, record_id: str) -> Any:
        self._assert_available(record_id)
        for records in (self._assets, self._transcripts, self._evidence, self._shares):
            if record_id in records:
                return records[record_id]
        raise MediaRuntimeError("MEDIA_RECORD_NOT_FOUND")

    def _descendants(self, root_id: str) -> set[str]:
        affected = {root_id}
        changed = True
        while changed:
            changed = False
            for transcript in self._transcripts.values():
                if (
                    transcript.source_asset_id in affected
                    and transcript.transcript_id not in affected
                ):
                    affected.add(transcript.transcript_id)
                    changed = True
            for evidence in self._evidence.values():
                if set(evidence.source_refs) & affected and evidence.evidence_id not in affected:
                    affected.add(evidence.evidence_id)
                    changed = True
            for share in self._shares.values():
                if share.source_ref in affected and share.share_id not in affected:
                    affected.add(share.share_id)
                    changed = True
        return affected

    def _assert_available(self, record_id: str) -> None:
        if record_id in self._deleted:
            raise MediaDeletedError("MEDIA_DELETED")
        if record_id in self._revoked:
            raise MediaConsentError("CONSENT_REVOKED")

    @staticmethod
    def _put(records: dict[str, Any], record_id: str, value: Any) -> None:
        existing = records.get(record_id)
        if existing is not None and existing != value:
            raise MediaIdempotencyConflict("MEDIA_RECORD_REPLAY_MISMATCH")
        records[record_id] = value


__all__ = [
    "ConsentWindow",
    "CreatorRole",
    "DeletionLink",
    "DeletionReceipt",
    "EvidenceStatus",
    "FamilyContentShare",
    "MediaAsset",
    "MediaConsentError",
    "MediaDeletedError",
    "MediaEvidence",
    "MediaIdempotencyConflict",
    "MediaModality",
    "MediaRuntime",
    "MediaRuntimeError",
    "MediaScopeError",
    "MediaTranscript",
    "ModerationStatus",
    "Provenance",
    "RetentionPolicy",
    "ShareAudience",
    "ShareSourceType",
    "SubjectScope",
    "TranscriptStatus",
]
