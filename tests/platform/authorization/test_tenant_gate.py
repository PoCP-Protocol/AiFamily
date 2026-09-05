"""The tenant gate: a suspended tenant is refused by `PolicyEngine`.

This is the enforcement test for `docs/06_platform/IDENTITY.md` §3 gap 3
("`TenantContext.is_active` 无任何调用方"). Before this, a tenant could be marked
SUSPENDED and keep operating, because nothing ever read the flag.

The gate is placed at the authorization boundary rather than inside business
methods on purpose (see `backend/platform/identity/directory.py`): a rule
enforced in forty methods is enforced in thirty-nine. These tests therefore
assert the property that matters — **no registration can grant a non-ACTIVE
tenant anything** — not merely that some helper returns False.
"""

from __future__ import annotations

import pytest

from backend.platform.authorization.policy import PolicyEngine, PolicyRule
from backend.platform.identity.context import ActorContext, ActorType, TenantStatus
from backend.platform.identity.directory import (
    DenyAllTenantDirectory,
    InMemoryTenantDirectory,
)

PERMISSIVE = PolicyRule(action="view", resource_type="family")


def _actor(actor_type: ActorType = ActorType.HUMAN, tenant_id: str = "tenant-1") -> ActorContext:
    return ActorContext(
        actor_id="actor-1",
        actor_type=actor_type,
        tenant_id=tenant_id,
        correlation_id="corr-1",
    )


def _engine(status: TenantStatus) -> PolicyEngine:
    engine = PolicyEngine(InMemoryTenantDirectory({"tenant-1": status}))
    engine.register(PERMISSIVE)
    return engine


def test_active_tenant_is_allowed_by_a_permissive_rule() -> None:
    """Control case — without this the gate could be passing by denying everything."""
    decision = _engine(TenantStatus.ACTIVE).check(_actor(), action="view", resource_type="family")
    assert decision.allowed is True


@pytest.mark.parametrize("status", [TenantStatus.SUSPENDED, TenantStatus.ARCHIVED])
def test_non_active_tenant_is_denied_despite_a_permissive_rule(status: TenantStatus) -> None:
    decision = _engine(status).check(_actor(), action="view", resource_type="family")

    assert decision.allowed is False
    assert status.value in decision.reason
    assert "tenant-1" in decision.reason


@pytest.mark.parametrize("actor_type", list(ActorType))
def test_suspended_tenant_is_denied_for_every_actor_type(actor_type: ActorType) -> None:
    """Including SYSTEM: a background job must not outrank tenant suspension."""
    decision = _engine(TenantStatus.SUSPENDED).check(
        _actor(actor_type), action="view", resource_type="family"
    )
    assert decision.allowed is False


def test_unknown_tenant_is_denied_not_assumed_active() -> None:
    engine = PolicyEngine(DenyAllTenantDirectory())
    engine.register(PERMISSIVE)

    decision = engine.check(_actor(), action="view", resource_type="family")

    assert decision.allowed is False
    assert "not known to the tenant directory" in decision.reason


def test_actor_from_a_different_tenant_than_the_registered_one_is_denied() -> None:
    """The gate reads `actor.tenant_id`; it does not accept a tenant by proximity."""
    engine = _engine(TenantStatus.ACTIVE)

    decision = engine.check(_actor(tenant_id="tenant-2"), action="view", resource_type="family")

    assert decision.allowed is False
    assert "tenant-2" in decision.reason


def test_no_number_of_permissive_rules_can_outvote_tenant_suspension() -> None:
    engine = PolicyEngine(InMemoryTenantDirectory({"tenant-1": TenantStatus.SUSPENDED}))
    for _ in range(5):
        engine.register(PolicyRule(action="view", resource_type="family"))
        engine.register(
            PolicyRule(
                action="view",
                resource_type="family",
                allowed_actor_types=frozenset(ActorType),
            )
        )

    decision = engine.check(_actor(), action="view", resource_type="family")
    assert decision.allowed is False


def test_tenant_veto_is_reported_as_a_tenant_problem_not_as_a_missing_rule() -> None:
    """A suspended tenant asking for an unregistered action must still say 'tenant'.

    The tenant veto runs before rule matching so an operator reading the audit
    trail sees the real cause. If it ran after, every suspended-tenant denial
    for an unregistered action would be mislabelled 'fail-closed default DENY'
    and the suspension would be invisible.
    """
    engine = PolicyEngine(InMemoryTenantDirectory({"tenant-1": TenantStatus.SUSPENDED}))

    decision = engine.check(_actor(), action="unregistered", resource_type="family")

    assert decision.allowed is False
    assert "suspended" in decision.reason
    assert "fail-closed" not in decision.reason


def test_policy_engine_cannot_be_constructed_without_a_tenant_directory() -> None:
    """No permissive default: the caller must say where tenant status comes from."""
    with pytest.raises(TypeError):
        PolicyEngine()  # type: ignore[call-arg]
