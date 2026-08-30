"""PolicyEngine fail-closed behavior.

Behavior re-derived from the source repository's
`family-authorization.policy.ts` test semantics: an unknown role/action
combination must fail closed (DENY), not fail open.
"""

from __future__ import annotations

from backend.platform.authorization.policy import PolicyEngine, PolicyRule
from backend.platform.identity.context import ActorContext, ActorType, TenantStatus
from backend.platform.identity.directory import InMemoryTenantDirectory

ACTIVE_TENANTS = InMemoryTenantDirectory({"tenant-1": TenantStatus.ACTIVE})


def _actor(actor_type: ActorType) -> ActorContext:
    return ActorContext(
        actor_id="actor-1",
        actor_type=actor_type,
        tenant_id="tenant-1",
        correlation_id="corr-1",
    )


def test_unregistered_action_resource_pair_is_denied() -> None:
    engine = PolicyEngine(ACTIVE_TENANTS)
    decision = engine.check(_actor(ActorType.HUMAN), action="delete", resource_type="family")

    assert decision.allowed is False
    assert "fail-closed" in decision.reason


def test_explicit_allow_rule_grants_access() -> None:
    engine = PolicyEngine(ACTIVE_TENANTS)
    engine.register(PolicyRule(action="view", resource_type="family"))

    decision = engine.check(_actor(ActorType.HUMAN), action="view", resource_type="family")

    assert decision.allowed is True


def test_rule_scoped_to_actor_types_denies_unlisted_actor_type() -> None:
    engine = PolicyEngine(ACTIVE_TENANTS)
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
    engine = PolicyEngine(ACTIVE_TENANTS)
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
    engine = PolicyEngine(ACTIVE_TENANTS)
    engine.register(
        PolicyRule(action="write_canonical_fact", resource_type="family_fact", human_only=True)
    )

    decision = engine.check(
        _actor(ActorType.AI), action="write_canonical_fact", resource_type="family_fact"
    )

    assert decision.allowed is False
    assert "human_only" in decision.reason
    assert "AI" in decision.reason


# --- R9 bypass regression: two rules on the same (action, resource_type) key ---
#
# The engine used to return ALLOW on the first matching rule whose permits() was
# True, which made `human_only` order-dependent: registering a permissive rule
# before a human_only rule for the same key let an AI actor write canonical
# facts. That is a real R9 bypass ("AI 输出不得自动成为事实"), because human_only
# *is* the enforcement point for R9 at this layer. The tests below pin
# deny-overrides semantics in both registration orders; none of the five tests
# above registers two rules on one key, which is why the bypass survived.

_PERMISSIVE = PolicyRule(action="write_canonical_fact", resource_type="family_fact")
_HUMAN_ONLY = PolicyRule(
    action="write_canonical_fact", resource_type="family_fact", human_only=True
)


def _engine_with(*rules: PolicyRule) -> PolicyEngine:
    engine = PolicyEngine(ACTIVE_TENANTS)
    for rule in rules:
        engine.register(rule)
    return engine


def test_permissive_rule_registered_before_human_only_still_denies_ai() -> None:
    engine = _engine_with(_PERMISSIVE, _HUMAN_ONLY)

    decision = engine.check(
        _actor(ActorType.AI), action="write_canonical_fact", resource_type="family_fact"
    )

    assert decision.allowed is False
    assert "human_only" in decision.reason


def test_human_only_registered_before_permissive_rule_denies_ai() -> None:
    engine = _engine_with(_HUMAN_ONLY, _PERMISSIVE)

    decision = engine.check(
        _actor(ActorType.AI), action="write_canonical_fact", resource_type="family_fact"
    )

    assert decision.allowed is False
    assert "human_only" in decision.reason


def test_human_only_veto_is_independent_of_registration_order() -> None:
    """Both orders must yield the identical decision — the veto is set-level."""
    forward = _engine_with(_PERMISSIVE, _HUMAN_ONLY).check(
        _actor(ActorType.AI), action="write_canonical_fact", resource_type="family_fact"
    )
    reverse = _engine_with(_HUMAN_ONLY, _PERMISSIVE).check(
        _actor(ActorType.AI), action="write_canonical_fact", resource_type="family_fact"
    )

    assert forward == reverse
    assert forward.allowed is False


def test_ai_denied_even_when_a_matching_rule_explicitly_allows_ai_actor_type() -> None:
    """A rule naming AI in allowed_actor_types does not defeat a sibling veto."""
    ai_allowed = PolicyRule(
        action="write_canonical_fact",
        resource_type="family_fact",
        allowed_actor_types=frozenset({ActorType.AI}),
    )
    engine = _engine_with(ai_allowed, _HUMAN_ONLY)

    decision = engine.check(
        _actor(ActorType.AI), action="write_canonical_fact", resource_type="family_fact"
    )

    assert decision.allowed is False
    assert "human_only" in decision.reason


def test_multiple_permissive_rules_do_not_outvote_a_single_human_only_rule() -> None:
    """human_only is a veto, not a vote: 3 permissive vs 1 veto still denies."""
    engine = _engine_with(_PERMISSIVE, _PERMISSIVE, _PERMISSIVE, _HUMAN_ONLY)

    decision = engine.check(
        _actor(ActorType.AI), action="write_canonical_fact", resource_type="family_fact"
    )

    assert decision.allowed is False


def test_human_actor_allowed_in_both_registration_orders() -> None:
    """The fix must not deny humans: human_only vetoes AI actors only."""
    forward = _engine_with(_PERMISSIVE, _HUMAN_ONLY).check(
        _actor(ActorType.HUMAN), action="write_canonical_fact", resource_type="family_fact"
    )
    reverse = _engine_with(_HUMAN_ONLY, _PERMISSIVE).check(
        _actor(ActorType.HUMAN), action="write_canonical_fact", resource_type="family_fact"
    )

    assert forward.allowed is True
    assert reverse.allowed is True


def test_system_actor_allowed_in_both_registration_orders() -> None:
    """SYSTEM is not AI, so the veto must not catch platform jobs either."""
    forward = _engine_with(_PERMISSIVE, _HUMAN_ONLY).check(
        _actor(ActorType.SYSTEM), action="write_canonical_fact", resource_type="family_fact"
    )
    reverse = _engine_with(_HUMAN_ONLY, _PERMISSIVE).check(
        _actor(ActorType.SYSTEM), action="write_canonical_fact", resource_type="family_fact"
    )

    assert forward.allowed is True
    assert reverse.allowed is True


def test_human_only_veto_is_scoped_to_its_own_key() -> None:
    """A veto on one key must not leak into a different (action, resource_type)."""
    engine = _engine_with(
        _HUMAN_ONLY,
        PolicyRule(action="read_perspective", resource_type="family_fact"),
    )

    decision = engine.check(
        _actor(ActorType.AI), action="read_perspective", resource_type="family_fact"
    )

    assert decision.allowed is True


def test_unregistered_pair_still_denies_when_other_rules_exist() -> None:
    """Fail-closed default must survive the deny-overrides rewrite."""
    engine = _engine_with(_PERMISSIVE, _HUMAN_ONLY)

    for actor_type in (ActorType.HUMAN, ActorType.AI, ActorType.SYSTEM):
        decision = engine.check(
            _actor(actor_type), action="write_canonical_fact", resource_type="other_resource"
        )
        assert decision.allowed is False
        assert "fail-closed" in decision.reason
