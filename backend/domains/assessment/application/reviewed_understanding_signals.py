"""Record the exact understanding version a guardian actually viewed."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from ..domain.errors import AssessmentForbiddenError, AssessmentValidationError
from ..domain.understanding_scope import is_supported_understanding_scope
from .growth_intent_handoff import ViewedUnderstandingSignal


@dataclass(frozen=True, slots=True)
class RecordReviewedUnderstandingInput:
    tenant_id: str
    family_id: str
    assessment_session_id: str | None
    signal_ref: str
    signal_version: int
    scope_ref: str
    reviewed_draft_ref: str
    draft_version: int
    provenance_ref: str
    draft_source: Literal["MODEL_GATEWAY", "SYNTHETIC", "FIXED_TEMPLATE"]
    output_schema_ref: str
    view_event_ref: str
    human_gate_receipt_ref: str
    human_gate_effective_status: Literal["EFFECTIVE", "NOT_REVIEWED", "REVOKED", "EXPIRED"]
    reviewed_by_actor_id: str
    reviewed_by_actor_type: Literal["FAMILY_GUARDIAN", "FAMILY_MEMBER", "OPERATOR", "AI"]
    reviewed_at: datetime
    expires_at: datetime | None
    subject_person_id: str
    need_type: str
    goal_text: str
    required_capability_keys: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    understanding_run_ref: str | None = None


class ReviewedUnderstandingSignalWriterPort(Protocol):
    async def save_viewed_signal(
        self, command: RecordReviewedUnderstandingInput
    ) -> ViewedUnderstandingSignal: ...


class RecordReviewedUnderstandingService:
    """Persist only an effective signal after a guardian has viewed it."""

    def __init__(self, writer: ReviewedUnderstandingSignalWriterPort) -> None:
        self._writer = writer

    async def record_viewed(
        self, command: RecordReviewedUnderstandingInput
    ) -> ViewedUnderstandingSignal:
        if command.reviewed_by_actor_type != "FAMILY_GUARDIAN":
            raise AssessmentForbiddenError("guardian_review_required")
        if command.human_gate_effective_status != "EFFECTIVE":
            raise AssessmentForbiddenError("human_gate_receipt_not_effective")
        if command.draft_source != "MODEL_GATEWAY":
            raise AssessmentForbiddenError("model_gateway_reviewed_draft_required")
        if not command.output_schema_ref.strip() or not command.view_event_ref.strip():
            raise AssessmentValidationError("reviewed_draft_verification_required")
        if not is_supported_understanding_scope(
            scope_ref=command.scope_ref,
            tenant_id=command.tenant_id,
            family_id=command.family_id,
        ):
            raise AssessmentForbiddenError("human_gate_scope_mismatch")
        if command.expires_at is not None and command.expires_at <= command.reviewed_at:
            raise AssessmentValidationError("reviewed_understanding_expiry_invalid")
        # Validate the complete immutable binding before the writer can stage a row.
        # This preserves the existing ViewedUnderstandingSignal contract as the
        # single boundary used by both persistence and confirmation.
        ViewedUnderstandingSignal(
            tenant_id=command.tenant_id,
            family_id=command.family_id,
            assessment_session_id=command.assessment_session_id,
            understanding_run_ref=command.understanding_run_ref,
            signal_ref=command.signal_ref,
            signal_version=command.signal_version,
            scope_ref=command.scope_ref,
            reviewed_draft_ref=command.reviewed_draft_ref,
            draft_version=command.draft_version,
            provenance_ref=command.provenance_ref,
            human_gate_receipt_ref=command.human_gate_receipt_ref,
            human_gate_effective_status=command.human_gate_effective_status,
            reviewed_by_actor_id=command.reviewed_by_actor_id,
            subject_person_id=command.subject_person_id,
            need_type=command.need_type,
            goal_text=command.goal_text,
            required_capability_keys=command.required_capability_keys,
            evidence_refs=command.evidence_refs,
            reviewed_at=command.reviewed_at,
            expires_at=command.expires_at,
            draft_source=command.draft_source,
            output_schema_ref=command.output_schema_ref,
            view_event_ref=command.view_event_ref,
        )
        return await self._writer.save_viewed_signal(command)


__all__ = [
    "RecordReviewedUnderstandingInput",
    "RecordReviewedUnderstandingService",
    "ReviewedUnderstandingSignalWriterPort",
]
