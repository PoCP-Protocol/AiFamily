"""PolicyEngine fail-closed behavior.

Behavior re-derived from the source repository's
`family-authorization.policy.ts` test semantics: an unknown role/action
combination must fail closed (DENY), not fail open.
"""

from __future__ import annotations

from backend.platform.authorization.policy import PolicyEngine, PolicyRule
from backend.platform.identity.context import ActorContext, ActorType


def _actor(actor_type: ActorType) -> ActorContext:
    return ActorContext(
        actor_id="actor-1",
        actor_type=actor_type,
        tenant_id="tenant-1",
        correlation_id="corr-1",
    )


def test_unregistered_action_resource_pair_is_denied() -> None:
    engine = PolicyEngine()
    decision = engine.check(_actor(ActorType.HUMAN), action="delete", resource_type="family")

    assert decision.allowed is False
    assert "fail-closed" in decision.reason


def test_explicit_allow_rule_grants_access() -> None:
    engine = PolicyEngine()
    engine.register(PolicyRule(action="view", resource_type="family"))

    decision = engine.check(_actor(ActorType.HUMAN), action="view", resource_type="family")

    assert decision.allowed is True


def test_rule_scoped_to_actor_types_denies_unlisted_actor_type() -> None:
    engine = PolicyEngine()
    engine.register(
        PolicyRule(
            action="approve",
            resource_type="growth_plan",
            allowed_actor_types=frozenset({ActorType.HUMAN}),
        )
    )

    human_decision = engine.check(
        _actor(ActorType.HUMAN), action="approve", resource_type="growth_plan"
    )
    system_decision = engine.check(
        _actor(ActorType.SYSTEM), action="approve", resource_type="growth_plan"
    )

    assert human_decision.allowed is True
    assert system_decision.allowed is False


def test_human_only_action_denies_ai_actor_even_if_generally_allowed() -> None:
    engine = PolicyEngine()
    engine.register(
        PolicyRule(
            action="write_canonical_fact",
            resource_type="family_fact",
            human_only=True,
        )
    )

    ai_decision = engine.check(
        _actor(ActorType.AI), action="write_canonical_fact", resource_type="family_fact"
    )
    human_decision = engine.check(
        _actor(ActorType.HUMAN), action="write_canonical_fact", resource_type="family_fact"
    )

    assert ai_decision.allowed is False
    assert human_decision.allowed is True


def test_human_only_denial_reason_mentions_ai() -> None:
    engine = PolicyEngine()
    engine.register(
        PolicyRule(action="write_canonical_fact", resource_type="family_fact", human_only=True)
    )

    decision = engine.check(
        _actor(ActorType.AI), action="write_canonical_fact", resource_type="family_fact"
    )

    assert decision.allowed is False
    assert "human_only" in decision.reason
    assert "AI" in decision.reason
