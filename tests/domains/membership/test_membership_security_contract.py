"""Reverse tests for the Membership fixes owned by this slice.

These tests cover the shared application/repository contract. The parametrized
repository fixture includes SQLite and an opt-in PostgreSQL adapter; the
PostgreSQL case remains an explicit skip when no database is configured. They
do not claim that the canonical migration chain has the V2 lifecycle tables.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from backend.domains.membership.application import commands, queries
from backend.domains.membership.domain.entities import utcnow
from backend.domains.membership.domain.errors import (
    MembershipConflictError,
    MembershipForbiddenError,
    MembershipNotFoundError,
)
from backend.domains.membership.infrastructure.fake_repository import FakeMembershipRepository
from tests.domains.membership.helpers import FAMILY, TENANT, make_ctx, seed_catalogue


async def test_entity_ids_are_not_readable_outside_their_scope(repo) -> None:
    plan, _ = await seed_catalogue(repo)
    subscription = await commands.subscribe_membership(
        repo,
        make_ctx(idempotency_key="scope-sub"),
        plan_id=plan.plan_id,
        subscription_ref="scope-subscription",
        consent_ref="consent-scope",
    )

    with pytest.raises(MembershipNotFoundError):
        await repo.load_subscription(
            subscription.membership_subscription_id,
            tenant_id="tenant-foreign",
            family_id="family-foreign",
        )

    assert await repo.list_subscriptions(TENANT, FAMILY) == [subscription]


async def test_same_idempotency_key_with_different_input_is_conflict(repo) -> None:
    plan, _ = await seed_catalogue(repo)
    await commands.subscribe_membership(
        repo,
        make_ctx(idempotency_key="same-key"),
        plan_id=plan.plan_id,
        subscription_ref="subscription-a",
        consent_ref="consent-a",
    )

    with pytest.raises(MembershipConflictError, match="idempotency_key_conflict"):
        await commands.subscribe_membership(
            repo,
            make_ctx(idempotency_key="same-key"),
            plan_id=plan.plan_id,
            subscription_ref="subscription-b",
            consent_ref="consent-a",
        )

    assert len(await repo.list_subscriptions(TENANT, FAMILY)) == 1


async def test_ai_cannot_replay_a_membership_command() -> None:
    repo = FakeMembershipRepository()
    plan, _ = await seed_catalogue(repo)
    await commands.subscribe_membership(
        repo,
        make_ctx(idempotency_key="human-command"),
        plan_id=plan.plan_id,
        subscription_ref="human-subscription",
        consent_ref="consent-human",
    )

    with pytest.raises(MembershipForbiddenError, match="requires_human_actor"):
        await commands.subscribe_membership(
            repo,
            make_ctx(idempotency_key="human-command", actor="ai:companion"),
            plan_id=plan.plan_id,
            subscription_ref="human-subscription",
            consent_ref="consent-human",
        )


async def test_expired_grant_is_not_consumable_or_presented_as_available(repo) -> None:
    plan, benefit_definition = await seed_catalogue(repo)
    subscription = await commands.subscribe_membership(
        repo,
        make_ctx(idempotency_key="expired-sub"),
        plan_id=plan.plan_id,
        subscription_ref="expired-subscription",
        consent_ref="consent-expired",
    )
    await commands.activate_membership_tier(
        repo,
        make_ctx(idempotency_key="expired-tier"),
        to_tier="M0_FREE",
        activation_source_type="FAMILY_ACCOUNT_CREATED",
        activation_source_ref="account:expired-family",
        decided_by="guardian:001",
    )
    grant = await commands.grant_membership_benefit(
        repo,
        make_ctx(idempotency_key="expired-grant"),
        membership_subscription_id=subscription.membership_subscription_id,
        benefit_definition_id=benefit_definition.benefit_definition_id,
        grant_ref="expired-grant-ref",
        source_page_id="UI-30",
    )
    expired_at = utcnow() - timedelta(seconds=1)
    expired = grant.model_copy(
        update={
            "valid_from": expired_at - timedelta(days=1),
            "valid_to": expired_at,
        }
    )
    await repo.save_benefit_grant(expired)
    await repo.commit()

    with pytest.raises(MembershipConflictError, match="grant_not_available"):
        await commands.consume_membership_benefit(
            repo,
            make_ctx(idempotency_key="expired-consume"),
            benefit_grant_id=grant.benefit_grant_id,
            units=1,
            source_page_id="UI-31",
        )

    projection = await queries.get_membership_projection(
        repo, tenant_id=TENANT, family_id=FAMILY
    )
    assert projection.benefits[0].status == "EXPIRED"
    assert projection.benefits[0].remaining_units == grant.remaining_units
    assert "可用权益 0 项" in projection.text_equivalent


async def test_benefit_definition_from_another_plan_is_rejected(repo) -> None:
    plan, benefit_definition = await seed_catalogue(repo)
    subscription = await commands.subscribe_membership(
        repo,
        make_ctx(idempotency_key="plan-scope-sub"),
        plan_id=plan.plan_id,
        subscription_ref="plan-scope-subscription",
        consent_ref="consent-plan-scope",
    )
    await repo.save_benefit_definition(
        benefit_definition.model_copy(update={"plan_id": "another-plan"})
    )
    await repo.commit()

    with pytest.raises(MembershipForbiddenError, match="benefit_definition_plan_mismatch"):
        await commands.grant_membership_benefit(
            repo,
            make_ctx(idempotency_key="plan-scope-grant"),
            membership_subscription_id=subscription.membership_subscription_id,
            benefit_definition_id=benefit_definition.benefit_definition_id,
            grant_ref="plan-scope-grant-ref",
            source_page_id="UI-30",
        )


async def test_revoke_releases_held_reservations(repo) -> None:
    plan, benefit_definition = await seed_catalogue(repo)
    subscription = await commands.subscribe_membership(
        repo,
        make_ctx(idempotency_key="revoke-sub"),
        plan_id=plan.plan_id,
        subscription_ref="revoke-subscription",
        consent_ref="consent-revoke",
    )
    grant = await commands.grant_membership_benefit(
        repo,
        make_ctx(idempotency_key="revoke-grant"),
        membership_subscription_id=subscription.membership_subscription_id,
        benefit_definition_id=benefit_definition.benefit_definition_id,
        grant_ref="revoke-grant-ref",
        source_page_id="UI-30",
    )
    reservation = await commands.reserve_membership_benefit(
        repo,
        make_ctx(idempotency_key="revoke-reservation"),
        benefit_grant_id=grant.benefit_grant_id,
        reservation_ref="revoke-reservation-ref",
        units=1,
    )

    revoked = await commands.revoke_membership_benefit(
        repo,
        make_ctx(idempotency_key="revoke-command"),
        benefit_grant_id=grant.benefit_grant_id,
        source_page_id="UI-30",
        decided_by="guardian:001",
    )

    assert revoked.status == "REVOKED"
    assert (await repo.load_reservation(reservation.benefit_reservation_id)).status == "RELEASED"
    assert [entry.action for entry in await repo.list_benefit_ledger(TENANT, FAMILY)] == [
        "GRANT",
        "REVOKE",
    ]


async def test_reservation_and_consume_cannot_double_spend(repo) -> None:
    plan, benefit_definition = await seed_catalogue(repo)
    subscription = await commands.subscribe_membership(
        repo,
        make_ctx(idempotency_key="double-spend-sub"),
        plan_id=plan.plan_id,
        subscription_ref="double-spend-subscription",
        consent_ref="consent-double-spend",
    )
    grant = await commands.grant_membership_benefit(
        repo,
        make_ctx(idempotency_key="double-spend-grant"),
        membership_subscription_id=subscription.membership_subscription_id,
        benefit_definition_id=benefit_definition.benefit_definition_id,
        grant_ref="double-spend-grant-ref",
        source_page_id="UI-30",
    )
    reservation = await commands.reserve_membership_benefit(
        repo,
        make_ctx(idempotency_key="double-spend-reservation"),
        benefit_grant_id=grant.benefit_grant_id,
        reservation_ref="double-spend-reservation-ref",
        units=2,
    )
    with pytest.raises(MembershipConflictError, match="grant_insufficient_unreserved_units"):
        await commands.reserve_membership_benefit(
            repo,
            make_ctx(idempotency_key="double-spend-reservation-again"),
            benefit_grant_id=grant.benefit_grant_id,
            reservation_ref="double-spend-reservation-ref-2",
            units=1,
        )

    first = await commands.consume_membership_benefit(
        repo,
        make_ctx(idempotency_key="double-spend-consume"),
        benefit_grant_id=grant.benefit_grant_id,
        units=2,
        source_page_id="UI-31",
        benefit_reservation_id=reservation.benefit_reservation_id,
    )
    replay = await commands.consume_membership_benefit(
        repo,
        make_ctx(idempotency_key="double-spend-consume"),
        benefit_grant_id=grant.benefit_grant_id,
        units=2,
        source_page_id="UI-31",
        benefit_reservation_id=reservation.benefit_reservation_id,
    )
    assert first.remaining_units == replay.remaining_units == 0
    assert len(await repo.list_benefit_ledger(TENANT, FAMILY)) == 2

    with pytest.raises(MembershipConflictError, match="grant_not_available"):
        await commands.consume_membership_benefit(
            repo,
            make_ctx(idempotency_key="double-spend-consume-again"),
            benefit_grant_id=grant.benefit_grant_id,
            units=1,
            source_page_id="UI-31",
        )


async def test_fake_commit_failure_restores_every_staged_write() -> None:
    repo = FakeMembershipRepository()
    plan, _ = await seed_catalogue(repo)
    repo.fail_commit = RuntimeError("commit unavailable")

    with pytest.raises(RuntimeError, match="commit unavailable"):
        await commands.subscribe_membership(
            repo,
            make_ctx(idempotency_key="commit-failure"),
            plan_id=plan.plan_id,
            subscription_ref="not-persisted",
            consent_ref="consent-failure",
        )

    assert await repo.list_subscriptions(TENANT, FAMILY) == []
    assert repo._snapshot is None


async def test_ledger_append_failure_rolls_back_grant_and_reservation() -> None:
    repo = FakeMembershipRepository()
    plan, benefit_definition = await seed_catalogue(repo)
    subscription = await commands.subscribe_membership(
        repo,
        make_ctx(idempotency_key="append-failure-sub"),
        plan_id=plan.plan_id,
        subscription_ref="append-failure-subscription",
        consent_ref="consent-append-failure",
    )
    grant = await commands.grant_membership_benefit(
        repo,
        make_ctx(idempotency_key="append-failure-grant"),
        membership_subscription_id=subscription.membership_subscription_id,
        benefit_definition_id=benefit_definition.benefit_definition_id,
        grant_ref="append-failure-grant-ref",
        source_page_id="UI-30",
    )
    reservation = await commands.reserve_membership_benefit(
        repo,
        make_ctx(idempotency_key="append-failure-reservation"),
        benefit_grant_id=grant.benefit_grant_id,
        reservation_ref="append-failure-reservation-ref",
        units=1,
    )
    repo.fail_append_ledger = RuntimeError("ledger unavailable")

    with pytest.raises(RuntimeError, match="ledger unavailable"):
        await commands.consume_membership_benefit(
            repo,
            make_ctx(idempotency_key="append-failure-consume"),
            benefit_grant_id=grant.benefit_grant_id,
            units=1,
            source_page_id="UI-31",
            benefit_reservation_id=reservation.benefit_reservation_id,
        )

    restored_grant = await repo.load_benefit_grant(grant.benefit_grant_id)
    restored_reservation = await repo.load_reservation(reservation.benefit_reservation_id)
    assert (restored_grant.status, restored_grant.remaining_units) == ("AVAILABLE", 2)
    assert restored_reservation.status == "HELD"
    assert [e.action for e in await repo.list_benefit_ledger(TENANT, FAMILY)] == ["GRANT"]
    assert repo._snapshot is None


async def test_subscription_state_methods_refuse_ai_actor_and_allow_pause_resume() -> None:
    repo = FakeMembershipRepository()
    plan, _ = await seed_catalogue(repo)
    subscription = await commands.subscribe_membership(
        repo,
        make_ctx(idempotency_key="state-sub"),
        plan_id=plan.plan_id,
        subscription_ref="state-subscription",
        consent_ref="consent-state",
    )

    with pytest.raises(MembershipForbiddenError, match="requires_human_actor"):
        subscription.pause(actor="ai:companion")

    paused = subscription.pause(actor="guardian:001")
    resumed = paused.resume(actor="guardian:001")
    assert (paused.status, resumed.status) == ("PAUSED", "ACTIVE")
