"""HTTP-layer tests for the membership router.

The interesting assertions here are the negative ones. The acceptance-chain test
already proves the domain works; what only an HTTP test can prove is that the
transport does not hand out authority the domain layer assumed it had:

* scope comes from the authenticated context, not from anything the client sent;
* an AI actor cannot move a tier, even by claiming to be a guardian;
* unknown surfaces 404 instead of 500.

`dependency_overrides` supplies the repository, context, and actor — the
production dependencies raise on purpose (a default tenant/family/actor would
fail open), so overriding is the intended mechanism, not a workaround.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.domains.membership.api import routes
from backend.domains.membership.api.dependencies import (
    get_action_context,
    get_actor_context,
    get_audit_recorder,
    get_repository,
)
from backend.domains.membership.application.context import ActionContext
from backend.domains.membership.infrastructure.fake_repository import FakeMembershipRepository
from backend.platform.audit.recorder import AuditRecorder
from backend.platform.identity.context import ActorContext, ActorType
from tests.domains.membership.helpers import FAMILY, GUARDIAN, TENANT, seed_catalogue

FOREIGN_FAMILY = "family-999"
FOREIGN_TENANT = "tenant-999"


def _ctx(idempotency_key: str | None = None, actor: str = "guardian:001") -> ActionContext:
    return ActionContext(
        tenant_id=TENANT,
        family_id=FAMILY,
        actor_person_id=GUARDIAN,
        actor=actor,
        correlation_id="corr-http",
        environment="TEST",
        idempotency_key=idempotency_key,
    )


def _actor(actor_type: ActorType = ActorType.HUMAN, actor_id: str = "guardian:001") -> ActorContext:
    return ActorContext(
        actor_id=actor_id,
        actor_type=actor_type,
        tenant_id=TENANT,
        correlation_id="corr-http",
    )


class Harness:
    """An app wired to one shared Fake repository plus swappable context/actor."""

    def __init__(self) -> None:
        self.repo = FakeMembershipRepository()
        self.recorder = AuditRecorder()
        self.ctx = _ctx()
        self.actor = _actor()
        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[get_repository] = lambda: self.repo
        app.dependency_overrides[get_action_context] = lambda: self.ctx
        app.dependency_overrides[get_actor_context] = lambda: self.actor
        app.dependency_overrides[get_audit_recorder] = lambda: self.recorder
        self.client = TestClient(app)


@pytest.fixture
def harness() -> Harness:
    return Harness()


async def test_full_chain_over_http(harness: Harness) -> None:
    plan, benefit_def = await seed_catalogue(harness.repo)
    c = harness.client

    harness.ctx = _ctx("http-sub-1")
    sub = c.post(
        "/membership/subscriptions",
        json={
            "plan_id": plan.plan_id,
            "subscription_ref": "SUB-HTTP-1",
            "consent_ref": "consent-http-1",
        },
    )
    assert sub.status_code == 200, sub.text
    subscription_id = sub.json()["membership_subscription_id"]

    harness.ctx = _ctx("http-tier-0")
    m0 = c.post(
        "/membership/tier-activations",
        json={
            "to_tier": "M0_FREE",
            "activation_source_type": "FAMILY_ACCOUNT_CREATED",
            "activation_source_ref": "account:family-001",
        },
    )
    assert m0.status_code == 200, m0.text
    # decided_by is not a request field; the route derives it from the context.
    assert m0.json()["transition"]["decided_by"] == "guardian:001"

    harness.ctx = _ctx("http-tier-1")
    m1 = c.post(
        "/membership/tier-activations",
        json={
            "to_tier": "M1_GROWTH",
            "activation_source_type": "GROWTH_PRODUCT_ACTIVATED",
            "activation_source_ref": "program:90day",
            "period_days": 90,
            "membership_subscription_id": subscription_id,
        },
    )
    assert m1.status_code == 200, m1.text

    harness.ctx = _ctx("http-grant-1")
    grant = c.post(
        "/membership/benefit-grants",
        json={
            "membership_subscription_id": subscription_id,
            "benefit_definition_id": benefit_def.benefit_definition_id,
            "grant_ref": "GRANT-HTTP-1",
            "source_page_id": "UI-30",
        },
    )
    assert grant.status_code == 200, grant.text
    grant_id = grant.json()["benefit_grant_id"]

    harness.ctx = _ctx("http-resv-1")
    resv = c.post(
        "/membership/benefit-reservations",
        json={"benefit_grant_id": grant_id, "reservation_ref": "RESV-HTTP-1", "units": 1},
    )
    assert resv.status_code == 200, resv.text

    harness.ctx = _ctx("http-consume-1")
    consumed = c.post(
        "/membership/benefit-consumptions",
        json={
            "benefit_grant_id": grant_id,
            "units": 1,
            "source_page_id": "UI-31",
            "benefit_reservation_id": resv.json()["benefit_reservation_id"],
        },
    )
    assert consumed.status_code == 200, consumed.text
    assert consumed.json()["remaining_units"] == 1

    projection = c.get("/membership/projection")
    assert projection.status_code == 200
    assert projection.json()["tier_code"] == "M1_GROWTH"

    for surface in ("UI-06", "UI-18", "UI-30", "UI-32"):
        screen = c.get(f"/membership/screens/{surface}")
        assert screen.status_code == 200, screen.text
        assert screen.json()["surface_id"] == surface


async def test_ai_actor_cannot_move_a_tier(harness: Harness) -> None:
    """R8/R9. The AI actor is refused by the fail-closed policy engine before
    the domain layer is ever reached — and crucially it cannot launder itself
    into a human by naming a `decided_by`, because that field no longer exists
    on the wire."""
    await seed_catalogue(harness.repo)
    harness.actor = _actor(ActorType.AI, "ai:growth.copilot")
    harness.ctx = _ctx("http-ai-1", actor="ai:growth.copilot")

    response = harness.client.post(
        "/membership/tier-activations",
        json={
            "to_tier": "M2_ANNUAL",
            "activation_source_type": "ANNUAL_MEMBERSHIP_ACTIVATED",
            "activation_source_ref": "order:annual",
            "decided_by": "guardian:001",  # ignored: not a model field
        },
    )
    assert response.status_code == 403
    assert "human_only" in response.json()["detail"]

    denials = [e for e in harness.recorder.all_events() if e.action.endswith(":denied")]
    assert denials, "拒绝也必须留审计 —— 被拒的升档尝试正是运营需要看见的事件"


async def test_body_cannot_override_family_or_tenant_scope(harness: Harness) -> None:
    """A foreign `family_id`/`tenant_id` in the body must have no effect: scope
    is server-derived. If this ever regresses, one family could write into
    another's membership."""
    plan, _ = await seed_catalogue(harness.repo)
    harness.ctx = _ctx("http-scope-1")

    response = harness.client.post(
        "/membership/subscriptions",
        json={
            "plan_id": plan.plan_id,
            "subscription_ref": "SUB-SCOPE-1",
            "consent_ref": "consent-scope-1",
            "family_id": FOREIGN_FAMILY,
            "tenant_id": FOREIGN_TENANT,
            "actor_person_id": "person-attacker",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["family_id"] == FAMILY
    assert body["tenant_id"] == TENANT
    assert body["actor_person_id"] == GUARDIAN
    assert await harness.repo.list_subscriptions(FOREIGN_TENANT, FOREIGN_FAMILY) == []


async def test_idempotent_replay_returns_the_same_entity(harness: Harness) -> None:
    plan, _ = await seed_catalogue(harness.repo)
    harness.ctx = _ctx("http-replay-1")
    payload = {
        "plan_id": plan.plan_id,
        "subscription_ref": "SUB-REPLAY-1",
        "consent_ref": "consent-replay-1",
    }
    first = harness.client.post("/membership/subscriptions", json=payload)
    second = harness.client.post("/membership/subscriptions", json=payload)
    assert first.status_code == second.status_code == 200
    assert (
        first.json()["membership_subscription_id"] == second.json()["membership_subscription_id"]
    )
    assert len(await harness.repo.list_subscriptions(TENANT, FAMILY)) == 1


async def test_domain_errors_map_to_distinct_status_codes(harness: Harness) -> None:
    plan, _ = await seed_catalogue(harness.repo)

    # 404 — unknown plan.
    harness.ctx = _ctx("http-404")
    missing = harness.client.post(
        "/membership/subscriptions",
        json={"plan_id": "plan-nope", "subscription_ref": "S", "consent_ref": "c"},
    )
    assert missing.status_code == 404

    # 403 — a forbidden activation source (points may never move a tier).
    harness.ctx = _ctx("http-403")
    forbidden = harness.client.post(
        "/membership/tier-activations",
        json={
            "to_tier": "M2_ANNUAL",
            "activation_source_type": "POINTS_REDEMPTION",
            "activation_source_ref": "redemption:1",
        },
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "activation_source_forbidden:points_redemption"

    # 400 — source and target disagree.
    harness.ctx = _ctx("http-400")
    mismatch = harness.client.post(
        "/membership/tier-activations",
        json={
            "to_tier": "M2_ANNUAL",
            "activation_source_type": "FAMILY_ACCOUNT_CREATED",
            "activation_source_ref": "account:x",
        },
    )
    assert mismatch.status_code == 400

    # 409 — renewal with no active period.
    harness.ctx = _ctx("http-409")
    conflict = harness.client.post(
        "/membership/period-renewals", json={"activation_source_ref": "order:x"}
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "no_active_period_to_renew"


async def test_unknown_screen_is_404_not_500(harness: Harness) -> None:
    await seed_catalogue(harness.repo)
    assert harness.client.get("/membership/screens/UI-99").status_code == 404
    # UI-13 is in MEMBERSHIP_READ_SURFACES but has no membership query function;
    # the dispatch table, not the surface set, decides what this router serves.
    assert harness.client.get("/membership/screens/UI-13").status_code == 404


async def test_every_write_leaves_an_audit_event(harness: Harness) -> None:
    """R6: 无审计不得改状态."""
    plan, _ = await seed_catalogue(harness.repo)
    harness.ctx = _ctx("http-audit-1")
    harness.client.post(
        "/membership/subscriptions",
        json={
            "plan_id": plan.plan_id,
            "subscription_ref": "SUB-AUDIT-1",
            "consent_ref": "consent-audit-1",
        },
    )
    actions = [e.action for e in harness.recorder.all_events()]
    assert "subscribe_membership" in actions
    event = next(e for e in harness.recorder.all_events() if e.action == "subscribe_membership")
    assert event.actor_id and event.tenant_id and event.correlation_id and event.reason
