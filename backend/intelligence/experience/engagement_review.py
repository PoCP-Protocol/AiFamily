"""Durable, scope-bound review records for Engagement AI drafts.

The model output remains a DRAFT.  This module stores the exact server-created
draft, evidence identifiers, scope and provenance needed by a later Human Gate
submission.  A client may select only a candidate identifier; it cannot supply
candidate text, scope, evidence or provenance.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Index, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from backend.intelligence.experience.accepted_achievement import (
    build_achievement_action_proposal,
)
from backend.intelligence.experience.contracts import (
    DeletionRef,
    ExperienceEvent,
    ExperienceScope,
)
from backend.intelligence.experience.engagement import EngagementDraft
from backend.intelligence.experience.persistence import ExperiencePersistenceBase
from backend.intelligence.human_gate.contracts import (
    ActorType,
    GateScope,
    HumanTask,
    NamedActionRequest,
)
from backend.intelligence.model_gateway.contracts import (
    AiProvenance,
    DataClass,
    ModelDraft,
    TokenUsage,
)
from backend.platform.audit import AuditRecorder


class EngagementDraftReviewError(ValueError):
    """A draft review record is invalid, expired, conflicting or out of scope."""


class EngagementDraftReviewNotFound(LookupError):
    """No active draft exists in the caller's authorized scope."""


class EngagementDraftReviewRow(ExperiencePersistenceBase):
    """Immutable DRAFT snapshot; it is never a family or growth fact."""

    __tablename__ = "ai_engagement_draft_reviews"
    __table_args__ = (
        CheckConstraint("status = 'DRAFT'", name="ck_ai_engagement_review_draft_only"),
        CheckConstraint(
            "may_mutate_business_state = false",
            name="ck_ai_engagement_review_cannot_mutate",
        ),
        CheckConstraint(
            "expires_at > created_at",
            name="ck_ai_engagement_review_positive_ttl",
        ),
        Index(
            "uq_ai_engagement_review_request",
            "tenant_id",
            "family_id",
            "request_id",
            unique=True,
        ),
        Index(
            "ix_ai_engagement_review_scope_expiry",
            "tenant_id",
            "family_id",
            "expires_at",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    draft_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(160), nullable=False)
    region_id: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    purpose: Mapped[str] = mapped_column(String(128), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(160), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    scope_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    evidence_event_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    output_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    provenance_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    stable_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    may_mutate_business_state: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    retention_policy: Mapped[str] = mapped_column(String(160), nullable=False)
    deletion_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    superseded_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


@dataclass(frozen=True, slots=True)
class StoredEngagementDraft:
    draft_id: str
    draft: EngagementDraft
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class EngagementReviewer:
    """Trusted human identity resolved outside the request body."""

    actor_id: str
    actor_type: ActorType

    def __post_init__(self) -> None:
        _text(self.actor_id, "actor_id")
        if self.actor_type not in {ActorType.GUARDIAN, ActorType.PROFESSIONAL}:
            raise EngagementDraftReviewError("ENGAGEMENT_HUMAN_REVIEWER_REQUIRED")


class EngagementDraftReviewStore(Protocol):
    async def save(
        self,
        draft: EngagementDraft,
        *,
        draft_id: str | None = None,
        created_at: datetime | None = None,
        ttl: timedelta = timedelta(hours=24),
    ) -> StoredEngagementDraft: ...

    async def resolve(
        self,
        draft_id: str,
        *,
        scope: ExperienceScope,
        now: datetime | None = None,
    ) -> StoredEngagementDraft: ...

    async def resolve_for_execution(
        self,
        draft_id: str,
        *,
        scope: GateScope,
    ) -> StoredEngagementDraft: ...


class EngagementReviewEventReader(Protocol):
    def read(
        self, *, scope: ExperienceScope, event_ids: tuple[str, ...]
    ) -> tuple[ExperienceEvent, ...] | Awaitable[tuple[ExperienceEvent, ...]]: ...


class EngagementReviewHumanGate(Protocol):
    def submit(
        self,
        proposal: Any,
        *,
        recorder: AuditRecorder,
        task_id: str | None = None,
    ) -> HumanTask | Awaitable[HumanTask]: ...


def engagement_draft_id(*, tenant_id: str, family_id: str, request_id: str) -> str:
    """Derive an opaque, retry-stable identifier without exposing model content."""

    values = (tenant_id, family_id, request_id)
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise EngagementDraftReviewError("ENGAGEMENT_DRAFT_IDENTITY_REQUIRED")
    digest = hashlib.sha256("\x1f".join(values).encode()).hexdigest()
    return f"engagement-draft:{digest}"


class InMemoryEngagementDraftReviewStore:
    """Production-shaped test adapter with identical replay and scope rules."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], StoredEngagementDraft] = {}

    async def save(
        self,
        draft: EngagementDraft,
        *,
        draft_id: str | None = None,
        created_at: datetime | None = None,
        ttl: timedelta = timedelta(hours=24),
    ) -> StoredEngagementDraft:
        incoming = _new_record(draft, draft_id=draft_id, created_at=created_at, ttl=ttl)
        scope = _required_scope(incoming.draft)
        key = (scope.tenant_id, incoming.draft_id)
        existing = self._records.get(key)
        if existing is not None:
            _assert_same_record(existing, incoming)
            return existing
        if any(
            _required_scope(item.draft).tenant_id == scope.tenant_id
            and _required_scope(item.draft).family_id == scope.family_id
            and item.draft.request_id == draft.request_id
            for item in self._records.values()
        ):
            raise EngagementDraftReviewError("ENGAGEMENT_DRAFT_REQUEST_COLLISION")
        self._records[key] = incoming
        return incoming

    async def resolve(
        self,
        draft_id: str,
        *,
        scope: ExperienceScope,
        now: datetime | None = None,
    ) -> StoredEngagementDraft:
        _validate_current_scope(scope)
        record = self._records.get((scope.tenant_id, _text(draft_id, "draft_id")))
        if record is None:
            raise EngagementDraftReviewNotFound(draft_id)
        return _authorize_record(record, scope=scope, now=now)

    async def resolve_for_execution(
        self,
        draft_id: str,
        *,
        scope: GateScope,
    ) -> StoredEngagementDraft:
        record = self._records.get((scope.tenant_id, _text(draft_id, "draft_id")))
        if record is None:
            raise EngagementDraftReviewNotFound(draft_id)
        return _authorize_gate_record(record, scope)


class SqlAlchemyEngagementDraftReviewStore:
    """Async SQL adapter owned by the caller's request transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(
        self,
        draft: EngagementDraft,
        *,
        draft_id: str | None = None,
        created_at: datetime | None = None,
        ttl: timedelta = timedelta(hours=24),
    ) -> StoredEngagementDraft:
        incoming = _new_record(draft, draft_id=draft_id, created_at=created_at, ttl=ttl)
        scope = _required_scope(incoming.draft)
        existing = await self._session.get(
            EngagementDraftReviewRow, (scope.tenant_id, incoming.draft_id)
        )
        if existing is not None:
            stored = _stored(existing)
            _assert_same_record(stored, incoming)
            return stored
        request_match = await self._session.scalar(
            select(EngagementDraftReviewRow).where(
                EngagementDraftReviewRow.tenant_id == scope.tenant_id,
                EngagementDraftReviewRow.family_id == scope.family_id,
                EngagementDraftReviewRow.request_id == incoming.draft.request_id,
            )
        )
        if request_match is not None:
            stored = _stored(request_match)
            _assert_same_record(stored, incoming)
            return stored
        row = _row(incoming)
        self._session.add(row)
        await self._session.flush()
        return _stored(row)

    async def resolve(
        self,
        draft_id: str,
        *,
        scope: ExperienceScope,
        now: datetime | None = None,
    ) -> StoredEngagementDraft:
        _validate_current_scope(scope)
        row = await self._session.get(
            EngagementDraftReviewRow,
            (scope.tenant_id, _text(draft_id, "draft_id")),
        )
        if row is None:
            raise EngagementDraftReviewNotFound(draft_id)
        return _authorize_record(_stored(row), scope=scope, now=now)

    async def resolve_for_execution(
        self,
        draft_id: str,
        *,
        scope: GateScope,
    ) -> StoredEngagementDraft:
        row = await self._session.get(
            EngagementDraftReviewRow,
            (scope.tenant_id, _text(draft_id, "draft_id")),
        )
        if row is None:
            raise EngagementDraftReviewNotFound(draft_id)
        return _authorize_gate_record(_stored(row), scope)


class AchievementCandidateSubmissionService:
    """Re-authorize a stored candidate and submit it to Human Gate."""

    def __init__(
        self,
        store: EngagementDraftReviewStore,
        event_reader: EngagementReviewEventReader,
        gate: EngagementReviewHumanGate,
        recorder: AuditRecorder,
    ) -> None:
        self._store = store
        self._event_reader = event_reader
        self._gate = gate
        self._recorder = recorder

    async def submit(
        self,
        *,
        draft_id: str,
        candidate_id: str,
        scope: ExperienceScope,
        actor_id: str,
        approval_ref: str,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> HumanTask:
        reference = _aware(now or datetime.now(UTC), "now")
        actor_id = _text(actor_id, "actor_id")
        approval_ref = _text(approval_ref, "approval_ref")
        idempotency_key = _text(idempotency_key, "idempotency_key")
        candidate_id = _text(candidate_id, "candidate_id")
        stored = await self._store.resolve(draft_id, scope=scope, now=reference)
        stored_scope = _required_scope(stored.draft)
        loaded = self._event_reader.read(
            scope=stored_scope,
            event_ids=stored.draft.evidence_event_ids,
        )
        if inspect.isawaitable(loaded):
            loaded = await loaded
        if not isinstance(loaded, tuple) or any(
            not isinstance(event, ExperienceEvent) for event in loaded
        ):
            raise EngagementDraftReviewError("ENGAGEMENT_REVIEW_EVENTS_INVALID")
        if {event.event_id for event in loaded} != set(stored.draft.evidence_event_ids):
            raise EngagementDraftReviewError("ENGAGEMENT_REVIEW_EVIDENCE_STALE")
        for event in loaded:
            if not _same_authorized_scope(event.scope, stored_scope):
                raise EngagementDraftReviewError("ENGAGEMENT_REVIEW_EVIDENCE_SCOPE_MISMATCH")
        for subject_id in stored_scope.subject_ids:
            self._recorder.record_read(
                actor_id=actor_id,
                tenant_id=stored_scope.tenant_id,
                action="READ_ENGAGEMENT_DRAFT_EVIDENCE_FOR_REVIEW",
                resource_type="EngagementDraft",
                resource_id=stored.draft_id,
                subject_person_id=subject_id,
                accessed_fields=("event_id", "event_type", "occurred_at", "evidence_ref"),
                access_purpose=stored_scope.purpose,
                reason="revalidate evidence before opening a human review task",
                correlation_id=scope.correlation_id,
                subject_is_minor=True,
                approval_ref=approval_ref,
            )
        identity = hashlib.sha256(
            "\x1f".join((stored_scope.tenant_id, idempotency_key)).encode()
        ).hexdigest()
        proposal = build_achievement_action_proposal(
            stored.draft,
            candidate_id=candidate_id,
            scope=stored_scope,
            draft_id=stored.draft_id,
            proposal_id=f"achievement-proposal:{identity}",
            now=reference,
            ttl=stored.expires_at - reference,
        )
        submitted = self._gate.submit(proposal, recorder=self._recorder)
        return await submitted if inspect.isawaitable(submitted) else submitted


class AcceptedAchievementDraftVerifier:
    """Rebuild the accepted action from its immutable draft before execution."""

    def __init__(
        self,
        store: EngagementDraftReviewStore,
        event_reader: EngagementReviewEventReader,
    ) -> None:
        self._store = store
        self._event_reader = event_reader

    async def verify(self, request: NamedActionRequest) -> None:
        arguments = request.action_arguments
        draft_id = _text(arguments.get("engagement_draft_id"), "engagement_draft_id")
        candidate_id = _text(arguments.get("candidate_id"), "candidate_id")
        stored = await self._store.resolve_for_execution(draft_id, scope=request.scope)
        stored_scope = _required_scope(stored.draft)
        loaded = self._event_reader.read(
            scope=stored_scope,
            event_ids=stored.draft.evidence_event_ids,
        )
        if inspect.isawaitable(loaded):
            loaded = await loaded
        if not isinstance(loaded, tuple) or {
            event.event_id for event in loaded if isinstance(event, ExperienceEvent)
        } != set(stored.draft.evidence_event_ids):
            raise EngagementDraftReviewError("ACCEPTED_ACHIEVEMENT_EVIDENCE_STALE")
        if any(
            not isinstance(event, ExperienceEvent)
            or not _same_authorized_scope(event.scope, stored_scope)
            for event in loaded
        ):
            raise EngagementDraftReviewError("ACCEPTED_ACHIEVEMENT_EVIDENCE_SCOPE_MISMATCH")
        rebuilt = build_achievement_action_proposal(
            stored.draft,
            candidate_id=candidate_id,
            scope=stored_scope,
            draft_id=stored.draft_id,
            proposal_id=request.proposal_id,
            now=stored.created_at,
            ttl=stored.expires_at - stored.created_at,
        )
        if (
            dict(rebuilt.action_arguments) != dict(request.action_arguments)
            or rebuilt.provenance_ref != request.provenance_ref
            or rebuilt.scope != request.scope
        ):
            raise EngagementDraftReviewError("ACCEPTED_ACHIEVEMENT_BINDING_MISMATCH")


def _new_record(
    draft: EngagementDraft,
    *,
    draft_id: str | None,
    created_at: datetime | None,
    ttl: timedelta,
) -> StoredEngagementDraft:
    if not isinstance(draft, EngagementDraft):
        raise EngagementDraftReviewError("ENGAGEMENT_DRAFT_REQUIRED")
    scope = _required_scope(draft)
    _validate_current_scope(scope)
    if ttl <= timedelta(0):
        raise EngagementDraftReviewError("ENGAGEMENT_DRAFT_TTL_INVALID")
    created = _aware(created_at or datetime.now(UTC), "created_at")
    resolved_id = draft_id or engagement_draft_id(
        tenant_id=scope.tenant_id,
        family_id=scope.family_id,
        request_id=draft.request_id,
    )
    return StoredEngagementDraft(
        draft_id=_text(resolved_id, "draft_id"),
        draft=draft,
        created_at=created,
        expires_at=created + ttl,
    )


def _authorize_record(
    record: StoredEngagementDraft,
    *,
    scope: ExperienceScope,
    now: datetime | None,
) -> StoredEngagementDraft:
    stored_scope = _required_scope(record.draft)
    if not _same_authorized_scope(stored_scope, scope):
        raise EngagementDraftReviewNotFound(record.draft_id)
    reference = _aware(now or datetime.now(UTC), "now")
    if reference >= record.expires_at:
        raise EngagementDraftReviewError("ENGAGEMENT_DRAFT_EXPIRED")
    return record


def _authorize_gate_record(
    record: StoredEngagementDraft,
    scope: GateScope,
) -> StoredEngagementDraft:
    stored = _required_scope(record.draft)
    if (
        stored.tenant_id != scope.tenant_id
        or stored.family_id != scope.family_id
        or stored.subject_ids != scope.subject_ids
        or stored.purpose != scope.purpose
        or stored.consent_version != scope.consent_version
        or stored.correlation_id != scope.correlation_id
        or stored.deletion_ref.requested_at is not None
    ):
        raise EngagementDraftReviewNotFound(record.draft_id)
    return record


def _same_authorized_scope(left: ExperienceScope, right: ExperienceScope) -> bool:
    """Ignore request correlation while preserving every data authority field."""

    return (
        left.tenant_id == right.tenant_id
        and left.region_id == right.region_id
        and left.family_id == right.family_id
        and left.subject_ids == right.subject_ids
        and left.purpose == right.purpose
        and left.consent_version == right.consent_version
        and left.data_class == right.data_class
        and left.locale == right.locale
        and left.content_locale == right.content_locale
        and left.model_locale == right.model_locale
        and left.policy_locale == right.policy_locale
        and left.deletion_ref.deletion_id == right.deletion_ref.deletion_id
        and left.deletion_ref.retention_policy == right.deletion_ref.retention_policy
    )


def _validate_current_scope(scope: ExperienceScope) -> None:
    if not isinstance(scope, ExperienceScope):
        raise EngagementDraftReviewError("EXPERIENCE_SCOPE_REQUIRED")
    if not scope.consent_granted:
        raise EngagementDraftReviewError("ENGAGEMENT_CONSENT_REQUIRED")
    if scope.deletion_ref.requested_at is not None:
        raise EngagementDraftReviewError("ENGAGEMENT_SCOPE_DELETED")


def _required_scope(draft: EngagementDraft) -> ExperienceScope:
    if draft.scope is None:
        raise EngagementDraftReviewError("ENGAGEMENT_SCOPE_REQUIRED")
    return draft.scope


def _assert_same_record(
    existing: StoredEngagementDraft, incoming: StoredEngagementDraft
) -> None:
    if _stable_digest(existing) != _stable_digest(incoming):
        raise EngagementDraftReviewError("ENGAGEMENT_DRAFT_REPLAY_MISMATCH")


def _row(record: StoredEngagementDraft) -> EngagementDraftReviewRow:
    scope = _required_scope(record.draft)
    return EngagementDraftReviewRow(
        tenant_id=scope.tenant_id,
        draft_id=record.draft_id,
        family_id=scope.family_id,
        region_id=scope.region_id,
        subject_ids=list(scope.subject_ids),
        purpose=scope.purpose,
        consent_version=scope.consent_version,
        request_id=record.draft.request_id,
        scope_payload=_scope_payload(scope),
        evidence_event_ids=list(record.draft.evidence_event_ids),
        output_payload=_json_object(record.draft.output, "output_payload"),
        provenance_payload=_provenance_payload(record.draft.draft.provenance),
        stable_digest=_stable_digest(record),
        status="DRAFT",
        may_mutate_business_state=False,
        retention_policy=scope.deletion_ref.retention_policy,
        deletion_ref=scope.deletion_ref.deletion_id,
        created_at=record.created_at,
        expires_at=record.expires_at,
        superseded_reason=None,
    )


def _stored(row: EngagementDraftReviewRow) -> StoredEngagementDraft:
    if row.status != "DRAFT" or row.may_mutate_business_state is not False:
        raise EngagementDraftReviewError("ENGAGEMENT_DRAFT_PERSISTED_STATE_INVALID")
    try:
        scope = _scope_from_payload(row.scope_payload)
        if (
            scope.tenant_id != row.tenant_id
            or scope.family_id != row.family_id
            or scope.region_id != row.region_id
            or list(scope.subject_ids) != row.subject_ids
            or scope.purpose != row.purpose
            or scope.consent_version != row.consent_version
            or scope.deletion_ref.deletion_id != row.deletion_ref
            or scope.deletion_ref.retention_policy != row.retention_policy
        ):
            raise EngagementDraftReviewError("ENGAGEMENT_DRAFT_SCOPE_SCALAR_MISMATCH")
        draft = EngagementDraft(
            request_id=row.request_id,
            draft=ModelDraft(
                output=_json_object(row.output_payload, "output_payload"),
                provenance=_provenance_from_payload(row.provenance_payload),
            ),
            evidence_event_ids=tuple(row.evidence_event_ids),
            scope=scope,
        )
        record = StoredEngagementDraft(
            draft_id=row.draft_id,
            draft=draft,
            created_at=_stored_time(row.created_at),
            expires_at=_stored_time(row.expires_at),
        )
        if row.stable_digest != _stable_digest(record):
            raise EngagementDraftReviewError("ENGAGEMENT_DRAFT_DIGEST_MISMATCH")
        return record
    except EngagementDraftReviewError:
        raise
    except (TypeError, ValueError) as error:
        raise EngagementDraftReviewError("ENGAGEMENT_DRAFT_PERSISTED_SHAPE_INVALID") from error


def _stable_digest(record: StoredEngagementDraft) -> str:
    payload = {
        "draft_id": record.draft_id,
        "request_id": record.draft.request_id,
        "scope": _scope_payload(_required_scope(record.draft)),
        "evidence_event_ids": list(record.draft.evidence_event_ids),
        "output": _json_object(record.draft.output, "output_payload"),
        "provenance": _provenance_payload(record.draft.draft.provenance),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _scope_payload(scope: ExperienceScope) -> dict[str, Any]:
    return {
        "global_id": scope.global_id,
        "tenant_id": scope.tenant_id,
        "region_id": scope.region_id,
        "family_id": scope.family_id,
        "subject_ids": list(scope.subject_ids),
        "purpose": scope.purpose,
        "consent_version": scope.consent_version,
        "consent_granted": scope.consent_granted,
        "data_class": str(scope.data_class),
        "locale": scope.locale,
        "content_locale": scope.content_locale,
        "model_locale": scope.model_locale,
        "policy_locale": scope.policy_locale,
        "deletion_ref": {
            "deletion_id": scope.deletion_ref.deletion_id,
            "retention_policy": scope.deletion_ref.retention_policy,
            "requested_at": _iso(scope.deletion_ref.requested_at),
        },
        "correlation_id": scope.correlation_id,
        "causation_id": scope.causation_id,
    }


def _scope_from_payload(raw: object) -> ExperienceScope:
    value = _mapping(raw, "scope_payload")
    deletion = _mapping(value.get("deletion_ref"), "deletion_ref")
    requested_at = deletion.get("requested_at")
    return ExperienceScope(
        global_id=_required(value, "global_id"),
        tenant_id=_required(value, "tenant_id"),
        region_id=_required(value, "region_id"),
        family_id=_required(value, "family_id"),
        subject_ids=_string_tuple(value.get("subject_ids"), "subject_ids"),
        purpose=_required(value, "purpose"),
        consent_version=_required(value, "consent_version"),
        consent_granted=_required_bool(value, "consent_granted"),
        data_class=cast(DataClass, _required(value, "data_class")),
        locale=_required(value, "locale"),
        content_locale=_required(value, "content_locale"),
        model_locale=_required(value, "model_locale"),
        policy_locale=_required(value, "policy_locale"),
        deletion_ref=DeletionRef(
            deletion_id=_required(deletion, "deletion_id"),
            retention_policy=_required(deletion, "retention_policy"),
            requested_at=_parse_time(requested_at) if requested_at is not None else None,
        ),
        correlation_id=_required(value, "correlation_id"),
        causation_id=_required(value, "causation_id"),
    )


def _provenance_payload(value: AiProvenance) -> dict[str, Any]:
    usage = value.token_usage
    return {
        "provider_id": value.provider_id,
        "model": value.model,
        "model_version": value.model_version,
        "prompt_version": value.prompt_version,
        "schema_version": value.schema_version,
        "context_snapshot_ref": value.context_snapshot_ref,
        "latency_ms": value.latency_ms,
        "data_class": str(value.data_class),
        "use_case": value.use_case,
        "confidence": value.confidence,
        "token_usage": None
        if usage is None
        else {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
        },
        "release_set_id": value.release_set_id,
        "bundle_id": value.bundle_id,
        "deployment_receipt_id": value.deployment_receipt_id,
        "runtime_config_digest": value.runtime_config_digest,
        "deployment_sequence": value.deployment_sequence,
        "control_id": value.control_id,
        "fence_claim_id": value.fence_claim_id,
        "generated_at": value.generated_at.isoformat(),
    }


def _provenance_from_payload(raw: object) -> AiProvenance:
    value = _mapping(raw, "provenance_payload")
    raw_usage = value.get("token_usage")
    usage = None
    if raw_usage is not None:
        usage_value = _mapping(raw_usage, "token_usage")
        usage = TokenUsage(
            prompt_tokens=usage_value.get("prompt_tokens"),
            completion_tokens=usage_value.get("completion_tokens"),
            total_tokens=usage_value.get("total_tokens"),
        )
    return AiProvenance(
        provider_id=_required(value, "provider_id"),
        model=_required(value, "model"),
        model_version=_required(value, "model_version"),
        prompt_version=_required(value, "prompt_version"),
        schema_version=_required(value, "schema_version"),
        context_snapshot_ref=_required(value, "context_snapshot_ref"),
        latency_ms=value.get("latency_ms"),
        data_class=cast(DataClass, _required(value, "data_class")),
        use_case=_required(value, "use_case"),
        confidence=value.get("confidence"),
        token_usage=usage,
        release_set_id=_optional(value.get("release_set_id")),
        bundle_id=_optional(value.get("bundle_id")),
        deployment_receipt_id=_optional(value.get("deployment_receipt_id")),
        runtime_config_digest=_optional(value.get("runtime_config_digest")),
        deployment_sequence=value.get("deployment_sequence"),
        control_id=_optional(value.get("control_id")),
        fence_claim_id=_optional(value.get("fence_claim_id")),
        generated_at=_parse_time(value.get("generated_at")),
    )


def _json_object(value: object, name: str) -> dict[str, Any]:
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)
        decoded = json.loads(encoded)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise EngagementDraftReviewError(f"{name.upper()}_INVALID") from error
    if not isinstance(decoded, dict):
        raise EngagementDraftReviewError(f"{name.upper()}_INVALID")
    return decoded


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EngagementDraftReviewError(f"{name.upper()}_INVALID")
    return value


def _required(value: Mapping[str, Any], key: str) -> str:
    return _text(value.get(key), key)


def _required_bool(value: Mapping[str, Any], key: str) -> bool:
    item = value.get(key)
    if not isinstance(item, bool):
        raise EngagementDraftReviewError(f"{key.upper()}_INVALID")
    return item


def _string_tuple(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise EngagementDraftReviewError(f"{name.upper()}_INVALID")
    return tuple(_text(item, name) for item in value)


def _optional(value: object) -> str | None:
    return None if value is None else _text(value, "optional_ref")


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EngagementDraftReviewError(f"{name.upper()}_REQUIRED")
    return value.strip()


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise EngagementDraftReviewError("ENGAGEMENT_DRAFT_TIME_INVALID")
    try:
        return _aware(datetime.fromisoformat(value.replace("Z", "+00:00")), "time")
    except ValueError as error:
        raise EngagementDraftReviewError("ENGAGEMENT_DRAFT_TIME_INVALID") from error


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise EngagementDraftReviewError(f"{name.upper()}_TIMEZONE_REQUIRED")
    return value.astimezone(UTC)


def _stored_time(value: datetime) -> datetime:
    """Normalize SQL values; SQLite discards timezone information on read."""

    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else _aware(value, "time").isoformat()


__all__ = [
    "AcceptedAchievementDraftVerifier",
    "AchievementCandidateSubmissionService",
    "EngagementDraftReviewError",
    "EngagementDraftReviewNotFound",
    "EngagementDraftReviewRow",
    "EngagementDraftReviewStore",
    "EngagementReviewer",
    "InMemoryEngagementDraftReviewStore",
    "SqlAlchemyEngagementDraftReviewStore",
    "StoredEngagementDraft",
    "engagement_draft_id",
]
