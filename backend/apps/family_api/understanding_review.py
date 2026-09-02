"""Server-owned confirmation of an immutable family-understanding draft."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.apps.family_api.sqlalchemy_understanding_snapshots import (
    SqlAlchemyUnderstandingDraftSnapshots,
)
from backend.domains.assessment.application.growth_intent_handoff import (
    ViewedUnderstandingSignal,
)
from backend.domains.assessment.application.reviewed_understanding_signals import (
    RecordReviewedUnderstandingInput,
    RecordReviewedUnderstandingService,
)
from backend.domains.assessment.infrastructure.sqlalchemy_reviewed_understanding_signals import (
    SqlAlchemyReviewedUnderstandingSignals,
)
from backend.intelligence.family_understanding.api import (
    ReviewUnderstandingCommand,
    ReviewUnderstandingView,
)
from backend.intelligence.family_understanding.snapshot import (
    UnderstandingDraftSnapshot,
    UnderstandingDraftSnapshotReader,
)
from backend.platform.authorization.review_receipts import (
    ReviewReceiptBinding,
    ReviewReceiptDenied,
    ReviewReceiptInvalid,
    ReviewReceiptIssuer,
)
from backend.platform.identity.context import ActorContext, ActorType


class ConfirmationReplayReader(Protocol):
    async def load_confirmation_replay(
        self,
        *,
        tenant_id: str,
        family_id: str,
        understanding_run_ref: str,
        artifact_ref: str,
        artifact_version: int,
        provenance_ref: str,
        actor_id: str,
        view_event_ref: str,
    ) -> ViewedUnderstandingSignal | None: ...


class UnderstandingConfirmationRejected(RuntimeError):
    """Fail-closed public reason for a rejected confirmation."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class ConfirmUnderstandingApplication:
    """Issue one Human Gate receipt and stage one Assessment-owned signal."""

    def __init__(
        self,
        snapshots: UnderstandingDraftSnapshotReader,
        receipts: ReviewReceiptIssuer,
        reviewed_signals: RecordReviewedUnderstandingService,
        *,
        confirmation_replays: ConfirmationReplayReader | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._snapshots = snapshots
        self._receipts = receipts
        self._reviewed_signals = reviewed_signals
        self._confirmation_replays = confirmation_replays
        self._clock = clock or (lambda: datetime.now(UTC))

    async def review(self, command: ReviewUnderstandingCommand) -> ReviewUnderstandingView:
        snapshot = await self._snapshots.load(
            tenant_id=command.tenant_id,
            family_id=command.family_id,
            artifact_ref=command.artifact_ref,
            artifact_version=command.artifact_version,
            provenance_ref=command.provenance_ref,
        )
        if snapshot is None:
            raise UnderstandingConfirmationRejected("UNDERSTANDING_SNAPSHOT_NOT_EFFECTIVE")
        self._assert_subject_binding(command, snapshot)

        replay = await self._load_replay(command, snapshot)
        if replay is not None:
            if replay.human_gate_effective_status != "EFFECTIVE" or replay.expires_at is None:
                raise UnderstandingConfirmationRejected("UNDERSTANDING_CONFIRMATION_DENIED")
            return ReviewUnderstandingView(
                receipt_ref=replay.human_gate_receipt_ref,
                status="EFFECTIVE",
                scope_ref=replay.scope_ref,
                artifact_ref=replay.reviewed_draft_ref,
                artifact_version=replay.draft_version,
                provenance_ref=replay.provenance_ref,
                expires_at=replay.expires_at,
            )

        confirmed_at = self._clock()
        actor = ActorContext(
            actor_id=command.actor_id,
            actor_type=ActorType.HUMAN,
            tenant_id=command.tenant_id,
            correlation_id=command.view_event_ref,
        )
        binding = ReviewReceiptBinding(
            tenant_id=snapshot.tenant_id,
            family_id=snapshot.family_id,
            scope_ref=snapshot.scope_ref,
            artifact_ref=snapshot.artifact_ref,
            artifact_version=snapshot.artifact_version,
            provenance_ref=snapshot.provenance_ref,
            view_event_ref=command.view_event_ref,
            viewed_at=confirmed_at,
            expires_at=snapshot.expires_at,
        )
        try:
            receipt = self._receipts.issue(actor, binding, evaluated_at=confirmed_at)
        except (ReviewReceiptDenied, ReviewReceiptInvalid) as exc:
            raise UnderstandingConfirmationRejected("UNDERSTANDING_CONFIRMATION_DENIED") from exc

        await self._reviewed_signals.record_viewed(
            RecordReviewedUnderstandingInput(
                tenant_id=snapshot.tenant_id,
                family_id=snapshot.family_id,
                assessment_session_id=None,
                understanding_run_ref=snapshot.understanding_run_ref,
                signal_ref=_signal_ref(snapshot),
                signal_version=snapshot.artifact_version,
                scope_ref=snapshot.scope_ref,
                reviewed_draft_ref=snapshot.artifact_ref,
                draft_version=snapshot.artifact_version,
                provenance_ref=snapshot.provenance_ref,
                draft_source="MODEL_GATEWAY",
                output_schema_ref=snapshot.schema_version,
                view_event_ref=command.view_event_ref,
                human_gate_receipt_ref=receipt.receipt_ref,
                human_gate_effective_status=receipt.status,
                reviewed_by_actor_id=command.actor_id,
                reviewed_by_actor_type="FAMILY_GUARDIAN",
                reviewed_at=confirmed_at,
                expires_at=receipt.expires_at,
                subject_person_id=snapshot.subject_person_id,
                need_type=snapshot.need_type,
                goal_text=snapshot.desired_change,
                required_capability_keys=snapshot.required_capability_keys,
                evidence_refs=snapshot.evidence_refs,
            )
        )
        return ReviewUnderstandingView(
            receipt_ref=receipt.receipt_ref,
            status=receipt.status,
            scope_ref=snapshot.scope_ref,
            artifact_ref=snapshot.artifact_ref,
            artifact_version=snapshot.artifact_version,
            provenance_ref=snapshot.provenance_ref,
            expires_at=receipt.expires_at,
        )

    @staticmethod
    def _assert_subject_binding(
        command: ReviewUnderstandingCommand, snapshot: UnderstandingDraftSnapshot
    ) -> None:
        if snapshot.subject_person_id != command.subject_person_id:
            raise UnderstandingConfirmationRejected("UNDERSTANDING_SUBJECT_MISMATCH")

    async def _load_replay(
        self,
        command: ReviewUnderstandingCommand,
        snapshot: UnderstandingDraftSnapshot,
    ) -> ViewedUnderstandingSignal | None:
        if self._confirmation_replays is None:
            return None
        return await self._confirmation_replays.load_confirmation_replay(
            tenant_id=snapshot.tenant_id,
            family_id=snapshot.family_id,
            understanding_run_ref=snapshot.understanding_run_ref,
            artifact_ref=snapshot.artifact_ref,
            artifact_version=snapshot.artifact_version,
            provenance_ref=snapshot.provenance_ref,
            actor_id=command.actor_id,
            view_event_ref=command.view_event_ref,
        )


class TransactionalConfirmUnderstandingApplication:
    """Run snapshot read, receipt issuance and signal write in one transaction."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        receipts: ReviewReceiptIssuer,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._receipts = receipts
        self._clock = clock

    async def review(self, command: ReviewUnderstandingCommand) -> ReviewUnderstandingView:
        async with self._session_factory() as session:
            signals = SqlAlchemyReviewedUnderstandingSignals(session)
            application = ConfirmUnderstandingApplication(
                SqlAlchemyUnderstandingDraftSnapshots(session),
                self._receipts,
                RecordReviewedUnderstandingService(signals),
                confirmation_replays=signals,
                clock=self._clock,
            )
            result = await application.review(command)
            await session.commit()
            return result


def _signal_ref(snapshot: UnderstandingDraftSnapshot) -> str:
    payload = {
        "tenant_id": snapshot.tenant_id,
        "family_id": snapshot.family_id,
        "understanding_run_ref": snapshot.understanding_run_ref,
        "artifact_ref": snapshot.artifact_ref,
        "artifact_version": snapshot.artifact_version,
        "provenance_ref": snapshot.provenance_ref,
    }
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return "understanding-signal:v1:sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "ConfirmUnderstandingApplication",
    "TransactionalConfirmUnderstandingApplication",
    "UnderstandingConfirmationRejected",
]
