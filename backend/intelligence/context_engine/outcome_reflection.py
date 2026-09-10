"""Project confirmed family outcomes into the canonical Context Engine."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Protocol

from .async_port import AsyncContextBrokerPort
from .contracts import ContextScope, DataClass, StateObservation


class ConfirmedOutcomeProjection(Protocol):
    """Minimal domain-neutral shape accepted from the FamilyNeed domain."""

    outcome_id: str
    need_id: str
    fulfillment_ref: str
    decision: object
    confirmed_by: str
    confirmed_at: datetime
    family_id: str
    tenant_id: str
    subject_ids: tuple[str, ...]
    consent_version: str
    deletion_ref: str
    family_note: str | None


class OutcomeReflectionContextWriter:
    """Write one confirmed outcome as an auditable Context observation."""

    def __init__(
        self,
        broker: AsyncContextBrokerPort,
        *,
        retention: timedelta = timedelta(days=90),
    ) -> None:
        if broker.durability_mode != "DURABLE":
            raise ValueError("outcome reflection requires durable Context Broker")
        if retention <= timedelta(0):
            raise ValueError("outcome reflection retention must be positive")
        self._broker = broker
        self._retention = retention

    async def record_family_need_outcome(self, outcome: object, *, scope: ContextScope) -> None:
        """Project a canonical FamilyNeed outcome without importing its domain.

        The application layer can call this method after its own human-gated
        ``confirm_outcome`` transaction commits.  Keeping the entry point on
        the intelligence side prevents a reverse dependency while making the
        required projection explicit and reviewable.
        """

        await self.record(outcome, scope=scope)  # type: ignore[arg-type]

    async def record(self, outcome: ConfirmedOutcomeProjection, *, scope: ContextScope) -> None:
        # FamilyNeed's canonical aggregate carries governance fields inside
        # ``context``.  Keep the intelligence port domain-neutral while
        # accepting that aggregate through an explicit, read-only projection.
        context = getattr(outcome, "context", None)
        tenant_id = getattr(outcome, "tenant_id", None) or getattr(context, "tenant_id", None)
        family_id = getattr(outcome, "family_id", None) or getattr(context, "family_id", None)
        subject_ids = tuple(
            getattr(outcome, "subject_ids", ())
            or getattr(context, "subject_person_ids", ())
        )
        consent_version = getattr(outcome, "consent_version", None) or getattr(
            context, "consent_version", None
        )
        if tenant_id != scope.tenant_id or family_id != scope.family_id:
            raise ValueError("outcome reflection scope mismatch")
        if not subject_ids or not set(subject_ids).issubset(scope.subject_ids):
            raise ValueError("outcome reflection subject scope mismatch")
        if consent_version != scope.consent_version:
            raise ValueError("outcome reflection consent version mismatch")
        deletion_ref = getattr(outcome, "deletion_ref", None)
        if deletion_ref is None and context is not None:
            deletion_ref = getattr(context, "deletion_ref", None)
        if not isinstance(deletion_ref, str) or not deletion_ref.strip():
            raise ValueError("outcome reflection deletion scope required")
        if deletion_ref != scope.deletion_ref:
            raise ValueError("outcome reflection deletion scope mismatch")
        decision = getattr(outcome.decision, "value", outcome.decision)
        feedback_ref = f"outcome:{outcome.outcome_id}:{decision}"
        family_note = getattr(outcome, "family_note", None)
        if family_note is not None and (
            not isinstance(family_note, str) or len(family_note) > 2000
        ):
            raise ValueError("outcome reflection note invalid")
        value = json.dumps(
            {
                "outcome_id": outcome.outcome_id,
                "need_id": outcome.need_id,
                "fulfillment_ref": outcome.fulfillment_ref,
                "decision": str(decision),
                "feedback_ref": feedback_ref,
                "confirmed_by": outcome.confirmed_by,
                "reflection": family_note.strip() if family_note and family_note.strip() else None,
                "confirmed_at": outcome.confirmed_at.isoformat(),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
        observation = StateObservation(
            observation_id=f"outcome-reflection:{outcome.outcome_id}:{digest}",
            tenant_id=scope.tenant_id,
            family_id=scope.family_id,
            subject_id=subject_ids[0],
            dimension="confirmed_outcome_reflection",
            observed_value=value,
            evidence_refs=(f"family-outcome:{outcome.outcome_id}",),
            provenance="family-need:confirmed-outcome",
            observed_at=outcome.confirmed_at,
            data_class=DataClass(scope.data_class),
            purpose=scope.purpose,
            consent_version=scope.consent_version,
            consent_granted=scope.consent_granted,
            region_id=scope.region_id,
            locale=scope.locale,
            deletion_ref=scope.deletion_ref,
            correlation_id=f"outcome-reflection:{outcome.outcome_id}",
            causation_id=f"family-need:{outcome.need_id}",
            expires_at=outcome.confirmed_at + self._retention,
            retention_policy="confirmed-outcome-reflection.v1",
        )
        await self._broker.append(observation)


__all__ = ["ConfirmedOutcomeProjection", "OutcomeReflectionContextWriter"]
