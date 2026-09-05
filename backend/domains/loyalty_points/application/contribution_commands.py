"""Named actions for the adult contribution ledger.

The command boundary owns authorization context, idempotency and the unit of
work.  The repository only stages rows; a contribution, its audit event,
outbox event and any PlatformPoint entry are committed together.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ..domain.contribution import (
    POINTS_PER_RELEASED_CONTRIBUTION,
    REWARD_BASIS,
    ContributionAuditEvent,
    ContributionConflictError,
    ContributionForbiddenError,
    ContributionNotFoundError,
    ContributionOperation,
    ContributionOutboxEvent,
    ContributionRecord,
    ContributionStatus,
    ContributionValidationError,
    PlatformPoint,
    ReviewDecision,
    require_adult,
    require_family_scope,
    require_human_actor,
    require_safe_reward_basis,
    utcnow,
)
from .contribution_ports import ContributionActionContext, ContributionRepositoryPort


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _require_idempotency(ctx: ContributionActionContext) -> str:
    if ctx.idempotency_key is None or not ctx.idempotency_key.strip():
        raise ContributionValidationError("idempotency_key_required")
    if len(ctx.idempotency_key) > 255:
        raise ContributionValidationError("idempotency_key_too_long")
    return ctx.idempotency_key


def _require_family_binding(ctx: ContributionActionContext, family_id: str) -> None:
    if family_id != ctx.family_id and family_id not in ctx.authorized_family_ids:
        raise ContributionForbiddenError("family_scope_denied")


@dataclass(frozen=True)
class _Mutation:
    record: ContributionRecord
    before_status: ContributionStatus | None
    reason_code: str
    event_type: str
    platform_point: PlatformPoint | None = None


async def _execute(
    repo: ContributionRepositoryPort,
    ctx: ContributionActionContext,
    *,
    action: str,
    fingerprint: str,
    mutator: Callable[[], Awaitable[_Mutation]],
) -> ContributionRecord:
    key = _require_idempotency(ctx)
    existing = await repo.find_operation(ctx.tenant_id, ctx.family_id, key)
    if existing is not None:
        if existing.action != action or existing.request_fingerprint != fingerprint:
            raise ContributionConflictError("idempotency_key_reuse_mismatch")
        return await repo.get_record(ctx.tenant_id, existing.resource_id)

    await repo.checkpoint()
    try:
        mutation = await mutator()
        record = mutation.record
        audit = ContributionAuditEvent(
            event_id=_new_id("contribution-audit"),
            tenant_id=ctx.tenant_id,
            family_id=ctx.family_id,
            actor_person_id=ctx.actor_person_id,
            actor=ctx.actor,
            action=action,
            resource_id=record.contribution_id,
            before_status=mutation.before_status,
            after_status=record.status,
            reason_code=mutation.reason_code,
            correlation_id=ctx.correlation_id,
        )
        outbox = ContributionOutboxEvent(
            event_id=_new_id("contribution-event"),
            tenant_id=ctx.tenant_id,
            family_id=ctx.family_id,
            aggregate_id=record.contribution_id,
            event_type=mutation.event_type,
            payload={
                "contribution_id": record.contribution_id,
                "before_status": (
                    mutation.before_status.value if mutation.before_status is not None else ""
                ),
                "after_status": record.status.value,
                "reason_code": mutation.reason_code,
            },
            correlation_id=ctx.correlation_id,
        )
        await repo.save_record(record)
        await repo.append_audit(audit)
        await repo.append_outbox(outbox)
        if mutation.platform_point is not None:
            await repo.append_platform_point(mutation.platform_point)
        await repo.save_operation(
            ContributionOperation(
                operation_id=_new_id("contribution-operation"),
                tenant_id=ctx.tenant_id,
                family_id=ctx.family_id,
                idempotency_key=key,
                action=action,
                request_fingerprint=fingerprint,
                resource_id=record.contribution_id,
            )
        )
        await repo.commit()
        return record
    except Exception:
        await repo.rollback()
        raise


async def submit_contribution(
    repo: ContributionRepositoryPort,
    ctx: ContributionActionContext,
    *,
    consumer_family_id: str,
    content_ref: str,
    content_type: str,
    purpose: str,
    copyright_attestation_ref: str,
    privacy_redaction_ref: str,
    content_version: int = 1,
) -> ContributionRecord:
    """Submit adult-authored material for review; no reward is created here."""

    require_human_actor(ctx.actor)
    require_adult(ctx.adult_verified, ctx.adult_verification_ref)
    if not consumer_family_id.strip():
        raise ContributionValidationError("consumer_family_required")
    _require_family_binding(ctx, consumer_family_id)
    payload = {
        "action": "submit",
        "consumer_family_id": consumer_family_id,
        "content_ref": content_ref,
        "content_type": content_type,
        "content_version": content_version,
        "purpose": purpose,
        "copyright_attestation_ref": copyright_attestation_ref,
        "privacy_redaction_ref": privacy_redaction_ref,
    }

    async def mutate() -> _Mutation:
        record = ContributionRecord(
            contribution_id=_new_id("contribution"),
            tenant_id=ctx.tenant_id,
            contributor_family_id=ctx.family_id,
            contributor_person_id=ctx.actor_person_id,
            contributor_is_adult=ctx.adult_verified,
            adult_verification_ref=ctx.adult_verification_ref,
            consumer_family_id=consumer_family_id,
            content_ref=content_ref,
            content_type=content_type,  # type: ignore[arg-type]
            content_version=content_version,
            purpose=purpose,
            copyright_attestation_ref=copyright_attestation_ref,
            privacy_redaction_ref=privacy_redaction_ref,
        )
        return _Mutation(
            record=record,
            before_status=None,
            reason_code="ADULT_CONTENT_SUBMITTED",
            event_type="AdultContributionSubmitted",
        )

    return await _execute(
        repo,
        ctx,
        action="submit",
        fingerprint=_fingerprint(payload),
        mutator=mutate,
    )


async def review_contribution(
    repo: ContributionRepositoryPort,
    ctx: ContributionActionContext,
    contribution_id: str,
    decision: ReviewDecision,
) -> ContributionRecord:
    require_human_actor(ctx.actor)
    record = await repo.get_record(ctx.tenant_id, contribution_id)
    require_family_scope(record, ctx.family_id, role="contributor")
    if decision.reviewer_person_id != ctx.actor_person_id:
        raise ContributionForbiddenError("reviewer_actor_mismatch")
    payload = {"action": "review", "contribution_id": contribution_id, **decision.model_dump()}

    async def mutate() -> _Mutation:
        current = await repo.get_record(ctx.tenant_id, contribution_id)
        require_family_scope(current, ctx.family_id, role="contributor")
        before = current.status
        current.review_ref = decision.review_ref
        current.reviewed_by = ctx.actor_person_id
        current.decision_code = decision.reason_code
        target = ContributionStatus.REVIEWED if decision.approved else ContributionStatus.REJECTED
        current.transition(target)
        return _Mutation(current, before, decision.reason_code, "AdultContributionReviewed")

    return await _execute(
        repo,
        ctx,
        action="review",
        fingerprint=_fingerprint(payload),
        mutator=mutate,
    )


async def verify_contribution(
    repo: ContributionRepositoryPort,
    ctx: ContributionActionContext,
    contribution_id: str,
    *,
    verification_ref: str,
) -> ContributionRecord:
    require_human_actor(ctx.actor)
    if not verification_ref.strip():
        raise ContributionValidationError("verification_ref_required")
    initial = await repo.get_record(ctx.tenant_id, contribution_id)
    require_family_scope(initial, ctx.family_id, role="contributor")
    payload = {
        "action": "verify",
        "contribution_id": contribution_id,
        "verification_ref": verification_ref,
    }

    async def mutate() -> _Mutation:
        current = await repo.get_record(ctx.tenant_id, contribution_id)
        require_family_scope(current, ctx.family_id, role="contributor")
        before = current.status
        if current.review_ref is None:
            raise ContributionConflictError("verification_requires_review")
        current.transition(ContributionStatus.VERIFIED)
        current.decision_code = verification_ref
        return _Mutation(current, before, "CONTENT_REVIEW_VERIFIED", "AdultContributionVerified")

    return await _execute(
        repo,
        ctx,
        action="verify",
        fingerprint=_fingerprint(payload),
        mutator=mutate,
    )


async def confirm_family_use(
    repo: ContributionRepositoryPort,
    ctx: ContributionActionContext,
    contribution_id: str,
    *,
    confirmation_ref: str,
) -> ContributionRecord:
    require_human_actor(ctx.actor)
    require_adult(ctx.adult_verified, ctx.adult_verification_ref)
    if not confirmation_ref.strip():
        raise ContributionValidationError("use_confirmation_required")
    initial = await repo.get_record(ctx.tenant_id, contribution_id)
    require_family_scope(initial, ctx.family_id, role="consumer")
    payload = {
        "action": "confirm_use",
        "contribution_id": contribution_id,
        "confirmation_ref": confirmation_ref,
    }

    async def mutate() -> _Mutation:
        current = await repo.get_record(ctx.tenant_id, contribution_id)
        require_family_scope(current, ctx.family_id, role="consumer")
        if current.status != ContributionStatus.VERIFIED:
            raise ContributionConflictError("family_use_requires_verified_contribution")
        if current.use_confirmation_ref is not None:
            raise ContributionConflictError("use_confirmation_already_recorded")
        before = current.status
        current.use_confirmation_ref = confirmation_ref
        current.use_confirmed_by = ctx.actor_person_id
        current.updated_at = utcnow()
        return _Mutation(
            current, before, "ADULT_FAMILY_USE_CONFIRMED", "AdultContributionUseConfirmed"
        )

    return await _execute(
        repo,
        ctx,
        action="confirm_use",
        fingerprint=_fingerprint(payload),
        mutator=mutate,
    )


async def hold_contribution(
    repo: ContributionRepositoryPort,
    ctx: ContributionActionContext,
    contribution_id: str,
    *,
    hold_reason: str,
) -> ContributionRecord:
    require_human_actor(ctx.actor)
    if not hold_reason.strip():
        raise ContributionValidationError("hold_reason_required")
    initial = await repo.get_record(ctx.tenant_id, contribution_id)
    require_family_scope(initial, ctx.family_id, role="contributor")
    payload = {"action": "hold", "contribution_id": contribution_id, "hold_reason": hold_reason}

    async def mutate() -> _Mutation:
        current = await repo.get_record(ctx.tenant_id, contribution_id)
        require_family_scope(current, ctx.family_id, role="contributor")
        if current.use_confirmation_ref is None:
            raise ContributionConflictError("hold_requires_family_use_confirmation")
        before = current.status
        current.hold_reason = hold_reason
        current.transition(ContributionStatus.HELD)
        return _Mutation(current, before, hold_reason, "AdultContributionHeld")

    return await _execute(
        repo,
        ctx,
        action="hold",
        fingerprint=_fingerprint(payload),
        mutator=mutate,
    )


async def release_contribution(
    repo: ContributionRepositoryPort,
    ctx: ContributionActionContext,
    contribution_id: str,
    *,
    release_ref: str,
    reward_basis: str = REWARD_BASIS,
) -> ContributionRecord:
    require_human_actor(ctx.actor)
    require_safe_reward_basis(reward_basis)
    if not release_ref.strip():
        raise ContributionValidationError("release_ref_required")
    initial = await repo.get_record(ctx.tenant_id, contribution_id)
    require_family_scope(initial, ctx.family_id, role="contributor")
    payload = {
        "action": "release",
        "contribution_id": contribution_id,
        "release_ref": release_ref,
        "reward_basis": reward_basis,
    }

    async def mutate() -> _Mutation:
        current = await repo.get_record(ctx.tenant_id, contribution_id)
        require_family_scope(current, ctx.family_id, role="contributor")
        if current.use_confirmation_ref is None:
            raise ContributionConflictError("release_requires_family_use_confirmation")
        before = current.status
        current.transition(ContributionStatus.RELEASED)
        current.release_ref = release_ref
        current.platform_point_entry_id = _new_id("platform-point")
        point = PlatformPoint(
            entry_id=current.platform_point_entry_id,
            tenant_id=current.tenant_id,
            family_id=current.contributor_family_id,
            contribution_id=current.contribution_id,
            points_delta=POINTS_PER_RELEASED_CONTRIBUTION,
            reward_basis="VERIFIED_ADULT_CONTRIBUTION",
        )
        return _Mutation(current, before, reward_basis, "AdultContributionReleased", point)

    return await _execute(
        repo,
        ctx,
        action="release",
        fingerprint=_fingerprint(payload),
        mutator=mutate,
    )


async def withdraw_contribution(
    repo: ContributionRepositoryPort,
    ctx: ContributionActionContext,
    contribution_id: str,
    *,
    reason_code: str,
) -> ContributionRecord:
    require_human_actor(ctx.actor)
    initial = await repo.get_record(ctx.tenant_id, contribution_id)
    require_family_scope(initial, ctx.family_id, role="contributor")
    payload = {"action": "withdraw", "contribution_id": contribution_id, "reason_code": reason_code}

    async def mutate() -> _Mutation:
        current = await repo.get_record(ctx.tenant_id, contribution_id)
        require_family_scope(current, ctx.family_id, role="contributor")
        if current.status not in {ContributionStatus.SUBMITTED, ContributionStatus.REVIEWED}:
            raise ContributionConflictError("withdrawal_window_closed")
        before = current.status
        current.decision_code = "WITHDRAWN"
        current.transition(ContributionStatus.REJECTED)
        return _Mutation(current, before, reason_code, "AdultContributionWithdrawn")

    return await _execute(
        repo,
        ctx,
        action="withdraw",
        fingerprint=_fingerprint(payload),
        mutator=mutate,
    )


async def appeal_contribution(
    repo: ContributionRepositoryPort,
    ctx: ContributionActionContext,
    contribution_id: str,
    *,
    appeal_ref: str,
    reason: str,
) -> ContributionRecord:
    require_human_actor(ctx.actor)
    initial = await repo.get_record(ctx.tenant_id, contribution_id)
    require_family_scope(initial, ctx.family_id, role="contributor")
    payload = {
        "action": "appeal",
        "contribution_id": contribution_id,
        "appeal_ref": appeal_ref,
        "reason": reason,
    }

    async def mutate() -> _Mutation:
        current = await repo.get_record(ctx.tenant_id, contribution_id)
        require_family_scope(current, ctx.family_id, role="contributor")
        before = current.status
        current.appeal_ref = appeal_ref
        current.appeal_reason = reason
        current.transition(ContributionStatus.APPEAL)
        return _Mutation(current, before, reason, "AdultContributionAppealed")

    return await _execute(
        repo,
        ctx,
        action="appeal",
        fingerprint=_fingerprint(payload),
        mutator=mutate,
    )


async def resolve_appeal(
    repo: ContributionRepositoryPort,
    ctx: ContributionActionContext,
    contribution_id: str,
    *,
    approved: bool,
    decision_code: str,
) -> ContributionRecord:
    require_human_actor(ctx.actor)
    initial = await repo.get_record(ctx.tenant_id, contribution_id)
    require_family_scope(initial, ctx.family_id, role="contributor")
    payload = {
        "action": "resolve_appeal",
        "contribution_id": contribution_id,
        "approved": approved,
        "decision_code": decision_code,
    }

    async def mutate() -> _Mutation:
        current = await repo.get_record(ctx.tenant_id, contribution_id)
        require_family_scope(current, ctx.family_id, role="contributor")
        before = current.status
        current.decision_code = decision_code
        if approved:
            points = await repo.list_platform_points(ctx.tenant_id, ctx.family_id)
            positive = next(
                (
                    point
                    for point in points
                    if point.contribution_id == contribution_id and point.points_delta > 0
                ),
                None,
            )
            if positive is not None:
                current.transition(ContributionStatus.RELEASED)
                current.platform_point_entry_id = positive.entry_id
                point = None
            else:
                current.transition(ContributionStatus.VERIFIED)
                point = None
            return _Mutation(
                current, before, decision_code, "AdultContributionAppealApproved", point
            )

        points = await repo.list_platform_points(ctx.tenant_id, ctx.family_id)
        positive = next(
            (
                point
                for point in points
                if point.contribution_id == contribution_id and point.points_delta > 0
            ),
            None,
        )
        if positive is None:
            current.transition(ContributionStatus.REJECTED)
            return _Mutation(current, before, decision_code, "AdultContributionAppealRejected")
        current.transition(ContributionStatus.REVERSED)
        current.reversal_ref = _new_id("reversal")
        point = PlatformPoint(
            entry_id=_new_id("platform-point-reversal"),
            tenant_id=current.tenant_id,
            family_id=current.contributor_family_id,
            contribution_id=current.contribution_id,
            points_delta=-positive.points_delta,
            reward_basis="REFUND_REVERSAL",
            reversal_of_entry_id=positive.entry_id,
        )
        return _Mutation(current, before, decision_code, "AdultContributionAppealReversed", point)

    return await _execute(
        repo,
        ctx,
        action="resolve_appeal",
        fingerprint=_fingerprint(payload),
        mutator=mutate,
    )


async def reverse_released_contribution(
    repo: ContributionRepositoryPort,
    ctx: ContributionActionContext,
    contribution_id: str,
    *,
    refund_ref: str,
) -> ContributionRecord:
    require_human_actor(ctx.actor)
    initial = await repo.get_record(ctx.tenant_id, contribution_id)
    require_family_scope(initial, ctx.family_id, role="contributor")
    payload = {
        "action": "refund_reversal",
        "contribution_id": contribution_id,
        "refund_ref": refund_ref,
    }

    async def mutate() -> _Mutation:
        current = await repo.get_record(ctx.tenant_id, contribution_id)
        require_family_scope(current, ctx.family_id, role="contributor")
        if current.platform_point_entry_id is None:
            raise ContributionConflictError("refund_requires_released_points")
        before = current.status
        current.transition(ContributionStatus.REVERSED)
        current.reversal_ref = refund_ref
        positive = next(
            (
                point
                for point in await repo.list_platform_points(ctx.tenant_id, ctx.family_id)
                if point.entry_id == current.platform_point_entry_id
            ),
            None,
        )
        if positive is None or positive.points_delta <= 0:
            raise ContributionNotFoundError("released_platform_point_not_found")
        point = PlatformPoint(
            entry_id=_new_id("platform-point-reversal"),
            tenant_id=current.tenant_id,
            family_id=current.contributor_family_id,
            contribution_id=current.contribution_id,
            points_delta=-positive.points_delta,
            reward_basis="REFUND_REVERSAL",
            reversal_of_entry_id=positive.entry_id,
        )
        return _Mutation(
            current, before, "REFUND_OR_WITHDRAWAL_REVERSED", "AdultContributionReversed", point
        )

    return await _execute(
        repo,
        ctx,
        action="refund_reversal",
        fingerprint=_fingerprint(payload),
        mutator=mutate,
    )


__all__ = [
    "appeal_contribution",
    "confirm_family_use",
    "hold_contribution",
    "release_contribution",
    "resolve_appeal",
    "review_contribution",
    "reverse_released_contribution",
    "submit_contribution",
    "verify_contribution",
    "withdraw_contribution",
]
