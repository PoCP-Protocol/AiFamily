"""Accepted human-response landing and subject deletion for Experience feedback."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.intelligence.human_gate.contracts import ActorType, NamedActionRequest
from backend.intelligence.tool_runtime.accepted_dispatch import ActionExecutionReceipt
from backend.platform.audit.models import AuditEvent
from backend.platform.audit.recorder import AuditRecorder
from backend.platform.consent.versioning import (
    ConsentVersionEntry,
    canonical_consent_version,
)

FEEDBACK_RESPONSE_ACTION_NAME = "RESPOND_TO_EXPERIENCE_FEEDBACK"
FEEDBACK_RESPONSE_RESOLUTION_CODE = "HUMAN_FOLLOWUP_QUEUED"


class ExperienceFeedbackResponseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FeedbackDeletionProof:
    proof_id: str
    deletion_ref_digest: str
    deleted_feedback: int
    deleted_resolutions: int
    deleted_deliveries: int
    deleted_human_tasks: int
    completed_at: datetime


class ExperienceFeedbackResponseActionHandler:
    """Append a response receipt after a Professional/Operator accepts the task."""

    def __init__(self, session: AsyncSession, *, recorder: AuditRecorder) -> None:
        self._session = session
        self._recorder = recorder

    async def __call__(self, request: NamedActionRequest) -> ActionExecutionReceipt:
        try:
            if request.action_name != FEEDBACK_RESPONSE_ACTION_NAME:
                raise ExperienceFeedbackResponseError("FEEDBACK_RESPONSE_ACTION_UNSUPPORTED")
            feedback_id = _required(request.action_arguments.get("feedback_id"), "feedback_id")
            achievement_id = _required(
                request.action_arguments.get("achievement_id"), "achievement_id"
            )
            if request.actor_type not in {ActorType.PROFESSIONAL, ActorType.OPERATOR}:
                raise ExperienceFeedbackResponseError("FEEDBACK_RESPONSE_REVIEWER_FORBIDDEN")
            preview = (
                await self._session.execute(
                    text(
                        """
                        SELECT subject_ids
                        FROM ai_achievement_feedback
                        WHERE feedback_id=:feedback_id
                        """
                    ),
                    {"feedback_id": feedback_id},
                )
            ).mappings().first()
            if preview is None:
                raise ExperienceFeedbackResponseError("FEEDBACK_RESPONSE_SOURCE_NOT_FOUND")
            subjects = tuple(str(item) for item in (preview["subject_ids"] or ()))
            await _lock_subjects(
                self._session,
                tenant_id=request.scope.tenant_id,
                subject_ids=subjects,
            )
            row = (
                await self._session.execute(
                    text(
                        """
                        SELECT f.feedback_id, f.achievement_id, f.signal, f.tenant_id,
                               f.region_id, f.family_id, f.subject_ids, f.purpose,
                               f.consent_version, f.deletion_ref, f.human_task_id,
                               f.provenance_ref, t.status AS task_status,
                               t.proposal_id AS task_proposal_id,
                               t.provenance_ref AS task_provenance_ref,
                               t.proposal_payload, t.decision_payload,
                               t.action_request_payload
                        FROM ai_achievement_feedback AS f
                        JOIN ai_human_tasks AS t ON t.task_id=f.human_task_id
                        WHERE f.feedback_id=:feedback_id
                        FOR UPDATE OF f, t
                        """
                    ),
                    {"feedback_id": feedback_id},
                )
            ).mappings().first()
            if row is None:
                raise ExperienceFeedbackResponseError("FEEDBACK_RESPONSE_SOURCE_NOT_FOUND")
            _assert_request_scope(request, row, achievement_id=achievement_id)
            _assert_human_task_binding(request, row)

            resolution_id = _resolution_id(request.request_id)
            existing = (
                await self._session.execute(
                    text(
                        """
                        SELECT resolution_id, feedback_id
                        FROM ai_experience_feedback_resolutions
                        WHERE request_id=:request_id
                        FOR UPDATE
                        """
                    ),
                    {"request_id": request.request_id},
                )
            ).first()
            if existing is not None:
                if str(existing.feedback_id) != feedback_id:
                    raise ExperienceFeedbackResponseError("FEEDBACK_RESPONSE_REPLAY_MISMATCH")
                return ActionExecutionReceipt(
                    request_id=request.request_id,
                    action_name=request.action_name,
                    result_ref=str(existing.resolution_id),
                )

            if await _subjects_are_fenced(
                self._session,
                tenant_id=request.scope.tenant_id,
                subject_ids=subjects,
            ):
                raise ExperienceFeedbackResponseError("FEEDBACK_RESPONSE_DELETION_PENDING")
            consent_matches, birth_dates = await _current_consent_matches(self._session, row)
            if not consent_matches:
                raise ExperienceFeedbackResponseError("FEEDBACK_RESPONSE_CONSENT_STALE")

            now = datetime.now(UTC)
            approval_ref = _approval_ref(request.decision_id)
            for subject_id in subjects:
                birth_date = birth_dates.get(subject_id)
                if birth_date is None:
                    raise ExperienceFeedbackResponseError("FEEDBACK_RESPONSE_SUBJECT_UNKNOWN")
                self._recorder.record_read(
                    actor_id=request.actor_id,
                    tenant_id=request.scope.tenant_id,
                    action="READ_EXPERIENCE_FEEDBACK_FOR_FOLLOWUP",
                    resource_type="FeedbackSignal",
                    resource_id=feedback_id,
                    subject_person_id=subject_id,
                    accessed_fields=("achievement_id", "signal", "provenance_ref"),
                    access_purpose=request.scope.purpose,
                    reason="accepted Human Gate request requires feedback review",
                    correlation_id=request.scope.correlation_id,
                    subject_is_minor=_age_on(birth_date, now.date()) < 18,
                    approval_ref=approval_ref,
                )
            await self._session.execute(
                text(
                    """
                    INSERT INTO ai_experience_feedback_resolutions(
                      resolution_id, feedback_id, request_id, human_task_id,
                      tenant_id, family_id, subject_ids, purpose, consent_version,
                      deletion_ref, responder_actor_id, resolution_code, resolved_at
                    ) VALUES (
                      :resolution_id, :feedback_id, :request_id, :human_task_id,
                      :tenant_id, :family_id, CAST(:subject_ids AS jsonb), :purpose,
                      :consent_version, :deletion_ref, :responder_actor_id,
                      :resolution_code, :resolved_at
                    )
                    """
                ),
                {
                    "resolution_id": resolution_id,
                    "feedback_id": feedback_id,
                    "request_id": request.request_id,
                    "human_task_id": request.task_id,
                    "tenant_id": request.scope.tenant_id,
                    "family_id": request.scope.family_id,
                    "subject_ids": json.dumps(list(request.scope.subject_ids)),
                    "purpose": request.scope.purpose,
                    "consent_version": request.scope.consent_version,
                    "deletion_ref": request.scope.deletion_ref,
                    "responder_actor_id": request.actor_id,
                    "resolution_code": FEEDBACK_RESPONSE_RESOLUTION_CODE,
                    "resolved_at": now,
                },
            )
            self._recorder.record(
                AuditEvent(
                    actor_id=request.actor_id,
                    tenant_id=request.scope.tenant_id,
                    action=FEEDBACK_RESPONSE_ACTION_NAME,
                    resource_type="ExperienceFeedbackResolution",
                    resource_id=resolution_id,
                    reason="professional accepted the family's request for a human response",
                    correlation_id=request.scope.correlation_id,
                    after={
                        "feedback_id": feedback_id,
                        "resolution_code": FEEDBACK_RESPONSE_RESOLUTION_CODE,
                        "boundary": "RESOLUTION_IS_NOT_FAMILY_FACT",
                    },
                )
            )
            await self._recorder.flush(self._session)
            await self._session.commit()
            return ActionExecutionReceipt(
                request_id=request.request_id,
                action_name=request.action_name,
                result_ref=resolution_id,
            )
        except BaseException:
            await self._session.rollback()
            raise


@dataclass(frozen=True, slots=True)
class SqlAlchemyExperienceFeedbackDeletionService:
    session_factory: async_sessionmaker[AsyncSession]

    async def delete_subject(
        self,
        *,
        tenant_id: str,
        subject_id: str,
        deletion_ref: str,
        completed_at: datetime | None = None,
    ) -> FeedbackDeletionProof:
        if not all(value.strip() for value in (tenant_id, subject_id, deletion_ref)):
            raise ValueError("feedback deletion scope is required")
        now = completed_at or datetime.now(UTC)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("feedback deletion time must be timezone-aware")
        proof_id = _deletion_proof_id(tenant_id, subject_id, deletion_ref)
        subject_ref_digest = feedback_subject_digest(tenant_id, subject_id)
        deletion_ref_digest = _digest(deletion_ref)
        async with self.session_factory() as session, session.begin():
            await _lock_subjects(session, tenant_id=tenant_id, subject_ids=(subject_id,))
            existing = (
                await session.execute(
                    text(
                        """
                        SELECT proof_id, deletion_ref_digest, deleted_feedback,
                               deleted_resolutions, deleted_deliveries,
                               deleted_human_tasks, completed_at
                        FROM ai_achievement_feedback_deletion_proofs
                        WHERE proof_id=:proof_id
                        """
                    ),
                    {"proof_id": proof_id},
                )
            ).mappings().first()
            if existing is not None:
                return _proof(existing)

            await session.execute(
                text(
                    """
                    INSERT INTO ai_experience_feedback_deletion_fences(
                      tenant_id, subject_ref_digest, deletion_ref_digest, fenced_at
                    ) VALUES (
                      :tenant_id, :subject_ref_digest, :deletion_ref_digest, :fenced_at
                    ) ON CONFLICT (tenant_id, subject_ref_digest) DO NOTHING
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "subject_ref_digest": subject_ref_digest,
                    "deletion_ref_digest": deletion_ref_digest,
                    "fenced_at": now.astimezone(UTC),
                },
            )

            candidates = (
                await session.execute(
                    text(
                        """
                        SELECT feedback_id, human_task_id
                        FROM ai_achievement_feedback
                        WHERE tenant_id=:tenant_id
                          AND subject_ids @> CAST(:subject_ids AS jsonb)
                        FOR UPDATE
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "subject_ids": json.dumps([subject_id]),
                    },
                )
            ).mappings().all()
            feedback_ids = [str(row["feedback_id"]) for row in candidates]
            task_ids = [
                str(row["human_task_id"])
                for row in candidates
                if row["human_task_id"] is not None
            ]
            deleted_deliveries = 0
            deleted_resolutions = 0
            deleted_feedback = 0
            deleted_human_tasks = 0
            if task_ids:
                result = await session.execute(
                    text(
                        "DELETE FROM ai_accepted_action_deliveries "
                        "WHERE task_id = ANY(CAST(:task_ids AS text[]))"
                    ),
                    {"task_ids": task_ids},
                )
                deleted_deliveries = int(result.rowcount or 0)
            if feedback_ids:
                await session.execute(text("SET LOCAL aifamily.deletion_mode = 'subject_request'"))
                result = await session.execute(
                    text(
                        "DELETE FROM ai_experience_feedback_resolutions "
                        "WHERE feedback_id = ANY(CAST(:feedback_ids AS text[]))"
                    ),
                    {"feedback_ids": feedback_ids},
                )
                deleted_resolutions = int(result.rowcount or 0)
                result = await session.execute(
                    text(
                        "DELETE FROM ai_achievement_feedback "
                        "WHERE feedback_id = ANY(CAST(:feedback_ids AS text[]))"
                    ),
                    {"feedback_ids": feedback_ids},
                )
                deleted_feedback = int(result.rowcount or 0)
            if task_ids:
                result = await session.execute(
                    text(
                        "DELETE FROM ai_human_tasks "
                        "WHERE task_id = ANY(CAST(:task_ids AS text[]))"
                    ),
                    {"task_ids": task_ids},
                )
                deleted_human_tasks = int(result.rowcount or 0)
            await _assert_zero_residuals(
                session,
                tenant_id=tenant_id,
                subject_id=subject_id,
                feedback_ids=feedback_ids,
                task_ids=task_ids,
            )
            proof = FeedbackDeletionProof(
                proof_id=proof_id,
                deletion_ref_digest=deletion_ref_digest,
                deleted_feedback=deleted_feedback,
                deleted_resolutions=deleted_resolutions,
                deleted_deliveries=deleted_deliveries,
                deleted_human_tasks=deleted_human_tasks,
                completed_at=now.astimezone(UTC),
            )
            await session.execute(
                text(
                    """
                    INSERT INTO ai_achievement_feedback_deletion_proofs(
                      proof_id, tenant_id, subject_ref_digest, deletion_ref_digest,
                      deleted_feedback, deleted_resolutions, deleted_deliveries,
                      deleted_human_tasks, completed_at
                    ) VALUES (
                      :proof_id, :tenant_id, :subject_ref_digest, :deletion_ref_digest,
                      :deleted_feedback, :deleted_resolutions, :deleted_deliveries,
                      :deleted_human_tasks, :completed_at
                    )
                    """
                ),
                {
                    "proof_id": proof.proof_id,
                    "tenant_id": tenant_id,
                    "subject_ref_digest": subject_ref_digest,
                    "deletion_ref_digest": proof.deletion_ref_digest,
                    "deleted_feedback": proof.deleted_feedback,
                    "deleted_resolutions": proof.deleted_resolutions,
                    "deleted_deliveries": proof.deleted_deliveries,
                    "deleted_human_tasks": proof.deleted_human_tasks,
                    "completed_at": proof.completed_at,
                },
            )
            recorder = AuditRecorder()
            recorder.record(
                AuditEvent(
                    actor_id="system:experience-feedback-deletion",
                    tenant_id=tenant_id,
                    action="DELETE_EXPERIENCE_FEEDBACK_SUBJECT",
                    resource_type="ExperienceFeedbackDeletionProof",
                    resource_id=proof.proof_id,
                    reason="subject-scoped deletion request",
                    correlation_id=f"feedback-delete:{deletion_ref_digest[:32]}",
                    after={
                        "deleted_feedback": proof.deleted_feedback,
                        "deleted_resolutions": proof.deleted_resolutions,
                        "deleted_deliveries": proof.deleted_deliveries,
                        "deleted_human_tasks": proof.deleted_human_tasks,
                    },
                )
            )
            await recorder.flush(session)
            return proof


def _assert_request_scope(
    request: NamedActionRequest,
    row,
    *,
    achievement_id: str,
) -> None:
    subjects = tuple(str(item) for item in (row["subject_ids"] or ()))
    if (
        str(row["signal"]) != "request_human"
        or str(row["achievement_id"]) != achievement_id
        or str(row["human_task_id"]) != request.task_id
        or str(row["tenant_id"]) != request.scope.tenant_id
        or str(row["family_id"]) != request.scope.family_id
        or subjects != request.scope.subject_ids
        or str(row["purpose"]) != request.scope.purpose
        or str(row["consent_version"]) != request.scope.consent_version
        or str(row["region_id"]) != request.scope.region_id
        or str(row["deletion_ref"]) != request.scope.deletion_ref
        or str(row["provenance_ref"]) != request.provenance_ref
    ):
        raise ExperienceFeedbackResponseError("FEEDBACK_RESPONSE_SCOPE_MISMATCH")


def _assert_human_task_binding(request: NamedActionRequest, row) -> None:
    proposal = row["proposal_payload"] or {}
    decision = row["decision_payload"] or {}
    action_request = row["action_request_payload"] or {}
    expected_arguments = {
        "feedback_id": str(row["feedback_id"]),
        "achievement_id": str(row["achievement_id"]),
        "signal": "request_human",
    }
    if (
        str(row["task_status"]) != "DECIDED"
        or str(row["task_proposal_id"]) != request.proposal_id
        or str(row["task_provenance_ref"]) != request.provenance_ref
        or proposal.get("source_kind") != "USER_REQUEST"
        or proposal.get("action_name") != FEEDBACK_RESPONSE_ACTION_NAME
        or proposal.get("action_arguments") != expected_arguments
        or decision.get("decision_id") != request.decision_id
        or decision.get("actor_id") != request.actor_id
        or decision.get("actor_type") != request.actor_type.value
        or decision.get("outcome") != "ACCEPT"
        or action_request.get("request_id") != request.request_id
        or action_request.get("action_name") != request.action_name
        or action_request.get("action_arguments") != expected_arguments
        or action_request.get("provenance_ref") != request.provenance_ref
    ):
        raise ExperienceFeedbackResponseError("FEEDBACK_RESPONSE_HUMAN_GATE_MISMATCH")


async def _current_consent_matches(
    session: AsyncSession, feedback
) -> tuple[bool, dict[str, date]]:
    subject_ids = tuple(str(item) for item in (feedback["subject_ids"] or ()))
    rows = (
        await session.execute(
            text(
                """
                SELECT c.consent_id, c.subject_person_id, c.guardian_person_id,
                       c.status, c.policy_version, c.granted_at, c.withdrawn_at,
                       p.birth_date
                FROM consents AS c
                JOIN persons AS p ON p.person_id=c.subject_person_id
                JOIN tenant_family_bindings AS tfb
                  ON tfb.family_id=c.family_id
                 AND CAST(tfb.tenant_id AS text)=:tenant_id
                 AND tfb.status='ACTIVE'
                 AND tfb.effective_from <= CURRENT_TIMESTAMP
                 AND (tfb.effective_to IS NULL OR tfb.effective_to > CURRENT_TIMESTAMP)
                WHERE CAST(c.family_id AS text)=:family_id
                  AND CAST(c.subject_person_id AS text) = ANY(CAST(:subject_ids AS text[]))
                  AND c.purpose=:purpose
                ORDER BY c.subject_person_id, c.granted_at DESC, c.consent_id DESC
                """
            ),
            {
                "family_id": feedback["family_id"],
                "tenant_id": feedback["tenant_id"],
                "subject_ids": list(subject_ids),
                "purpose": str(feedback["purpose"]).upper(),
            },
        )
    ).mappings().all()
    if not rows:
        return False, {}
    active_subjects = {
        str(row["subject_person_id"])
        for row in rows
        if str(row["status"]).upper() == "GRANTED" and row["withdrawn_at"] is None
    }
    if active_subjects != set(subject_ids):
        return False, {}
    entries: list[ConsentVersionEntry] = []
    birth_dates: dict[str, date] = {}
    for row in rows:
        granted_at = row["granted_at"]
        birth_date = row["birth_date"]
        if not isinstance(granted_at, datetime) or not isinstance(birth_date, date):
            return False, {}
        birth_dates[str(row["subject_person_id"])] = birth_date
        age = granted_at.date().year - birth_date.year - (
            (granted_at.date().month, granted_at.date().day)
            < (birth_date.month, birth_date.day)
        )
        entries.append(
            ConsentVersionEntry(
                consent_id=str(row["consent_id"]),
                status=str(row["status"]),
                granted_at=granted_at,
                guardian_person_id=str(row["guardian_person_id"]),
                subject_age=age,
                policy_version=str(row["policy_version"]),
            )
        )
    return (
        canonical_consent_version(entries) == str(feedback["consent_version"]),
        birth_dates,
    )


async def _lock_subjects(
    session: AsyncSession, *, tenant_id: str, subject_ids: tuple[str, ...]
) -> None:
    for subject_id in sorted(set(subject_ids)):
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
            {"identity": f"experience-feedback-subject:{tenant_id}:{subject_id}"},
        )


async def _subjects_are_fenced(
    session: AsyncSession, *, tenant_id: str, subject_ids: tuple[str, ...]
) -> bool:
    digests = [feedback_subject_digest(tenant_id, subject_id) for subject_id in subject_ids]
    if not digests:
        return False
    count = await session.scalar(
        text(
            "SELECT count(*) FROM ai_experience_feedback_deletion_fences "
            "WHERE tenant_id=:tenant_id "
            "AND subject_ref_digest = ANY(CAST(:digests AS text[]))"
        ),
        {"tenant_id": tenant_id, "digests": digests},
    )
    return int(count or 0) > 0


async def _assert_zero_residuals(
    session: AsyncSession,
    *,
    tenant_id: str,
    subject_id: str,
    feedback_ids: list[str],
    task_ids: list[str],
) -> None:
    feedback_count = await session.scalar(
        text(
            "SELECT count(*) FROM ai_achievement_feedback WHERE tenant_id=:tenant_id "
            "AND subject_ids @> CAST(:subjects AS jsonb)"
        ),
        {"tenant_id": tenant_id, "subjects": json.dumps([subject_id])},
    )
    resolution_count = delivery_count = task_count = 0
    if feedback_ids:
        resolution_count = await session.scalar(
            text(
                "SELECT count(*) FROM ai_experience_feedback_resolutions "
                "WHERE feedback_id = ANY(CAST(:ids AS text[]))"
            ),
            {"ids": feedback_ids},
        )
    if task_ids:
        delivery_count = await session.scalar(
            text(
                "SELECT count(*) FROM ai_accepted_action_deliveries "
                "WHERE task_id = ANY(CAST(:ids AS text[]))"
            ),
            {"ids": task_ids},
        )
        task_count = await session.scalar(
            text(
                "SELECT count(*) FROM ai_human_tasks "
                "WHERE task_id = ANY(CAST(:ids AS text[]))"
            ),
            {"ids": task_ids},
        )
    residuals = (feedback_count, resolution_count, delivery_count, task_count)
    if any(int(value or 0) for value in residuals):
        raise ExperienceFeedbackResponseError("FEEDBACK_DELETION_RESIDUALS_REMAIN")


def _required(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExperienceFeedbackResponseError(f"FEEDBACK_RESPONSE_{field_name.upper()}_REQUIRED")
    return value.strip()


def _resolution_id(request_id: str) -> str:
    return "feedback-resolution:" + hashlib.sha256(request_id.encode()).hexdigest()


def _deletion_proof_id(tenant_id: str, subject_id: str, deletion_ref: str) -> str:
    material = "\x1f".join((tenant_id, subject_id, deletion_ref))
    return "feedback-deletion:" + hashlib.sha256(material.encode()).hexdigest()


def feedback_subject_digest(tenant_id: str, subject_id: str) -> str:
    return _digest(f"{tenant_id}\x1f{subject_id}")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _approval_ref(decision_id: str) -> str:
    return f"human-gate:{_digest(decision_id)}"


def _age_on(birth_date: date, on_date: date) -> int:
    return on_date.year - birth_date.year - (
        (on_date.month, on_date.day) < (birth_date.month, birth_date.day)
    )


def _proof(row) -> FeedbackDeletionProof:
    return FeedbackDeletionProof(
        proof_id=str(row["proof_id"]),
        deletion_ref_digest=str(row["deletion_ref_digest"]),
        deleted_feedback=int(row["deleted_feedback"]),
        deleted_resolutions=int(row["deleted_resolutions"]),
        deleted_deliveries=int(row["deleted_deliveries"]),
        deleted_human_tasks=int(row["deleted_human_tasks"]),
        completed_at=row["completed_at"],
    )


__all__ = [
    "FEEDBACK_RESPONSE_ACTION_NAME",
    "FEEDBACK_RESPONSE_RESOLUTION_CODE",
    "ExperienceFeedbackResponseActionHandler",
    "ExperienceFeedbackResponseError",
    "FeedbackDeletionProof",
    "SqlAlchemyExperienceFeedbackDeletionService",
    "feedback_subject_digest",
]
