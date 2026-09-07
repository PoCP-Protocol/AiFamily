"""Human-gated lifecycle operations for course release baselines.

This application boundary deliberately contains no repository or provider
integration.  It accepts an immutable ``ReleaseBaseline`` and a real human
decision, delegates the transition to the shared PLM contract, and returns a
new baseline plus an audit projection.  HTTP and persistence adapters can
consume this seam without duplicating lifecycle rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from backend.intelligence.human_gate.contracts import (
    HUMAN_ACTOR_TYPES,
    ActorType,
    DecisionOutcome,
    HumanDecision,
)

from ..ipd_contracts import GateEvidence, IPDContractError, ReleaseBaseline


class CourseReleaseLifecycleError(ValueError):
    """Raised when a course release cannot cross the Human Gate."""


CourseReleaseAction = Literal["APPROVE", "RELEASE", "PAUSE", "ROLLBACK", "RETIRE"]


@dataclass(frozen=True, slots=True)
class CourseReleaseLifecycleAudit:
    release_id: str
    from_status: str
    to_status: str
    action: CourseReleaseAction
    decision_id: str
    task_id: str
    actor_id: str
    actor_type: ActorType
    evidence_ids: tuple[str, ...]
    decided_at: datetime
    rollback_target_ref: str | None = None


@dataclass(frozen=True, slots=True)
class CourseReleaseLifecycleResult:
    baseline: ReleaseBaseline
    audit: CourseReleaseLifecycleAudit


def _evidence(items: tuple[GateEvidence, ...]) -> tuple[GateEvidence, ...]:
    if not isinstance(items, tuple) or not items:
        raise CourseReleaseLifecycleError("COURSE_RELEASE_GATE_EVIDENCE_REQUIRED")
    if any(not isinstance(item, GateEvidence) for item in items):
        raise CourseReleaseLifecycleError("COURSE_RELEASE_GATE_EVIDENCE_INVALID")
    ids = tuple(item.evidence_id.strip() for item in items)
    if any(not item for item in ids) or len(set(ids)) != len(ids):
        raise CourseReleaseLifecycleError("COURSE_RELEASE_GATE_EVIDENCE_INVALID")
    return items


def advance_course_release_lifecycle(
    baseline: ReleaseBaseline,
    *,
    action: CourseReleaseAction,
    decision: HumanDecision,
    evidence: tuple[GateEvidence, ...],
    rollback_target_ref: str | None = None,
    now: datetime | None = None,
) -> CourseReleaseLifecycleResult:
    """Apply one explicit, human-approved course release transition."""

    if not isinstance(baseline, ReleaseBaseline):
        raise CourseReleaseLifecycleError("COURSE_RELEASE_BASELINE_REQUIRED")
    if not isinstance(decision, HumanDecision):
        raise CourseReleaseLifecycleError("COURSE_RELEASE_HUMAN_DECISION_REQUIRED")
    if decision.actor_type not in HUMAN_ACTOR_TYPES:
        raise CourseReleaseLifecycleError("COURSE_RELEASE_HUMAN_ACTOR_REQUIRED")
    if DecisionOutcome(decision.outcome) is not DecisionOutcome.ACCEPT:
        raise CourseReleaseLifecycleError("COURSE_RELEASE_HUMAN_ACCEPT_REQUIRED")
    if action not in {"APPROVE", "RELEASE", "PAUSE", "ROLLBACK", "RETIRE"}:
        raise CourseReleaseLifecycleError("COURSE_RELEASE_ACTION_INVALID")
    items = _evidence(evidence)
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise CourseReleaseLifecycleError("COURSE_RELEASE_NOW_MUST_BE_AWARE")
    if decision.decided_at > current:
        raise CourseReleaseLifecycleError("COURSE_RELEASE_DECISION_FROM_FUTURE")

    try:
        if action == "APPROVE":
            updated = baseline.approve(
                decided_by=decision.actor_id,
                human_gate_ref=decision.task_id,
                evidence=items,
            )
        elif action == "RELEASE":
            updated = baseline.release(decided_by=decision.actor_id, evidence=items)
        elif action == "PAUSE":
            updated = baseline.pause(decided_by=decision.actor_id, evidence=items)
        elif action == "ROLLBACK":
            if not rollback_target_ref or not rollback_target_ref.strip():
                raise CourseReleaseLifecycleError("COURSE_RELEASE_ROLLBACK_TARGET_REQUIRED")
            updated = baseline.rollback(
                target_ref=rollback_target_ref,
                decided_by=decision.actor_id,
                evidence=items,
            )
        else:
            updated = baseline.retire(decided_by=decision.actor_id, evidence=items)
    except IPDContractError as exc:
        raise CourseReleaseLifecycleError(str(exc)) from exc

    return CourseReleaseLifecycleResult(
        baseline=updated,
        audit=CourseReleaseLifecycleAudit(
            release_id=baseline.release_id,
            from_status=str(baseline.status),
            to_status=str(updated.status),
            action=action,
            decision_id=decision.decision_id,
            task_id=decision.task_id,
            actor_id=decision.actor_id,
            actor_type=decision.actor_type,
            evidence_ids=tuple(item.evidence_id for item in items),
            decided_at=decision.decided_at,
            rollback_target_ref=updated.rollback_target_ref,
        ),
    )


__all__ = [
    "CourseReleaseLifecycleAudit",
    "CourseReleaseLifecycleError",
    "CourseReleaseLifecycleResult",
    "advance_course_release_lifecycle",
]
