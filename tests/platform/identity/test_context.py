"""ActorContext / TenantContext behavior."""

from __future__ import annotations

import pytest

from backend.platform.identity.context import ActorContext, ActorType, TenantContext, TenantStatus


def _actor(actor_type: ActorType) -> ActorContext:
    return ActorContext(
        actor_id="actor-1",
        actor_type=actor_type,
        tenant_id="tenant-1",
        correlation_id="corr-1",
    )


def test_is_ai_true_only_for_ai_actor_type() -> None:
    ai_actor = _actor(ActorType.AI)
    human_actor = _actor(ActorType.HUMAN)
    system_actor = _actor(ActorType.SYSTEM)

    assert ai_actor.is_ai is True
    assert human_actor.is_ai is False
    assert system_actor.is_ai is False


def test_is_human_and_is_system_are_mutually_exclusive_with_is_ai() -> None:
    human_actor = _actor(ActorType.HUMAN)
    assert human_actor.is_human is True
    assert human_actor.is_ai is False
    assert human_actor.is_system is False


def test_actor_context_is_frozen() -> None:
    actor = _actor(ActorType.HUMAN)
    with pytest.raises(AttributeError):
        actor.actor_id = "someone-else"  # type: ignore[misc]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"actor_id": "", "actor_type": ActorType.HUMAN, "tenant_id": "t1", "correlation_id": "c1"},
        {"actor_id": "a1", "actor_type": ActorType.HUMAN, "tenant_id": "", "correlation_id": "c1"},
        {"actor_id": "a1", "actor_type": ActorType.HUMAN, "tenant_id": "t1", "correlation_id": ""},
    ],
)
def test_actor_context_rejects_empty_required_fields(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        ActorContext(**kwargs)


def test_tenant_context_is_active_reflects_status() -> None:
    active = TenantContext(tenant_id="t1", status=TenantStatus.ACTIVE)
    suspended = TenantContext(tenant_id="t1", status=TenantStatus.SUSPENDED)

    assert active.is_active is True
    assert suspended.is_active is False


def test_tenant_context_is_frozen() -> None:
    tenant = TenantContext(tenant_id="t1", status=TenantStatus.ACTIVE)
    with pytest.raises(AttributeError):
        tenant.tenant_id = "other"  # type: ignore[misc]
