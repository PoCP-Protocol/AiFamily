"""Acceptance and rejection matrix for the adult contribution ledger."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.domains.loyalty_points.application.contribution_commands import (
    appeal_contribution,
    confirm_family_use,
    hold_contribution,
    release_contribution,
    resolve_appeal,
    reverse_released_contribution,
    review_contribution,
    submit_contribution,
    verify_contribution,
    withdraw_contribution,
)
from backend.domains.loyalty_points.application.contribution_ports import (
    ContributionActionContext,
)
from backend.domains.loyalty_points.domain.contribution import (
    ContributionConflictError,
    ContributionForbiddenError,
    ContributionNotFoundError,
    ContributionRecord,
    ContributionStatus,
    ContributionValidationError,
    FGCNContributionUnit,
    ReviewDecision,
    SettlementAmount,
    require_safe_reward_basis,
)
from backend.domains.loyalty_points.infrastructure.contribution_fake_repository import (
    FakeContributionRepository,
)
from backend.domains.loyalty_points.infrastructure.contribution_sqlalchemy import (
    ContributionBase,
    SqlAlchemyContributionRepository,
)

TENANT = "tenant-contribution"
OTHER_TENANT = "tenant-other"
CONTRIBUTOR_FAMILY = "family-contributor"
CONSUMER_FAMILY = "family-consumer"
OTHER_FAMILY = "family-other"
CONTRIBUTOR_PERSON = "adult-contributor"
CONSUMER_PERSON = "adult-consumer"


@pytest_asyncio.fixture(params=["fake", "sqlite"])
async def contribution_repo(request) -> AsyncIterator[object]:
    if request.param == "fake":
        yield FakeContributionRepository()
        return

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(ContributionBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield SqlAlchemyContributionRepository(session)
    await engine.dispose()


def _ctx(
    *,
    family_id: str = CONTRIBUTOR_FAMILY,
    tenant_id: str = TENANT,
    person_id: str = CONTRIBUTOR_PERSON,
    actor: str = "guardian:contributor",
    adult: bool = True,
    verification_ref: str = "adult-verification-1",
    key: str | None = None,
    authorized_family_ids: frozenset[str] = frozenset(),
) -> ContributionActionContext:
    return ContributionActionContext(
        tenant_id=tenant_id,
        family_id=family_id,
        actor_person_id=person_id,
        actor=actor,
        correlation_id=f"correlation:{key or 'no-key'}",
        adult_verified=adult,
        adult_verification_ref=verification_ref,
        idempotency_key=key,
        authorized_family_ids=authorized_family_ids,
    )


def _consumer_ctx(key: str, *, adult: bool = True) -> ContributionActionContext:
    return _ctx(
        family_id=CONSUMER_FAMILY,
        person_id=CONSUMER_PERSON,
        actor="guardian:consumer",
        adult=adult,
        key=key,
    )


async def _submit(repo, *, key: str = "submit-1", consumer_family_id: str = CONSUMER_FAMILY):
    return await submit_contribution(
        repo,
        _ctx(key=key, authorized_family_ids=frozenset({consumer_family_id})),
        consumer_family_id=consumer_family_id,
        content_ref="adult-experience:communication-1",
        content_type="ARTICLE",
        purpose="VERIFIED_ADULT_CONTRIBUTION",
        copyright_attestation_ref="copyright-attestation-1",
        privacy_redaction_ref="privacy-redaction-1",
    )


async def _verified(repo, *, prefix: str = "flow"):
    record = await _submit(repo, key=f"{prefix}-submit")
    reviewed = await review_contribution(
        repo,
        _ctx(key=f"{prefix}-review"),
        record.contribution_id,
        ReviewDecision(
            review_ref=f"review:{prefix}",
            reviewer_person_id=CONTRIBUTOR_PERSON,
            content_approved=True,
            copyright_approved=True,
            safety_approved=True,
            reason_code="CONTENT_COPYRIGHT_SAFETY_APPROVED",
        ),
    )
    assert reviewed.status is ContributionStatus.REVIEWED
    return await verify_contribution(
        repo,
        _ctx(key=f"{prefix}-verify"),
        record.contribution_id,
        verification_ref=f"verification:{prefix}",
    )


async def _released(repo, *, prefix: str = "release"):
    record = await _verified(repo, prefix=prefix)
    confirmed = await confirm_family_use(
        repo,
        _consumer_ctx(f"{prefix}-confirm"),
        record.contribution_id,
        confirmation_ref=f"use:{prefix}",
    )
    assert confirmed.status is ContributionStatus.VERIFIED
    await hold_contribution(
        repo,
        _ctx(key=f"{prefix}-hold"),
        record.contribution_id,
        hold_reason="adult-family-use-confirmed",
    )
    return await release_contribution(
        repo,
        _ctx(key=f"{prefix}-release"),
        record.contribution_id,
        release_ref=f"release:{prefix}",
    )


async def test_adult_contribution_lifecycle_is_identical_on_fake_and_sqlite(
    contribution_repo,
) -> None:
    record = await _submit(contribution_repo)
    reviewed = await review_contribution(
        contribution_repo,
        _ctx(key="review-1"),
        record.contribution_id,
        ReviewDecision(
            review_ref="review:1",
            reviewer_person_id=CONTRIBUTOR_PERSON,
            content_approved=True,
            copyright_approved=True,
            safety_approved=True,
            reason_code="APPROVED",
        ),
    )
    verified = await verify_contribution(
        contribution_repo,
        _ctx(key="verify-1"),
        record.contribution_id,
        verification_ref="verification:1",
    )
    confirmed = await confirm_family_use(
        contribution_repo,
        _consumer_ctx("confirm-1"),
        record.contribution_id,
        confirmation_ref="use-confirmation:1",
    )
    held = await hold_contribution(
        contribution_repo,
        _ctx(key="hold-1"),
        record.contribution_id,
        hold_reason="adult-family-use-confirmed",
    )
    released = await release_contribution(
        contribution_repo,
        _ctx(key="release-1"),
        record.contribution_id,
        release_ref="release:1",
    )

    assert [
        record.status,
        reviewed.status,
        verified.status,
        confirmed.status,
        held.status,
        released.status,
    ] == [
        ContributionStatus.SUBMITTED,
        ContributionStatus.REVIEWED,
        ContributionStatus.VERIFIED,
        ContributionStatus.VERIFIED,
        ContributionStatus.HELD,
        ContributionStatus.RELEASED,
    ]
    points = await contribution_repo.list_platform_points(TENANT, CONTRIBUTOR_FAMILY)
    assert [(entry.points_delta, entry.reward_basis) for entry in points] == [
        (20, "VERIFIED_ADULT_CONTRIBUTION")
    ]
    audits = await contribution_repo.list_audits(TENANT, record.contribution_id)
    outbox = await contribution_repo.list_outbox(TENANT, record.contribution_id)
    assert len(audits) == len(outbox) == 6
    assert audits[-1].after_status is ContributionStatus.RELEASED
    assert outbox[-1].event_type == "AdultContributionReleased"


async def test_submit_requires_verified_adult_and_human_actor(contribution_repo) -> None:
    with pytest.raises(ContributionForbiddenError, match="adult_contributor_required"):
        await submit_contribution(
            contribution_repo,
            _ctx(key="child-submit", adult=False, verification_ref=""),
            consumer_family_id=CONSUMER_FAMILY,
            content_ref="adult-experience:child-test",
            content_type="ARTICLE",
            purpose="VERIFIED_ADULT_CONTRIBUTION",
            copyright_attestation_ref="copyright-1",
            privacy_redaction_ref="privacy-1",
        )

    with pytest.raises(ContributionForbiddenError, match="human_actor_required"):
        await submit_contribution(
            contribution_repo,
            _ctx(key="ai-submit", actor="ai:reviewer"),
            consumer_family_id=CONSUMER_FAMILY,
            content_ref="adult-experience:ai-test",
            content_type="ARTICLE",
            purpose="VERIFIED_ADULT_CONTRIBUTION",
            copyright_attestation_ref="copyright-1",
            privacy_redaction_ref="privacy-1",
        )


@pytest.mark.parametrize(
    "failed_field",
    ["content_approved", "copyright_approved", "safety_approved"],
)
async def test_content_copyright_and_safety_review_each_rejects(contribution_repo, failed_field):
    record = await _submit(contribution_repo, key=f"submit-{failed_field}")
    decisions = {
        "content_approved": True,
        "copyright_approved": True,
        "safety_approved": True,
    }
    decisions[failed_field] = False
    rejected = await review_contribution(
        contribution_repo,
        _ctx(key=f"review-{failed_field}"),
        record.contribution_id,
        ReviewDecision(
            review_ref=f"review:{failed_field}",
            reviewer_person_id=CONTRIBUTOR_PERSON,
            reason_code=f"REJECTED_{failed_field.upper()}",
            **decisions,
        ),
    )
    assert rejected.status is ContributionStatus.REJECTED
    assert await contribution_repo.list_platform_points(TENANT, CONTRIBUTOR_FAMILY) == []


async def test_cross_family_and_cross_tenant_access_is_denied(contribution_repo) -> None:
    record = await _submit(contribution_repo)
    with pytest.raises(ContributionForbiddenError, match="family_scope_denied"):
        await verify_contribution(
            contribution_repo,
            _ctx(family_id=OTHER_FAMILY, key="wrong-family"),
            record.contribution_id,
            verification_ref="wrong-family-verification",
        )
    with pytest.raises(ContributionNotFoundError, match="contribution_not_found"):
        await verify_contribution(
            contribution_repo,
            _ctx(tenant_id=OTHER_TENANT, key="wrong-tenant"),
            record.contribution_id,
            verification_ref="wrong-tenant-verification",
        )


async def test_submit_rejects_an_unbound_consumer_family(contribution_repo) -> None:
    with pytest.raises(ContributionForbiddenError, match="family_scope_denied"):
        await submit_contribution(
            contribution_repo,
            _ctx(key="unbound-consumer"),
            consumer_family_id=OTHER_FAMILY,
            content_ref="adult-experience:unbound",
            content_type="ARTICLE",
            purpose="VERIFIED_ADULT_CONTRIBUTION",
            copyright_attestation_ref="copyright-1",
            privacy_redaction_ref="privacy-1",
        )
async def test_idempotency_replays_once_and_rejects_key_reuse(contribution_repo) -> None:
    first = await _submit(contribution_repo, key="same-submit")
    replay = await _submit(contribution_repo, key="same-submit")
    assert replay.contribution_id == first.contribution_id
    with pytest.raises(ContributionConflictError, match="idempotency_key_reuse_mismatch"):
        await submit_contribution(
            contribution_repo,
            _ctx(
                key="same-submit",
                authorized_family_ids=frozenset({CONSUMER_FAMILY}),
            ),
            consumer_family_id=CONSUMER_FAMILY,
            content_ref="adult-experience:different",
            content_type="ARTICLE",
            purpose="VERIFIED_ADULT_CONTRIBUTION",
            copyright_attestation_ref="copyright-1",
            privacy_redaction_ref="privacy-1",
        )
    assert len(await contribution_repo.list_audits(TENANT, first.contribution_id)) == 1
    assert len(await contribution_repo.list_outbox(TENANT, first.contribution_id)) == 1


async def test_family_use_confirmation_is_adult_once_only(contribution_repo) -> None:
    record = await _verified(contribution_repo, prefix="confirmation")
    first = await confirm_family_use(
        contribution_repo,
        _consumer_ctx("confirmation-once"),
        record.contribution_id,
        confirmation_ref="adult-use-1",
    )
    replay = await confirm_family_use(
        contribution_repo,
        _consumer_ctx("confirmation-once"),
        record.contribution_id,
        confirmation_ref="adult-use-1",
    )
    assert replay.use_confirmation_ref == first.use_confirmation_ref
    with pytest.raises(ContributionConflictError, match="use_confirmation_already_recorded"):
        await confirm_family_use(
            contribution_repo,
            _consumer_ctx("confirmation-different"),
            record.contribution_id,
            confirmation_ref="adult-use-2",
        )
    with pytest.raises(ContributionForbiddenError, match="adult_contributor_required"):
        await confirm_family_use(
            contribution_repo,
            _consumer_ctx("confirmation-child", adult=False),
            record.contribution_id,
            confirmation_ref="adult-use-child",
        )


async def test_release_rejects_ai_and_child_or_outcome_reward_basis(contribution_repo) -> None:
    record = await _verified(contribution_repo, prefix="release-gate")
    await confirm_family_use(
        contribution_repo,
        _consumer_ctx("release-gate-confirm"),
        record.contribution_id,
        confirmation_ref="use:release-gate",
    )
    await hold_contribution(
        contribution_repo,
        _ctx(key="release-gate-hold"),
        record.contribution_id,
        hold_reason="confirmed",
    )
    with pytest.raises(ContributionForbiddenError, match="human_actor_required"):
        await release_contribution(
            contribution_repo,
            _ctx(key="release-gate-ai", actor="ai:reward"),
            record.contribution_id,
            release_ref="release:ai",
        )
    with pytest.raises(ContributionForbiddenError, match="child_or_outcome_reward_basis_forbidden"):
        await release_contribution(
            contribution_repo,
            _ctx(key="release-gate-child"),
            record.contribution_id,
            release_ref="release:child",
            reward_basis="CHILD_SCORE",
        )


async def test_commit_failure_rolls_back_record_audit_outbox_and_operation() -> None:
    repo = FakeContributionRepository()
    repo.fail_next_commit = True
    with pytest.raises(RuntimeError, match="injected_contribution_commit_failure"):
        await _submit(repo, key="rollback-submit")
    assert repo.records == {}
    assert repo.operations == {}
    assert repo.audits == []
    assert repo.outbox == []
    assert repo.platform_points == []
    recovered = await _submit(repo, key="rollback-submit")
    assert recovered.status is ContributionStatus.SUBMITTED


async def test_withdrawal_and_appeal_cannot_skip_use_confirmation(contribution_repo) -> None:
    record = await _submit(contribution_repo, key="withdraw-submit")
    withdrawn = await withdraw_contribution(
        contribution_repo,
        _ctx(key="withdraw"),
        record.contribution_id,
        reason_code="CONTRIBUTOR_WITHDREW",
    )
    assert withdrawn.status is ContributionStatus.REJECTED
    appealed = await appeal_contribution(
        contribution_repo,
        _ctx(key="withdraw-appeal"),
        record.contribution_id,
        appeal_ref="appeal:withdraw",
        reason="please reconsider",
    )
    restored_to_review = await resolve_appeal(
        contribution_repo,
        _ctx(key="withdraw-appeal-resolve"),
        record.contribution_id,
        approved=True,
        decision_code="APPEAL_ACCEPTED_REQUIRES_FAMILY_USE_CONFIRMATION",
    )
    assert appealed.status is ContributionStatus.APPEAL
    assert restored_to_review.status is ContributionStatus.VERIFIED
    assert await contribution_repo.list_platform_points(TENANT, CONTRIBUTOR_FAMILY) == []


async def test_refund_reversal_is_negative_and_preserves_original_fact(contribution_repo) -> None:
    released = await _released(contribution_repo, prefix="refund")
    reversed_record = await reverse_released_contribution(
        contribution_repo,
        _ctx(key="refund-reversal"),
        released.contribution_id,
        refund_ref="refund:1",
    )
    replay = await reverse_released_contribution(
        contribution_repo,
        _ctx(key="refund-reversal"),
        released.contribution_id,
        refund_ref="refund:1",
    )
    assert reversed_record.status is ContributionStatus.REVERSED
    assert replay.status is ContributionStatus.REVERSED
    points = await contribution_repo.list_platform_points(TENANT, CONTRIBUTOR_FAMILY)
    assert [(point.points_delta, point.reversal_of_entry_id) for point in points] == [
        (20, None),
        (-20, points[0].entry_id),
    ]
    assert len(await contribution_repo.list_audits(TENANT, released.contribution_id)) == 7


def test_points_fgcn_units_and_settlement_amounts_are_distinct_ledgers() -> None:
    unit = FGCNContributionUnit(
        unit_id="fgcn-unit-1",
        contribution_id="contribution-1",
        units=2,
        allocation_basis_ref="case-allocation-1",
    )
    settlement = SettlementAmount(
        settlement_id="settlement-1",
        contribution_id="contribution-1",
        minor_units=1000,
        currency="CNY",
        settlement_basis_ref="adult-settlement-1",
    )
    assert type(unit) is not type(settlement)
    assert "points_delta" not in type(unit).model_fields
    assert "minor_units" not in type(unit).model_fields


def test_reward_basis_deny_list_is_explicit_and_not_child_driven() -> None:
    with pytest.raises(ContributionForbiddenError, match="child_or_outcome_reward_basis_forbidden"):
        require_safe_reward_basis("CHILD_EMOTION_SCORE")
    with pytest.raises(ContributionValidationError, match="unsupported_reward_basis"):
        require_safe_reward_basis("UNRELATED_BASIS")
    assert "child_person_id" not in ContributionRecord.model_fields
