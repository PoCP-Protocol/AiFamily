"""Human-gated lifecycle adapter for IPD product packages.

The adapter is deliberately a pure application boundary.  It validates a
Human Gate decision and its evidence before delegating the sequential status
transition to :class:`ProductPackage.advance`.  No repository, model gateway,
or business-fact writer is accepted here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from backend.intelligence.human_gate.contracts import (
    HUMAN_ACTOR_TYPES,
    ActorType,
    DecisionOutcome,
    HumanDecision,
)

from ..ipd_contracts import (
    ArtifactStatus,
    GateDecision,
    GateEvidence,
    IPDContractError,
    ProductPackage,
    ReleaseBaseline,
)


class ProductPackageLifecycleError(ValueError):
    """Raised when a package lifecycle decision cannot pass the human gate."""


_PACKAGE_STATUSES = (
    ArtifactStatus.DRAFT,
    ArtifactStatus.PILOT,
    ArtifactStatus.QUALIFIED,
    ArtifactStatus.RELEASED,
)


@dataclass(frozen=True, slots=True)
class ProductPackageLifecycleAudit:
    """Immutable audit projection for one accepted lifecycle transition."""

    package_id: str
    package_version: str
    from_status: ArtifactStatus
    to_status: ArtifactStatus
    decision_id: str
    task_id: str
    actor_id: str
    actor_type: ActorType
    outcome: DecisionOutcome
    gate_decision: GateDecision
    evidence_ids: tuple[str, ...]
    decided_at: datetime
    decision_expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ProductPackageLifecycleResult:
    """New package value plus the audit record; neither is persisted here."""

    package: ProductPackage
    audit: ProductPackageLifecycleAudit


def _aware(value: datetime, code: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ProductPackageLifecycleError(code)
    return value.astimezone(UTC)


def _normalise_status(value: ArtifactStatus | str) -> ArtifactStatus:
    try:
        status = value if isinstance(value, ArtifactStatus) else ArtifactStatus(value)
    except (TypeError, ValueError) as exc:
        raise ProductPackageLifecycleError("TARGET_STATUS_INVALID") from exc
    if status not in _PACKAGE_STATUSES:
        raise ProductPackageLifecycleError("TARGET_STATUS_INVALID")
    return status


def _validate_evidence(evidence: tuple[GateEvidence, ...]) -> tuple[GateEvidence, ...]:
    if not isinstance(evidence, tuple) or not evidence:
        raise ProductPackageLifecycleError("GATE_EVIDENCE_REQUIRED")
    if any(not isinstance(item, GateEvidence) for item in evidence):
        raise ProductPackageLifecycleError("GATE_EVIDENCE_INVALID")
    evidence_ids = tuple(item.evidence_id.strip() for item in evidence)
    if len(set(evidence_ids)) != len(evidence_ids):
        raise ProductPackageLifecycleError("GATE_EVIDENCE_MUST_BE_UNIQUE")
    return evidence


def _validate_release_baseline(
    package: ProductPackage,
    target_status: ArtifactStatus,
    release_baseline: ReleaseBaseline | None,
) -> None:
    if target_status is not ArtifactStatus.RELEASED:
        return
    if not package.release_baseline_id:
        raise ProductPackageLifecycleError("RELEASE_BASELINE_REQUIRED")
    if not isinstance(release_baseline, ReleaseBaseline):
        raise ProductPackageLifecycleError("RELEASE_BASELINE_REQUIRED")
    if release_baseline.status is not ArtifactStatus.RELEASED:
        raise ProductPackageLifecycleError("RELEASE_BASELINE_NOT_RELEASED")
    if release_baseline.release_id != package.release_baseline_id:
        raise ProductPackageLifecycleError("RELEASE_BASELINE_MISMATCH")
    if (
        release_baseline.package_id != package.package_id
        or release_baseline.package_version != package.version
    ):
        raise ProductPackageLifecycleError("RELEASE_BASELINE_PACKAGE_MISMATCH")


def advance_product_package_lifecycle(
    package: ProductPackage,
    *,
    decision: HumanDecision,
    evidence: tuple[GateEvidence, ...],
    target_status: ArtifactStatus | str,
    release_baseline: ReleaseBaseline | None = None,
    decision_expires_at: datetime | None = None,
    now: datetime | None = None,
) -> ProductPackageLifecycleResult:
    """Apply one accepted Human Gate decision to a product package.

    ``HumanDecision.outcome=ACCEPT`` is the Human Gate equivalent of the IPD
    ``GateDecision.GO``.  REJECT, ESCALATE, non-human actors, expired/future
    decisions, incomplete evidence, and release-baseline mismatches fail
    before ``package.advance`` is called.
    """

    if not isinstance(package, ProductPackage):
        raise ProductPackageLifecycleError("PRODUCT_PACKAGE_REQUIRED")
    if not isinstance(decision, HumanDecision):
        raise ProductPackageLifecycleError("HUMAN_DECISION_REQUIRED")
    if decision.actor_type not in HUMAN_ACTOR_TYPES:
        raise ProductPackageLifecycleError("HUMAN_ACTOR_REQUIRED")
    try:
        outcome = DecisionOutcome(decision.outcome)
        actor_type = ActorType(decision.actor_type)
    except (TypeError, ValueError) as exc:
        raise ProductPackageLifecycleError("HUMAN_DECISION_INVALID") from exc
    if actor_type not in HUMAN_ACTOR_TYPES:
        raise ProductPackageLifecycleError("HUMAN_ACTOR_REQUIRED")
    if outcome is not DecisionOutcome.ACCEPT:
        raise ProductPackageLifecycleError("HUMAN_GATE_ACCEPT_REQUIRED")

    target = _normalise_status(target_status)
    evidence_items = _validate_evidence(evidence)
    current = _aware(now or datetime.now(UTC), "NOW_MUST_BE_TIMEZONE_AWARE")
    decided_at = _aware(decision.decided_at, "DECISION_TIME_MUST_BE_TIMEZONE_AWARE")
    if decided_at > current:
        raise ProductPackageLifecycleError("DECISION_FROM_FUTURE")
    expiry = None
    if decision_expires_at is not None:
        expiry = _aware(decision_expires_at, "DECISION_EXPIRY_MUST_BE_TIMEZONE_AWARE")
        if expiry <= current:
            raise ProductPackageLifecycleError("HUMAN_DECISION_EXPIRED")
    _validate_release_baseline(package, target, release_baseline)

    try:
        advanced = package.advance(
            target,
            decision=GateDecision.GO,
            decided_by=decision.actor_id,
            evidence=evidence_items,
        )
    except IPDContractError as exc:
        raise ProductPackageLifecycleError(str(exc)) from exc

    audit = ProductPackageLifecycleAudit(
        package_id=package.package_id,
        package_version=package.version,
        from_status=package.status,
        to_status=advanced.status,
        decision_id=decision.decision_id,
        task_id=decision.task_id,
        actor_id=decision.actor_id,
        actor_type=actor_type,
        outcome=outcome,
        gate_decision=GateDecision.GO,
        evidence_ids=tuple(item.evidence_id for item in evidence_items),
        decided_at=decided_at,
        decision_expires_at=expiry,
    )
    return ProductPackageLifecycleResult(package=advanced, audit=audit)


__all__ = [
    "ProductPackageLifecycleAudit",
    "ProductPackageLifecycleError",
    "ProductPackageLifecycleResult",
    "advance_product_package_lifecycle",
]
