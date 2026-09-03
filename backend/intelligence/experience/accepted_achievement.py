"""Human-confirmed landing for AI engagement achievement candidates.

The engagement model may suggest an achievement candidate, but the candidate
is only a DRAFT.  This module binds it to the exact experience scope and event
evidence, sends a Named Action through Human Gate, and projects the result only
after a human actor accepts it.  The projection is an experience read model;
it never mutates a Family/Journey/Service/Commerce fact.
"""

from __future__ import annotations

import hashlib
import inspect
from collections.abc import Awaitable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast

from backend.intelligence.experience.achievement import (
    Achievement,
    AchievementKey,
)
from backend.intelligence.experience.contracts import (
    DeletionRef,
    ExperienceProvenance,
    ExperienceScope,
    ProvenanceKind,
)
from backend.intelligence.experience.engagement import EngagementDraft
from backend.intelligence.experience.projections import (
    AchievementNotificationProjection,
    ExperienceAnalyticsProjection,
)
from backend.intelligence.human_gate.contracts import (
    ActionProposal,
    ActorType,
    GateScope,
    NamedActionRequest,
)
from backend.intelligence.human_gate.errors import HumanGateError
from backend.intelligence.model_gateway.contracts import AiProvenance, DataClass
from backend.intelligence.tool_runtime.accepted_dispatch import ActionExecutionReceipt
from backend.platform.audit import AuditEvent, AuditRecorder
from backend.platform.idempotency.keys import IdempotencyKey

ACHIEVEMENT_ACTION_NAME = "PUBLISH_EXPERIENCE_ACHIEVEMENT"


class AcceptedAchievementError(ValueError):
    """Raised when an AI achievement candidate cannot cross Human Gate."""


class AchievementProjectionWriter(Protocol):
    def append(self, achievement: Achievement) -> Achievement | Awaitable[Achievement]: ...


class AcceptedAchievementVerifier(Protocol):
    def verify(self, request: NamedActionRequest) -> None | Awaitable[None]: ...


def build_achievement_action_proposal(
    draft: EngagementDraft,
    *,
    candidate_id: str,
    scope: ExperienceScope,
    draft_id: str,
    proposal_id: str,
    now: datetime | None = None,
    ttl: timedelta = timedelta(hours=24),
) -> ActionProposal:
    """Convert one AI candidate to a reviewable, scope-bound Named Action."""

    if not isinstance(draft, EngagementDraft):
        raise AcceptedAchievementError("ENGAGEMENT_DRAFT_REQUIRED")
    if not isinstance(scope, ExperienceScope):
        raise AcceptedAchievementError("EXPERIENCE_SCOPE_REQUIRED")
    if not candidate_id or not draft_id or not proposal_id:
        raise AcceptedAchievementError("ACHIEVEMENT_PROPOSAL_IDENTIFIERS_REQUIRED")
    candidate = next(
        (
            item
            for item in draft.achievement_candidates
            if item.get("candidate_id") == candidate_id
        ),
        None,
    )
    if candidate is None:
        raise AcceptedAchievementError("ACHIEVEMENT_CANDIDATE_NOT_FOUND")
    text = candidate.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        raise AcceptedAchievementError("ACHIEVEMENT_CANDIDATE_TEXT_INVALID")
    evidence_refs = _evidence_refs(candidate.get("evidence_refs"), draft.evidence_event_ids)
    occurrence_id = _occurrence_id(candidate.get("occurrence_id"), evidence_refs)
    provenance = _experience_provenance(draft.draft.provenance, draft.request_id, evidence_refs)
    created_at = now or datetime.now(UTC)
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise AcceptedAchievementError("ACHIEVEMENT_PROPOSAL_TIMEZONE_REQUIRED")
    if ttl <= timedelta(0):
        raise AcceptedAchievementError("ACHIEVEMENT_PROPOSAL_TTL_INVALID")
    if draft.scope is None:
        raise AcceptedAchievementError("ENGAGEMENT_SCOPE_REQUIRED")
    if not _same_scope(draft.scope, scope):
        raise AcceptedAchievementError("ACHIEVEMENT_SCOPE_MISMATCH")
    return ActionProposal(
        proposal_id=proposal_id,
        draft_id=draft_id,
        draft_status="DRAFT",
        action_name=ACHIEVEMENT_ACTION_NAME,
        action_arguments={
            "candidate_id": candidate_id,
            "engagement_draft_id": draft_id,
            "title": "来自这次行动的成长时刻",
            "message": text.strip(),
            "achievement_key": AchievementKey.AI_EVIDENCE_MOMENT.value,
            "evidence_refs": list(evidence_refs),
            "occurrence_id": occurrence_id,
            "experience_scope": _scope_payload(scope),
            "experience_provenance": _provenance_payload(provenance),
        },
        scope=_gate_scope(scope),
        allowed_actor_types=(ActorType.GUARDIAN, ActorType.PROFESSIONAL),
        risk_level="MEDIUM",
        provenance_ref=provenance.provenance_ref,
        created_at=created_at,
        expires_at=created_at + ttl,
    )


class ExperienceAchievementActionHandler:
    """Project a human-accepted AI achievement into the read model."""

    def __init__(
        self,
        projection: AchievementProjectionWriter,
        *,
        recorder: AuditRecorder,
        notifications: AchievementNotificationProjection | None = None,
        analytics: ExperienceAnalyticsProjection | None = None,
        verifier: AcceptedAchievementVerifier | None = None,
    ) -> None:
        self._projection = projection
        self._recorder = recorder
        self._notifications = notifications
        self._analytics = analytics
        self._verifier = verifier

    async def __call__(self, request: NamedActionRequest) -> ActionExecutionReceipt:
        try:
            if request.action_name != ACHIEVEMENT_ACTION_NAME:
                raise AcceptedAchievementError("ACHIEVEMENT_ACTION_UNSUPPORTED")
            if self._verifier is not None:
                verified = self._verifier.verify(request)
                if inspect.isawaitable(verified):
                    await verified
            args = request.action_arguments
            scope = _scope_from_payload(
                _mapping(args.get("experience_scope"), "experience_scope")
            )
            _assert_gate_scope(request.scope, scope)
            provenance = _provenance_from_payload(
                _mapping(args.get("experience_provenance"), "experience_provenance")
            )
            title = _required_text(args.get("title"), "title")
            message = _required_text(args.get("message"), "message")
            evidence_refs = _evidence_refs(args.get("evidence_refs"), ())
            occurrence_id = _occurrence_id(args.get("occurrence_id"), evidence_refs)
            if args.get("achievement_key") != AchievementKey.AI_EVIDENCE_MOMENT.value:
                raise AcceptedAchievementError("ACHIEVEMENT_KEY_UNSUPPORTED")
            achievement_id = _achievement_id(scope, occurrence_id)
            achievement = Achievement(
                achievement_id=achievement_id,
                key=AchievementKey.AI_EVIDENCE_MOMENT,
                title=title,
                message=message,
                scope=scope,
                evidence_refs=evidence_refs,
                provenance=provenance,
                idempotency_key=IdempotencyKey(
                    scope.tenant_id, f"accepted-achievement:{request.request_id}"
                ),
                earned_at=datetime.now(UTC),
                basis="ACTION_COMPLETED",
                occurrence_id=occurrence_id,
            )
            persisted = self._projection.append(achievement)
            if inspect.isawaitable(persisted):
                persisted = await persisted
            if self._analytics is not None:
                recorded = self._analytics.record_achievement(persisted)
                if inspect.isawaitable(recorded):
                    await recorded
            if self._notifications is not None:
                published = self._notifications.publish(persisted)
                if inspect.isawaitable(published):
                    await published
            self._recorder.record(
                AuditEvent(
                    actor_id=request.actor_id,
                    tenant_id=scope.tenant_id,
                    action=ACHIEVEMENT_ACTION_NAME,
                    resource_type="AchievementProjection",
                    resource_id=persisted.achievement_id,
                    reason="human-confirmed evidence-bound engagement achievement",
                    correlation_id=scope.correlation_id,
                    after={
                        "achievement_key": persisted.key.value,
                        "evidence_count": len(evidence_refs),
                    },
                )
            )
            await _flush_and_commit(self._projection, self._recorder)
            return ActionExecutionReceipt(
                request_id=request.request_id,
                action_name=request.action_name,
                result_ref=persisted.achievement_id,
            )
        except BaseException:
            rollback = getattr(self._projection, "rollback", None)
            if callable(rollback):
                result = rollback()
                if inspect.isawaitable(result):
                    await result
            raise


def _same_scope(left: ExperienceScope, right: ExperienceScope) -> bool:
    return (
        left.global_id == right.global_id
        and left.tenant_id == right.tenant_id
        and left.region_id == right.region_id
        and left.family_id == right.family_id
        and left.subject_ids == right.subject_ids
        and left.purpose == right.purpose
        and left.consent_version == right.consent_version
        and left.consent_granted == right.consent_granted
        and left.data_class == right.data_class
        and left.locale == right.locale
        and left.content_locale == right.content_locale
        and left.model_locale == right.model_locale
        and left.policy_locale == right.policy_locale
        and left.deletion_ref == right.deletion_ref
        and left.correlation_id == right.correlation_id
        and left.causation_id == right.causation_id
    )


def _evidence_refs(value: object, allowed_event_ids: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise AcceptedAchievementError("ACHIEVEMENT_EVIDENCE_REQUIRED")
    allowed = set(allowed_event_ids)
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise AcceptedAchievementError("ACHIEVEMENT_EVIDENCE_INVALID")
        ref = item.strip()
        event_id = ref.removeprefix("experience-event:")
        if allowed_event_ids and event_id not in allowed:
            raise AcceptedAchievementError("ACHIEVEMENT_EVIDENCE_NOT_REAL_EVENT")
        if not ref.startswith("experience-event:"):
            ref = f"experience-event:{ref}"
        result.append(ref)
    if len(set(result)) != len(result):
        raise AcceptedAchievementError("ACHIEVEMENT_EVIDENCE_DUPLICATE")
    return tuple(result)


def _gate_scope(scope: ExperienceScope) -> GateScope:
    return GateScope(
        tenant_id=scope.tenant_id,
        family_id=scope.family_id,
        subject_ids=scope.subject_ids,
        purpose=scope.purpose,
        consent_version=scope.consent_version,
        correlation_id=scope.correlation_id,
    )


def _assert_gate_scope(gate_scope: GateScope, scope: ExperienceScope) -> None:
    if (
        gate_scope.tenant_id != scope.tenant_id
        or gate_scope.family_id != scope.family_id
        or gate_scope.subject_ids != scope.subject_ids
        or gate_scope.purpose != scope.purpose
        or gate_scope.consent_version != scope.consent_version
        or gate_scope.correlation_id != scope.correlation_id
    ):
        raise HumanGateError("INVALID_CONTRACT", "accepted achievement scope mismatch")


def _experience_provenance(
    provenance: AiProvenance,
    request_id: str,
    evidence_refs: tuple[str, ...],
) -> ExperienceProvenance:
    return ExperienceProvenance(
        provenance_ref=f"ai-engagement:{request_id}",
        source_refs=evidence_refs,
        kind=ProvenanceKind.AI_DRAFT,
        policy_version="experience-achievement.v1",
        context_snapshot_ref=provenance.context_snapshot_ref,
        model_attempt_ref=f"model-request:{request_id}",
        captured_at=provenance.generated_at,
    )


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


def _scope_from_payload(raw: Mapping[str, Any]) -> ExperienceScope:
    deletion = _mapping(raw.get("deletion_ref"), "deletion_ref")
    requested_at = deletion.get("requested_at")
    return ExperienceScope(
        global_id=_required_text(raw.get("global_id"), "global_id"),
        tenant_id=_required_text(raw.get("tenant_id"), "tenant_id"),
        region_id=_required_text(raw.get("region_id"), "region_id"),
        family_id=_required_text(raw.get("family_id"), "family_id"),
        subject_ids=_text_tuple(raw.get("subject_ids"), "subject_ids"),
        purpose=_required_text(raw.get("purpose"), "purpose"),
        consent_version=_required_text(raw.get("consent_version"), "consent_version"),
        consent_granted=_required_bool(raw.get("consent_granted"), "consent_granted"),
        data_class=cast(DataClass, _required_text(raw.get("data_class"), "data_class")),
        locale=_required_text(raw.get("locale"), "locale"),
        content_locale=_required_text(raw.get("content_locale"), "content_locale"),
        model_locale=_required_text(raw.get("model_locale"), "model_locale"),
        policy_locale=_required_text(raw.get("policy_locale"), "policy_locale"),
        deletion_ref=DeletionRef(
            deletion_id=_required_text(deletion.get("deletion_id"), "deletion_id"),
            retention_policy=_required_text(deletion.get("retention_policy"), "retention_policy"),
            requested_at=_parse_datetime(requested_at) if requested_at is not None else None,
        ),
        correlation_id=_required_text(raw.get("correlation_id"), "correlation_id"),
        causation_id=_required_text(raw.get("causation_id"), "causation_id"),
    )


def _provenance_payload(provenance: ExperienceProvenance) -> dict[str, Any]:
    return {
        "provenance_ref": provenance.provenance_ref,
        "source_refs": list(provenance.source_refs),
        "kind": provenance.kind.value,
        "policy_version": provenance.policy_version,
        "context_snapshot_ref": provenance.context_snapshot_ref,
        "model_attempt_ref": provenance.model_attempt_ref,
        "captured_at": provenance.captured_at.isoformat(),
    }


def _provenance_from_payload(raw: Mapping[str, Any]) -> ExperienceProvenance:
    return ExperienceProvenance(
        provenance_ref=_required_text(raw.get("provenance_ref"), "provenance_ref"),
        source_refs=_text_tuple(raw.get("source_refs"), "source_refs"),
        kind=ProvenanceKind(_required_text(raw.get("kind"), "kind")),
        policy_version=_required_text(raw.get("policy_version"), "policy_version"),
        context_snapshot_ref=_required_text(
            raw.get("context_snapshot_ref"), "context_snapshot_ref"
        ),
        model_attempt_ref=_required_text(raw.get("model_attempt_ref"), "model_attempt_ref"),
        captured_at=_parse_datetime(raw.get("captured_at")),
    )


async def _flush_and_commit(
    projection: AchievementProjectionWriter,
    recorder: AuditRecorder,
) -> None:
    flush = getattr(projection, "flush_audit", None)
    if callable(flush):
        result = flush(recorder)
        if inspect.isawaitable(result):
            await result
    commit = getattr(projection, "commit", None)
    if callable(commit):
        result = commit()
        if inspect.isawaitable(result):
            await result


def _achievement_id(scope: ExperienceScope, occurrence_id: str) -> str:
    token = hashlib.sha256(occurrence_id.encode("utf-8")).hexdigest()[:16]
    return f"achievement:{scope.family_id}:ai_evidence_moment:{token}"


def _occurrence_id(value: object, evidence_refs: tuple[str, ...]) -> str:
    """Return a stable, evidence-derived identity for repeatable moments."""

    encoded = "|".join(sorted(evidence_refs))
    evidence_token = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]
    if value is not None:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 256:
            raise AcceptedAchievementError("ACHIEVEMENT_OCCURRENCE_INVALID")
        prefix = value.strip()
        return f"{prefix[:200]}:evidence:{evidence_token}"
    return f"evidence:{evidence_token}"


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AcceptedAchievementError(f"{name}_INVALID")
    return value


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AcceptedAchievementError(f"{name}_REQUIRED")
    return value.strip()


def _text_tuple(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise AcceptedAchievementError(f"{name}_REQUIRED")
    values = tuple(_required_text(item, name) for item in value)
    if len(set(values)) != len(values):
        raise AcceptedAchievementError(f"{name}_DUPLICATE")
    return values


def _required_bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise AcceptedAchievementError(f"{name}_REQUIRED")
    return value


def _parse_datetime(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise AcceptedAchievementError("TIMESTAMP_REQUIRED")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise AcceptedAchievementError("TIMESTAMP_INVALID") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AcceptedAchievementError("TIMESTAMP_TIMEZONE_REQUIRED")
    return parsed


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


__all__ = [
    "ACHIEVEMENT_ACTION_NAME",
    "AcceptedAchievementError",
    "AcceptedAchievementVerifier",
    "ExperienceAchievementActionHandler",
    "build_achievement_action_proposal",
]
