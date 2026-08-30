"""Experience-loop contracts for the Family need platform.

These are transport/runtime contracts, not business aggregates.  They make the
experience flywheel observable (``ExperienceEvent``), explainable
(``RecommendationDecision``), and correctable (``FeedbackSignal``) without
giving the AI runtime a way to write Family/Journey/Service/Commerce facts.

The contracts deliberately carry the same scope envelope on every record:
tenant, region, family, subjects, purpose, consent, data class, four locale
dimensions, provenance, deletion and correlation/causation.  A record with a
missing envelope cannot safely enter a recommendation cache, event stream, or
evaluation set at global scale.

The implementation is intentionally provider-agnostic.  Model access remains
owned by ``backend.intelligence.model_gateway``; this module only describes
the evidence and feedback around an experience decision.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from backend.intelligence.model_gateway.contracts import DataClass
from backend.platform.idempotency.keys import IdempotencyKey


class ExperienceContractError(ValueError):
    """Base error raised when an experience record cannot be admitted."""


class ScopeMismatchError(ExperienceContractError):
    """Raised when records from different tenant/family/subject scopes meet."""


class ExperienceNode(StrEnum):
    """N0-N8 nodes from the Family Need target model."""

    N0 = "N0"  # need signal
    N1 = "N1"  # need clarification
    N2 = "N2"  # need triage
    N3 = "N3"  # solution design
    N4 = "N4"  # resource orchestration
    N5 = "N5"  # delivery
    N6 = "N6"  # quality acceptance
    N7 = "N7"  # outcome and relationship
    N8 = "N8"  # new need feedback loop


class ExperienceEventType(StrEnum):
    """Interaction facts, never authoritative growth/service facts."""

    ENTRY_OPENED = "entry_opened"
    CONTENT_SHOWN = "content_shown"
    CONTENT_SELECTED = "content_selected"
    ACTION_PROPOSAL_SHOWN = "action_proposal_shown"
    ACTION_STARTED = "action_started"
    ACTION_COMPLETED = "action_completed"
    ACTION_SKIPPED = "action_skipped"
    ACTION_PAUSED = "action_paused"
    FEEDBACK_SUBMITTED = "feedback_submitted"
    SERVICE_INTENT_DECLARED = "service_intent_declared"
    COMMERCIAL_GATE_OPENED = "commercial_gate_opened"


class RecommendationStatus(StrEnum):
    """Lifecycle of a suggestion; none of these states is a business fact."""

    PROPOSED = "proposed"
    SHOWN = "shown"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    BLOCKED = "blocked"
    EXPIRED = "expired"


class FeedbackSignalType(StrEnum):
    """User/family feedback, including safe exits and service escalation."""

    ACCEPTED = "accepted"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    REWRITTEN = "rewritten"
    PAUSED = "paused"
    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"
    COMPLAINT = "complaint"
    REQUEST_HUMAN = "request_human"
    LOWER_FREQUENCY = "lower_frequency"
    CLEAR_RECOMMENDATIONS = "clear_recommendations"
    SERVICE_INTENT = "service_intent"


class FeedbackTargetType(StrEnum):
    EVENT = "experience_event"
    RECOMMENDATION = "recommendation_decision"
    ACTION_PROPOSAL = "action_proposal"


class ExperienceModality(StrEnum):
    """Supported experience input/output modalities."""

    TEXT = "text"
    VOICE = "voice"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    INTERACTIVE_CARD = "interactive_card"


class ModalityOperation(StrEnum):
    """How a media artifact crosses the experience boundary."""

    INPUT = "input"
    OUTPUT = "output"
    TRANSCRIPTION = "transcription"
    OCR = "ocr"
    PLAYBACK = "playback"


class MemoryScope(StrEnum):
    """Who a memory is about; scopes are never inferred from free text."""

    CHILD = "child"
    GUARDIAN = "guardian"
    FAMILY_RELATIONSHIP = "family_relationship"


class MemoryLevel(StrEnum):
    """Retention horizon; every level still has an explicit expiry."""

    M0_TURN = "M0"
    M1_SESSION = "M1"
    M2_JOURNEY = "M2"
    M3_DURABLE = "M3"


class ProvenanceKind(StrEnum):
    USER = "user"
    HUMAN = "human"
    SYSTEM = "system"
    AI_DRAFT = "ai_draft"
    SYNTHETIC_TEST = "synthetic_test"


@dataclass(frozen=True, slots=True)
class DeletionRef:
    """A deletion/retention handle carried into every experience record."""

    deletion_id: str
    retention_policy: str
    requested_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.deletion_id or not self.retention_policy:
            raise ExperienceContractError(
                "deletion_id and retention_policy are required for experience data"
            )


@dataclass(frozen=True, slots=True)
class ExperienceProvenance:
    """Why this record exists and, for AI drafts, which attempt produced it."""

    provenance_ref: str
    source_refs: tuple[str, ...]
    kind: ProvenanceKind
    policy_version: str
    context_snapshot_ref: str | None = None
    model_attempt_ref: str | None = None
    captured_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.provenance_ref or not self.policy_version:
            raise ExperienceContractError(
                "provenance_ref and policy_version are required"
            )
        if not self.source_refs:
            raise ExperienceContractError("source_refs must not be empty")
        if not isinstance(self.kind, ProvenanceKind):
            raise ExperienceContractError("PROVENANCE_KIND_UNSUPPORTED")
        if self.kind is ProvenanceKind.AI_DRAFT and (
            not self.context_snapshot_ref or not self.model_attempt_ref
        ):
            raise ExperienceContractError(
                "AI draft provenance requires context_snapshot_ref and model_attempt_ref"
            )


@dataclass(frozen=True, slots=True)
class ExperienceMediaRef:
    """Tenant-scoped media handle for input/output/transcription/OCR/playback.

    The experience runtime stores only a reference and metadata, never a raw
    provider object.  Every derived artifact (for example a transcript or OCR
    result) must carry its own provenance and deletion handle so deleting the
    source can find all derived copies.
    """

    media_id: str
    media_ref: str
    tenant_id: str
    region_id: str
    family_id: str
    subject_ids: tuple[str, ...]
    modality: ExperienceModality
    operation: ModalityOperation
    purpose: str
    consent_version: str
    consent_granted: bool
    data_class: DataClass
    locale: str
    provenance: ExperienceProvenance
    deletion_ref: DeletionRef
    correlation_id: str
    causation_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.media_id or not self.media_ref:
            raise ExperienceContractError("media_id and media_ref are required")
        if not self.tenant_id or not self.region_id or not self.family_id:
            raise ExperienceContractError("media tenant/region/family scope is required")
        if not self.correlation_id or not self.causation_id:
            raise ExperienceContractError("media correlation_id and causation_id are required")
        if not self.subject_ids or any(not value for value in self.subject_ids):
            raise ExperienceContractError("media subject_ids must not be empty")
        if not isinstance(self.modality, ExperienceModality):
            raise ExperienceContractError("MEDIA_MODALITY_UNSUPPORTED")
        if not isinstance(self.operation, ModalityOperation):
            raise ExperienceContractError("MEDIA_OPERATION_UNSUPPORTED")
        if str(self.data_class) not in _VALID_DATA_CLASSES:
            raise ExperienceContractError("MEDIA_DATA_CLASS_UNSUPPORTED")
        if not _LOCALE_RE.fullmatch(self.locale):
            raise ExperienceContractError("MEDIA_LOCALE_UNSUPPORTED")
        if not isinstance(self.provenance, ExperienceProvenance):
            raise ExperienceContractError("MEDIA_PROVENANCE_REQUIRED")
        if not isinstance(self.deletion_ref, DeletionRef):
            raise ExperienceContractError("MEDIA_DELETION_REF_REQUIRED")
        if (
            str(self.data_class) in {"FAMILY_PRIVATE_TEXT", "MINOR_PERSONAL_DATA"}
            and not self.consent_granted
        ):
            raise ExperienceContractError("MEDIA_CONSENT_REQUIRED")
        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise ExperienceContractError("MEDIA_EXPIRY_INVALID")
        if self.operation is ModalityOperation.PLAYBACK and self.expires_at is None:
            raise ExperienceContractError("MEDIA_PLAYBACK_REQUIRES_EXPIRY")

    def is_expired(self, moment: datetime | None = None) -> bool:
        """Return whether the artifact may no longer be played/read."""

        if self.expires_at is None:
            return False
        reference = moment or datetime.now(UTC)
        if reference.tzinfo is None and self.expires_at.tzinfo is not None:
            reference = reference.replace(tzinfo=UTC)
        if reference.tzinfo is not None and self.expires_at.tzinfo is None:
            reference = reference.astimezone(UTC).replace(tzinfo=None)
        return reference >= self.expires_at

    def assert_playable(self, moment: datetime | None = None) -> None:
        """Fail closed rather than returning an expired media reference."""

        if self.is_expired(moment):
            raise ExperienceContractError("MEDIA_EXPIRED")

    def assert_scope(self, scope: ExperienceScope) -> None:
        """Reject cross-tenant/family/subject media attachment."""

        if self.tenant_id != scope.tenant_id:
            raise ScopeMismatchError("CROSS_TENANT_MEDIA_SCOPE")
        if self.region_id != scope.region_id or self.family_id != scope.family_id:
            raise ScopeMismatchError("CROSS_FAMILY_MEDIA_SCOPE")
        if frozenset(self.subject_ids) != frozenset(scope.subject_ids):
            raise ScopeMismatchError("CROSS_SUBJECT_MEDIA_SCOPE")
        if self.consent_version != scope.consent_version:
            raise ExperienceContractError("MEDIA_CONSENT_VERSION_MISMATCH")
        if not scope.consent_granted:
            raise ExperienceContractError("CONSENT_REQUIRED")


@dataclass(frozen=True, slots=True)
class MemoryRef:
    """An explicitly scoped, expiring memory reference.

    M0-M3 are retention horizons, not permission levels.  The child, guardian,
    and family-relationship scopes are explicit because a memory must not be
    reinterpreted as a different person's profile by a recommender.  Durable
    M3 memory still expires and carries a deletion cascade; there is no
    unlimited-memory mode.
    """

    memory_id: str
    memory_ref: str
    tenant_id: str
    region_id: str
    family_id: str
    subject_ids: tuple[str, ...]
    memory_scope: MemoryScope
    level: MemoryLevel
    purpose: str
    consent_version: str
    consent_granted: bool
    data_class: DataClass
    locale: str
    provenance: ExperienceProvenance
    deletion_ref: DeletionRef
    source_ref: str
    correlation_id: str
    causation_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    derived_memory_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.memory_id or not self.memory_ref or not self.source_ref:
            raise ExperienceContractError(
                "memory_id, memory_ref and source_ref are required"
            )
        if not self.tenant_id or not self.region_id or not self.family_id:
            raise ExperienceContractError("memory tenant/region/family scope is required")
        if not self.correlation_id or not self.causation_id:
            raise ExperienceContractError("memory correlation_id and causation_id are required")
        if not self.subject_ids or any(not value for value in self.subject_ids):
            raise ExperienceContractError("memory subject_ids must not be empty")
        if not _LOCALE_RE.fullmatch(self.locale):
            raise ExperienceContractError("MEMORY_LOCALE_UNSUPPORTED")
        if not isinstance(self.memory_scope, MemoryScope):
            raise ExperienceContractError("MEMORY_SCOPE_UNSUPPORTED")
        if not isinstance(self.level, MemoryLevel):
            raise ExperienceContractError("MEMORY_LEVEL_UNSUPPORTED")
        if str(self.data_class) not in _VALID_DATA_CLASSES:
            raise ExperienceContractError("MEMORY_DATA_CLASS_UNSUPPORTED")
        if not isinstance(self.provenance, ExperienceProvenance):
            raise ExperienceContractError("MEMORY_PROVENANCE_REQUIRED")
        if not isinstance(self.deletion_ref, DeletionRef):
            raise ExperienceContractError("MEMORY_DELETION_REF_REQUIRED")
        expected_count = {
            MemoryScope.CHILD: 1,
            MemoryScope.GUARDIAN: 1,
        }.get(self.memory_scope)
        if expected_count is not None and len(self.subject_ids) != expected_count:
            raise ExperienceContractError(
                f"{self.memory_scope.value} memory requires exactly one subject"
            )
        if self.memory_scope is MemoryScope.FAMILY_RELATIONSHIP and len(self.subject_ids) < 2:
            raise ExperienceContractError(
                "family_relationship memory requires at least two subjects"
            )
        if (
            str(self.data_class) in {"FAMILY_PRIVATE_TEXT", "MINOR_PERSONAL_DATA"}
            and not self.consent_granted
        ):
            raise ExperienceContractError("MEMORY_CONSENT_REQUIRED")
        if self.purpose.lower() in _COMMERCIAL_PURPOSES:
            raise ExperienceContractError(
                "MEMORY_COMMERCIAL_PURPOSE_FORBIDDEN: memory cannot become a commercial profile"
            )
        if self.expires_at is None or self.expires_at <= self.created_at:
            raise ExperienceContractError(
                "MEMORY_EXPIRY_REQUIRED: memory retention must be bounded"
            )
        if any(not value or value == self.memory_id for value in self.derived_memory_ids):
            raise ExperienceContractError("derived_memory_ids must be distinct non-empty ids")
        if len(set(self.derived_memory_ids)) != len(self.derived_memory_ids):
            raise ExperienceContractError("derived_memory_ids must not contain duplicates")

    def is_expired(self, moment: datetime | None = None) -> bool:
        reference = moment or datetime.now(UTC)
        if reference.tzinfo is None and self.expires_at.tzinfo is not None:
            reference = reference.replace(tzinfo=UTC)
        if reference.tzinfo is not None and self.expires_at.tzinfo is None:
            reference = reference.astimezone(UTC).replace(tzinfo=None)
        return reference >= self.expires_at

    def assert_readable_by(
        self,
        scope: ExperienceScope,
        *,
        purpose: str,
        moment: datetime | None = None,
    ) -> None:
        """Fail closed for unauthorized, expired, or purpose-mismatched reads."""

        if self.tenant_id != scope.tenant_id:
            raise ScopeMismatchError("CROSS_TENANT_MEMORY_READ")
        if self.region_id != scope.region_id or self.family_id != scope.family_id:
            raise ScopeMismatchError("CROSS_FAMILY_MEMORY_READ")
        if not set(self.subject_ids).issubset(scope.subject_ids):
            raise ScopeMismatchError("MEMORY_SUBJECT_READ_DENIED")
        if self.consent_version != scope.consent_version:
            raise ExperienceContractError("MEMORY_CONSENT_VERSION_MISMATCH")
        if not scope.consent_granted:
            raise ExperienceContractError("CONSENT_REQUIRED")
        if purpose != self.purpose:
            raise ExperienceContractError("MEMORY_PURPOSE_MISMATCH")
        if not self.consent_granted:
            raise ExperienceContractError("MEMORY_CONSENT_REQUIRED")
        if self.is_expired(moment):
            raise ExperienceContractError("MEMORY_EXPIRED")

    def deletion_cascade_ids(self) -> tuple[str, ...]:
        """Return source plus derived ids for deletion worker fan-out."""

        return (self.memory_id, *self.derived_memory_ids)

    def assert_scope(self, scope: ExperienceScope) -> None:
        if self.tenant_id != scope.tenant_id:
            raise ScopeMismatchError("CROSS_TENANT_MEMORY_SCOPE")
        if self.region_id != scope.region_id or self.family_id != scope.family_id:
            raise ScopeMismatchError("CROSS_FAMILY_MEMORY_SCOPE")
        if not set(self.subject_ids).issubset(scope.subject_ids):
            raise ScopeMismatchError("CROSS_SUBJECT_MEMORY_SCOPE")
        if self.consent_version != scope.consent_version:
            raise ExperienceContractError("MEMORY_CONSENT_VERSION_MISMATCH")
        if not scope.consent_granted:
            raise ExperienceContractError("CONSENT_REQUIRED")


_LOCALE_RE = re.compile(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*")
_REGION_RE = re.compile(r"[A-Z]{2,3}")
_VALID_DATA_CLASSES = {
    "SYNTHETIC",
    "OPERATIONAL_TEXT",
    "FAMILY_PRIVATE_TEXT",
    "MINOR_PERSONAL_DATA",
}
_COMMERCIAL_PURPOSES = {
    "marketing",
    "commercial_recommendation",
    "upsell",
    "sales",
}


@dataclass(frozen=True, slots=True)
class ExperienceScope:
    """Common isolation and policy envelope for all three contracts."""

    global_id: str
    tenant_id: str
    region_id: str
    family_id: str
    subject_ids: tuple[str, ...]
    purpose: str
    consent_version: str
    consent_granted: bool
    data_class: DataClass
    locale: str
    content_locale: str
    model_locale: str
    policy_locale: str
    deletion_ref: DeletionRef
    correlation_id: str
    causation_id: str

    def __post_init__(self) -> None:
        required = (
            self.global_id,
            self.tenant_id,
            self.region_id,
            self.family_id,
            self.purpose,
            self.consent_version,
            self.correlation_id,
            self.causation_id,
        )
        if not all(required):
            raise ExperienceContractError(
                "global_id, tenant_id, region_id, family_id, purpose, consent_version, "
                "correlation_id and causation_id are required"
            )
        if not isinstance(self.deletion_ref, DeletionRef):
            raise ExperienceContractError("DELETION_REF_REQUIRED")
        if (
            str(self.data_class) in {"FAMILY_PRIVATE_TEXT", "MINOR_PERSONAL_DATA"}
            and not self.consent_granted
        ):
            raise ExperienceContractError("CONSENT_REQUIRED")
        if not isinstance(self.subject_ids, tuple) or any(not value for value in self.subject_ids):
            raise ExperienceContractError("subject_ids must be a tuple of non-empty ids")
        if len(set(self.subject_ids)) != len(self.subject_ids):
            raise ExperienceContractError("subject_ids must not contain duplicates")
        if str(self.data_class) not in _VALID_DATA_CLASSES:
            raise ExperienceContractError("DATA_CLASS_UNSUPPORTED")
        for name, locale in (
            ("locale", self.locale),
            ("content_locale", self.content_locale),
            ("model_locale", self.model_locale),
            ("policy_locale", self.policy_locale),
        ):
            if not _LOCALE_RE.fullmatch(locale):
                raise ExperienceContractError(f"{name.upper()}_UNSUPPORTED")
        if not _REGION_RE.fullmatch(self.region_id):
            raise ExperienceContractError("REGION_UNSUPPORTED")
        if (
            str(self.data_class) == "MINOR_PERSONAL_DATA"
            and self.purpose.lower() in _COMMERCIAL_PURPOSES
        ):
            raise ExperienceContractError(
                "MINOR_COMMERCIAL_PURPOSE_FORBIDDEN: automated commercial recommendation "
                "cannot be based on minor personal data"
            )

    @property
    def subject_id(self) -> str | None:
        """Convenience accessor for one-subject flows; multi-subject remains explicit."""

        return self.subject_ids[0] if len(self.subject_ids) == 1 else None


class _ScopedContract:
    """Read-only field projection so callers can inspect scope directly."""

    scope: ExperienceScope
    provenance: ExperienceProvenance
    media_refs: tuple[ExperienceMediaRef, ...]
    memory_refs: tuple[MemoryRef, ...]

    @property
    def global_id(self) -> str:
        return self.scope.global_id

    @property
    def tenant_id(self) -> str:
        return self.scope.tenant_id

    @property
    def region_id(self) -> str:
        return self.scope.region_id

    @property
    def family_id(self) -> str:
        return self.scope.family_id

    @property
    def subject_ids(self) -> tuple[str, ...]:
        return self.scope.subject_ids

    @property
    def subject_id(self) -> str | None:
        return self.scope.subject_id

    @property
    def purpose(self) -> str:
        return self.scope.purpose

    @property
    def consent_version(self) -> str:
        return self.scope.consent_version

    @property
    def consent_granted(self) -> bool:
        return self.scope.consent_granted

    @property
    def data_class(self) -> DataClass:
        return self.scope.data_class

    @property
    def locale(self) -> str:
        return self.scope.locale

    @property
    def content_locale(self) -> str:
        return self.scope.content_locale

    @property
    def model_locale(self) -> str:
        return self.scope.model_locale

    @property
    def policy_locale(self) -> str:
        return self.scope.policy_locale

    @property
    def deletion_ref(self) -> DeletionRef:
        return self.scope.deletion_ref

    @property
    def correlation_id(self) -> str:
        return self.scope.correlation_id

    @property
    def causation_id(self) -> str:
        return self.scope.causation_id

    @property
    def modalities(self) -> tuple[ExperienceModality, ...]:
        """Modalities attached to this record (text when no media is attached)."""

        attached = tuple(dict.fromkeys(media.modality for media in self.media_refs))
        return attached or (ExperienceModality.TEXT,)

    @property
    def modality(self) -> ExperienceModality:
        """Convenience accessor for the primary modality."""

        return self.modalities[0]

    @property
    def memory_scopes(self) -> tuple[MemoryScope, ...]:
        """Explicit memory partitions attached to this record."""

        return tuple(dict.fromkeys(memory.memory_scope for memory in self.memory_refs))

    @property
    def may_mutate_business_state(self) -> bool:
        """Experience records are signals/proposals, never domain mutations."""

        return False


def _validate_idempotency(key: IdempotencyKey, tenant_id: str) -> None:
    if key.tenant_id != tenant_id:
        raise ScopeMismatchError("IDEMPOTENCY_TENANT_MISMATCH")


@dataclass(frozen=True, slots=True)
class ExperienceEvent(_ScopedContract):
    """Append-only interaction fact used by the experience and growth flywheels."""

    event_id: str
    event_type: ExperienceEventType
    node: ExperienceNode
    scope: ExperienceScope
    idempotency_key: IdempotencyKey
    provenance: ExperienceProvenance
    actor_id: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    payload: Mapping[str, Any] = field(default_factory=dict)
    media_refs: tuple[ExperienceMediaRef, ...] = ()
    memory_refs: tuple[MemoryRef, ...] = ()

    def __post_init__(self) -> None:
        if not self.event_id or not self.actor_id:
            raise ExperienceContractError("event_id and actor_id are required")
        if not isinstance(self.event_type, ExperienceEventType):
            raise ExperienceContractError("EVENT_TYPE_UNSUPPORTED")
        if not isinstance(self.node, ExperienceNode):
            raise ExperienceContractError("EXPERIENCE_NODE_UNSUPPORTED")
        if not isinstance(self.scope, ExperienceScope):
            raise ExperienceContractError("EXPERIENCE_SCOPE_REQUIRED")
        if not isinstance(self.provenance, ExperienceProvenance):
            raise ExperienceContractError("PROVENANCE_REQUIRED")
        if not isinstance(self.idempotency_key, IdempotencyKey):
            raise ExperienceContractError("IDEMPOTENCY_KEY_REQUIRED")
        _validate_idempotency(self.idempotency_key, self.scope.tenant_id)
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
        for media in self.media_refs:
            media.assert_scope(self.scope)
        for memory in self.memory_refs:
            memory.assert_scope(self.scope)
        forbidden = {
            "family_score",
            "family_rank",
            "ranking",
            "authoritative_fact",
            "canonical_state",
        }
        if forbidden.intersection(self.payload):
            raise ExperienceContractError(
                "EXPERIENCE_PAYLOAD_CANNOT_WRITE_FACT_OR_RANKING"
            )


@dataclass(frozen=True, slots=True)
class RecommendationDecision(_ScopedContract):
    """Explainable candidate decision emitted by a governed experience curator."""

    decision_id: str
    request_id: str
    scope: ExperienceScope
    idempotency_key: IdempotencyKey
    provenance: ExperienceProvenance
    strategy_version: str
    candidate_ids: tuple[str, ...]
    status: RecommendationStatus = RecommendationStatus.PROPOSED
    selected_ids: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    profile_id: str = "experience_curator"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    media_refs: tuple[ExperienceMediaRef, ...] = ()
    memory_refs: tuple[MemoryRef, ...] = ()

    def __post_init__(self) -> None:
        if not self.decision_id or not self.request_id or not self.strategy_version:
            raise ExperienceContractError(
                "decision_id, request_id and strategy_version are required"
            )
        if not isinstance(self.status, RecommendationStatus):
            raise ExperienceContractError("RECOMMENDATION_STATUS_UNSUPPORTED")
        if not isinstance(self.scope, ExperienceScope):
            raise ExperienceContractError("EXPERIENCE_SCOPE_REQUIRED")
        if not isinstance(self.provenance, ExperienceProvenance):
            raise ExperienceContractError("PROVENANCE_REQUIRED")
        if not isinstance(self.idempotency_key, IdempotencyKey):
            raise ExperienceContractError("IDEMPOTENCY_KEY_REQUIRED")
        _validate_idempotency(self.idempotency_key, self.scope.tenant_id)
        for media in self.media_refs:
            media.assert_scope(self.scope)
        for memory in self.memory_refs:
            memory.assert_scope(self.scope)
        if not self.candidate_ids or any(not value for value in self.candidate_ids):
            raise ExperienceContractError("candidate_ids must contain at least one id")
        if len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ExperienceContractError("candidate_ids must not contain duplicates")
        if not set(self.selected_ids).issubset(self.candidate_ids):
            raise ExperienceContractError("selected_ids must be a subset of candidate_ids")
        if self.status is RecommendationStatus.ACCEPTED and not self.selected_ids:
            raise ExperienceContractError("accepted recommendation requires selected_ids")
        if self.status in {
            RecommendationStatus.REJECTED,
            RecommendationStatus.BLOCKED,
        } and self.selected_ids:
            raise ExperienceContractError(
                "rejected or blocked recommendation cannot select a candidate"
            )


@dataclass(frozen=True, slots=True)
class FeedbackSignal(_ScopedContract):
    """Append-only feedback that tunes experience, frequency, and escalation."""

    feedback_id: str
    target_type: FeedbackTargetType
    target_id: str
    signal: FeedbackSignalType
    scope: ExperienceScope
    idempotency_key: IdempotencyKey
    provenance: ExperienceProvenance
    reason_code: str | None = None
    next_preference: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    media_refs: tuple[ExperienceMediaRef, ...] = ()
    memory_refs: tuple[MemoryRef, ...] = ()

    def __post_init__(self) -> None:
        if not self.feedback_id or not self.target_id:
            raise ExperienceContractError("feedback_id and target_id are required")
        if not isinstance(self.target_type, FeedbackTargetType):
            raise ExperienceContractError("FEEDBACK_TARGET_UNSUPPORTED")
        if not isinstance(self.signal, FeedbackSignalType):
            raise ExperienceContractError("FEEDBACK_SIGNAL_UNSUPPORTED")
        if not isinstance(self.scope, ExperienceScope):
            raise ExperienceContractError("EXPERIENCE_SCOPE_REQUIRED")
        if not isinstance(self.provenance, ExperienceProvenance):
            raise ExperienceContractError("PROVENANCE_REQUIRED")
        if not isinstance(self.idempotency_key, IdempotencyKey):
            raise ExperienceContractError("IDEMPOTENCY_KEY_REQUIRED")
        _validate_idempotency(self.idempotency_key, self.scope.tenant_id)
        for media in self.media_refs:
            media.assert_scope(self.scope)
        for memory in self.memory_refs:
            memory.assert_scope(self.scope)
        negative = {
            FeedbackSignalType.SKIPPED,
            FeedbackSignalType.PAUSED,
            FeedbackSignalType.NOT_HELPFUL,
            FeedbackSignalType.COMPLAINT,
        }
        if self.signal in negative and not (self.reason_code or self.next_preference):
            raise ExperienceContractError(
                "negative feedback requires reason_code or next_preference"
            )

    @property
    def requires_human_review(self) -> bool:
        """Complaint/human request enters the operations queue; never auto-closes."""

        return self.signal in {
            FeedbackSignalType.COMPLAINT,
            FeedbackSignalType.REQUEST_HUMAN,
        }

    def assert_targets(self, target: _ScopedContract) -> None:
        """Reject cross-tenant, cross-family, or cross-subject feedback binding."""

        if self.tenant_id != target.tenant_id:
            raise ScopeMismatchError("CROSS_TENANT_SCOPE")
        if self.family_id != target.family_id:
            raise ScopeMismatchError("CROSS_FAMILY_SCOPE")
        if frozenset(self.subject_ids) != frozenset(target.subject_ids):
            raise ScopeMismatchError("CROSS_SUBJECT_SCOPE")


def assert_scope_compatible(left: _ScopedContract, right: _ScopedContract) -> None:
    """Check exact isolation before joining events, decisions, or feedback."""

    if left.tenant_id != right.tenant_id:
        raise ScopeMismatchError("CROSS_TENANT_SCOPE")
    if left.family_id != right.family_id:
        raise ScopeMismatchError("CROSS_FAMILY_SCOPE")
    if frozenset(left.subject_ids) != frozenset(right.subject_ids):
        raise ScopeMismatchError("CROSS_SUBJECT_SCOPE")
    if left.purpose != right.purpose:
        raise ScopeMismatchError("PURPOSE_SCOPE_MISMATCH")


__all__ = [
    "DeletionRef",
    "ExperienceContractError",
    "ExperienceEvent",
    "ExperienceEventType",
    "ExperienceNode",
    "ExperienceMediaRef",
    "ExperienceModality",
    "ExperienceProvenance",
    "ExperienceScope",
    "FeedbackSignal",
    "FeedbackSignalType",
    "FeedbackTargetType",
    "MemoryLevel",
    "MemoryRef",
    "MemoryScope",
    "ModalityOperation",
    "ProvenanceKind",
    "RecommendationDecision",
    "RecommendationStatus",
    "ScopeMismatchError",
    "assert_scope_compatible",
]

# P4 keeps original media, derived transcripts, evidence, and family shares as
# separate runtime contracts.  The implementation lives in ``media_runtime``
# so its lifecycle adapter can remain independent from the broader experience
# event contracts; re-exporting the four records here gives callers one stable
# contract module without merging their deletion/provenance semantics.
from backend.intelligence.experience.media_runtime import (  # noqa: E402
    FamilyContentShare,
    MediaAsset,
    MediaEvidence,
    MediaTranscript,
)

__all__ += [
    "FamilyContentShare",
    "MediaAsset",
    "MediaEvidence",
    "MediaTranscript",
]
