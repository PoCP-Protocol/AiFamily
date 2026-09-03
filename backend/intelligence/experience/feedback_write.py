"""Append-only achievement feedback with an atomic Human Gate escalation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.intelligence.experience.achievement_persistence import (
    SqlAlchemyAchievementProjection,
)
from backend.intelligence.experience.contracts import (
    ExperienceProvenance,
    ExperienceScope,
    FeedbackSignal,
    FeedbackSignalType,
    FeedbackTargetType,
    ProvenanceKind,
)
from backend.intelligence.experience.feedback_response import (
    FEEDBACK_RESPONSE_ACTION_NAME,
    feedback_subject_digest,
)
from backend.intelligence.human_gate.contracts import (
    ActionProposal,
    ActorType,
    GateScope,
    ProposalSourceKind,
)
from backend.intelligence.human_gate.persistence import SqlAlchemyHumanGate
from backend.platform.audit.models import AuditEvent
from backend.platform.audit.recorder import AuditRecorder
from backend.platform.idempotency.keys import IdempotencyKey


class AchievementFeedbackError(Exception):
    """Base failure translated by the HTTP boundary."""


class AchievementFeedbackNotFound(AchievementFeedbackError):
    pass


class AchievementFeedbackConflict(AchievementFeedbackError):
    pass


class AchievementFeedbackValidation(AchievementFeedbackError):
    pass


@dataclass(frozen=True, slots=True)
class AchievementFeedbackReceipt:
    feedback_id: str
    achievement_id: str
    signal: FeedbackSignalType
    human_task_id: str | None
    replayed: bool
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class SqlAlchemyAchievementFeedbackApplication:
    """Persist feedback and optional escalation in one caller-owned transaction."""

    session_factory: async_sessionmaker[AsyncSession]
    escalation_ttl: timedelta = timedelta(days=7)

    def __post_init__(self) -> None:
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("feedback application requires async_sessionmaker")
        if self.escalation_ttl <= timedelta(0):
            raise ValueError("feedback escalation_ttl must be positive")

    async def record(
        self,
        *,
        scope: ExperienceScope,
        actor_id: str,
        achievement_id: str,
        signal: FeedbackSignalType,
        reason_code: str | None,
        idempotency_key: str,
        occurred_at: datetime,
    ) -> AchievementFeedbackReceipt:
        _validate_command(
            scope=scope,
            actor_id=actor_id,
            achievement_id=achievement_id,
            signal=signal,
            reason_code=reason_code,
            idempotency_key=idempotency_key,
            occurred_at=occurred_at,
        )
        request_hash = _request_hash(
            achievement_id=achievement_id,
            signal=signal,
            reason_code=reason_code,
            occurred_at=occurred_at,
        )
        feedback_id = _feedback_id(scope.tenant_id, idempotency_key)
        async with self.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "SELECT pg_advisory_xact_lock("
                    "hashtextextended(:lock_identity, 0))"
                ),
                {"lock_identity": f"{scope.tenant_id}:{idempotency_key}"},
            )
            existing = (
                await session.execute(
                    text(
                        """
                        SELECT feedback_id, achievement_id, signal, human_task_id,
                               request_hash, occurred_at
                        FROM ai_achievement_feedback
                        WHERE tenant_id=:tenant_id AND idempotency_key=:idempotency_key
                        FOR UPDATE
                        """
                    ),
                    {
                        "tenant_id": scope.tenant_id,
                        "idempotency_key": idempotency_key,
                    },
                )
            ).mappings().first()
            if existing is not None:
                if str(existing["request_hash"]) != request_hash:
                    raise AchievementFeedbackConflict("feedback_idempotency_conflict")
                return AchievementFeedbackReceipt(
                    feedback_id=str(existing["feedback_id"]),
                    achievement_id=str(existing["achievement_id"]),
                    signal=FeedbackSignalType(str(existing["signal"])),
                    human_task_id=(
                        str(existing["human_task_id"])
                        if existing["human_task_id"] is not None
                        else None
                    ),
                    replayed=True,
                    occurred_at=_aware(existing["occurred_at"]),
                )

            for subject_id in sorted(set(scope.subject_ids)):
                await session.execute(
                    text(
                        "SELECT pg_advisory_xact_lock("
                        "hashtextextended(:lock_identity, 0))"
                    ),
                    {
                        "lock_identity": (
                            f"experience-feedback-subject:{scope.tenant_id}:{subject_id}"
                        )
                    },
                )
            deletion_fence_count = await session.scalar(
                text(
                    "SELECT count(*) FROM ai_experience_feedback_deletion_fences "
                    "WHERE tenant_id=:tenant_id "
                    "AND subject_ref_digest = ANY(CAST(:digests AS text[]))"
                ),
                {
                    "tenant_id": scope.tenant_id,
                    "digests": [
                        feedback_subject_digest(scope.tenant_id, subject_id)
                        for subject_id in scope.subject_ids
                    ],
                },
            )
            if int(deletion_fence_count or 0) > 0:
                raise AchievementFeedbackValidation("feedback_subject_deletion_requested")

            achievements = await SqlAlchemyAchievementProjection(session).earned(scope)
            achievement = next(
                (item for item in achievements if item.achievement_id == achievement_id),
                None,
            )
            if achievement is None:
                raise AchievementFeedbackNotFound("achievement_not_found")

            provenance = ExperienceProvenance(
                provenance_ref=f"human-feedback:{feedback_id}",
                source_refs=(
                    f"achievement:{achievement.achievement_id}",
                    *achievement.evidence_refs,
                ),
                kind=ProvenanceKind.HUMAN,
                policy_version="achievement-feedback.v1",
                captured_at=occurred_at.astimezone(UTC),
            )
            feedback = FeedbackSignal(
                feedback_id=feedback_id,
                target_type=FeedbackTargetType.ACHIEVEMENT,
                target_id=achievement_id,
                signal=signal,
                scope=scope,
                idempotency_key=IdempotencyKey(
                    tenant_id=scope.tenant_id,
                    value=idempotency_key,
                ),
                provenance=provenance,
                reason_code=reason_code,
                occurred_at=occurred_at.astimezone(UTC),
            )
            human_task_id: str | None = None
            recorder = AuditRecorder()
            gate = SqlAlchemyHumanGate(session)
            if feedback.requires_human_review:
                proposal = _escalation_proposal(
                    feedback,
                    created_at=occurred_at.astimezone(UTC),
                    expires_at=occurred_at.astimezone(UTC) + self.escalation_ttl,
                )
                task = await gate.submit(
                    proposal,
                    recorder=recorder,
                    task_id=_human_task_id(feedback.feedback_id),
                )
                human_task_id = task.task_id

            await session.execute(
                text(
                    """
                    INSERT INTO ai_achievement_feedback(
                      feedback_id, achievement_id, target_type, signal,
                      tenant_id, region_id, family_id, subject_ids, purpose,
                      consent_version, data_class, locale, deletion_ref,
                      correlation_id, causation_id, actor_id, reason_code,
                      provenance_ref, provenance_payload, idempotency_key,
                      request_hash, human_task_id, occurred_at
                    ) VALUES (
                      :feedback_id, :achievement_id, :target_type, :signal,
                      :tenant_id, :region_id, :family_id, CAST(:subject_ids AS jsonb),
                      :purpose, :consent_version, :data_class, :locale,
                      :deletion_ref, :correlation_id, :causation_id, :actor_id,
                      :reason_code, :provenance_ref, CAST(:provenance_payload AS jsonb),
                      :idempotency_key, :request_hash, :human_task_id, :occurred_at
                    )
                    """
                ),
                {
                    "feedback_id": feedback.feedback_id,
                    "achievement_id": achievement_id,
                    "target_type": feedback.target_type.value,
                    "signal": feedback.signal.value,
                    "tenant_id": scope.tenant_id,
                    "region_id": scope.region_id,
                    "family_id": scope.family_id,
                    "subject_ids": json.dumps(list(scope.subject_ids)),
                    "purpose": scope.purpose,
                    "consent_version": scope.consent_version,
                    "data_class": str(scope.data_class),
                    "locale": scope.locale,
                    "deletion_ref": scope.deletion_ref.deletion_id,
                    "correlation_id": scope.correlation_id,
                    "causation_id": scope.causation_id,
                    "actor_id": actor_id,
                    "reason_code": reason_code,
                    "provenance_ref": provenance.provenance_ref,
                    "provenance_payload": json.dumps(
                        {
                            "source_refs": list(provenance.source_refs),
                            "kind": provenance.kind.value,
                            "policy_version": provenance.policy_version,
                        }
                    ),
                    "idempotency_key": idempotency_key,
                    "request_hash": request_hash,
                    "human_task_id": human_task_id,
                    "occurred_at": feedback.occurred_at,
                },
            )
            recorder.record(
                AuditEvent(
                    actor_id=actor_id,
                    tenant_id=scope.tenant_id,
                    action="RECORD_ACHIEVEMENT_FEEDBACK",
                    resource_type="FeedbackSignal",
                    resource_id=feedback.feedback_id,
                    reason=reason_code or signal.value,
                    correlation_id=scope.correlation_id,
                    after={
                        "achievement_id": achievement_id,
                        "signal": signal.value,
                        "human_task_id": human_task_id,
                        "boundary": "FEEDBACK_IS_NOT_FAMILY_FACT",
                    },
                )
            )
            await gate.flush_audit(recorder)
            return AchievementFeedbackReceipt(
                feedback_id=feedback.feedback_id,
                achievement_id=achievement_id,
                signal=signal,
                human_task_id=human_task_id,
                replayed=False,
                occurred_at=feedback.occurred_at,
            )


def _escalation_proposal(
    feedback: FeedbackSignal,
    *,
    created_at: datetime,
    expires_at: datetime,
) -> ActionProposal:
    return ActionProposal(
        proposal_id=f"feedback-escalation:{feedback.feedback_id}",
        draft_id=f"human-feedback:{feedback.feedback_id}",
        draft_status="DRAFT",
        action_name=FEEDBACK_RESPONSE_ACTION_NAME,
        action_arguments={
            "feedback_id": feedback.feedback_id,
            "achievement_id": feedback.target_id,
            "signal": feedback.signal.value,
        },
        scope=GateScope(
            tenant_id=feedback.scope.tenant_id,
            family_id=feedback.scope.family_id,
            subject_ids=feedback.scope.subject_ids,
            purpose=feedback.scope.purpose,
            consent_version=feedback.scope.consent_version,
            correlation_id=feedback.scope.correlation_id,
            region_id=feedback.scope.region_id,
            deletion_ref=feedback.scope.deletion_ref.deletion_id,
        ),
        allowed_actor_types=(ActorType.PROFESSIONAL, ActorType.OPERATOR),
        risk_level="LOW",
        provenance_ref=feedback.provenance.provenance_ref,
        created_at=created_at,
        expires_at=expires_at,
        source_kind=ProposalSourceKind.USER_REQUEST,
    )


def _validate_command(
    *,
    scope: ExperienceScope,
    actor_id: str,
    achievement_id: str,
    signal: FeedbackSignalType,
    reason_code: str | None,
    idempotency_key: str,
    occurred_at: datetime,
) -> None:
    if not isinstance(scope, ExperienceScope) or not scope.consent_granted:
        raise AchievementFeedbackValidation("active_experience_scope_required")
    if not actor_id.strip() or not achievement_id.strip():
        raise AchievementFeedbackValidation("feedback_identity_required")
    if signal not in {
        FeedbackSignalType.HELPFUL,
        FeedbackSignalType.NOT_HELPFUL,
        FeedbackSignalType.REQUEST_HUMAN,
    }:
        raise AchievementFeedbackValidation("feedback_signal_unsupported")
    if signal in {FeedbackSignalType.NOT_HELPFUL, FeedbackSignalType.REQUEST_HUMAN} and not (
        reason_code and reason_code.strip()
    ):
        raise AchievementFeedbackValidation("feedback_reason_code_required")
    if not idempotency_key.strip() or len(idempotency_key) > 256:
        raise AchievementFeedbackValidation("idempotency_key_invalid")
    _aware(occurred_at)


def _feedback_id(tenant_id: str, idempotency_key: str) -> str:
    digest = hashlib.sha256(f"{tenant_id}\x1f{idempotency_key}".encode()).hexdigest()
    return f"achievement-feedback:{digest}"


def _human_task_id(feedback_id: str) -> str:
    digest = hashlib.sha256(feedback_id.encode()).hexdigest()
    return f"human-task:feedback:{digest}"


def _request_hash(
    *, achievement_id: str,
    signal: FeedbackSignalType,
    reason_code: str | None,
    occurred_at: datetime,
) -> str:
    material = json.dumps(
        {
            "achievement_id": achievement_id,
            "signal": signal.value,
            "reason_code": reason_code,
            "occurred_at": occurred_at.astimezone(UTC).isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode()).hexdigest()


def _aware(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AchievementFeedbackValidation("feedback_occurred_at_timezone_required")
    return value.astimezone(UTC)


__all__ = [
    "AchievementFeedbackConflict",
    "AchievementFeedbackError",
    "AchievementFeedbackNotFound",
    "AchievementFeedbackReceipt",
    "AchievementFeedbackValidation",
    "SqlAlchemyAchievementFeedbackApplication",
]
