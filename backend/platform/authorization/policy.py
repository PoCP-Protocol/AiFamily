"""PolicyEngine — minimal fail-closed authorization decision point.

Design intent (re-derived from the *behavior* the source repository's
`family-authorization.policy.ts` tested for, not from its implementation):
an authorization decision for an (actor, action, resource_type) triple that
has no registered rule must be DENY, never ALLOW. "Unknown" and "forbidden"
must be indistinguishable failure modes to a caller who forgets to register
something — that is what "fail closed" means, and it is the direct
countermeasure to the R7 scar in REPOSITORY_CONSTITUTION.md (a policy that
existed only as an unenforced constant).

This module does not attempt to be a general-purpose RBAC/ABAC system. It is
the smallest possible decision point that:
  1. defaults to DENY for anything unregistered,
  2. lets a caller register an explicit ALLOW rule for
     (action, resource_type), optionally scoped to certain actor types,
  3. always denies AI actors from actions marked `human_only=True`,
     regardless of whether an ALLOW rule was registered for that action
     and regardless of the order in which rules were registered,
  4. always denies an actor whose tenant is not ACTIVE, before any rule is
     consulted at all.

Point 4 is why `PolicyEngine.__init__` takes a **required** `TenantDirectory`
(`backend/platform/identity/directory.py`). `TenantContext.is_active` previously
had zero callers anywhere in the repository, so "a suspended tenant must not
operate" was not a rule — it was an unread property
(`docs/06_platform/IDENTITY.md` §3 gap 3). The check belongs here, at the one
authorization boundary every mutating route already passes through, rather than
inside each business method: a rule enforced in forty places is enforced in
thirty-nine. The directory argument has no default because a permissive default
would fail *open* for every tenant nobody remembered to register, and an
unknown tenant is denied for exactly the reason an unregistered action is.

Decision semantics: **deny-overrides, order-independent.** `check` collects
*every* rule matching (action, resource_type) before deciding, and evaluates
`human_only` across the whole matching set first. One `human_only=True` rule
vetoes an AI actor even if ten permissive rules for the same key also match,
and even if those permissive rules were registered first. This is not a
stylistic preference: `human_only` is the enforcement point for R9 ("AI 推断
只能生成 Perspective / Recommendation", never canonical fact), and an
enforcement point whose outcome depends on registration order is not an
enforcement point. The earlier implementation returned on the first rule whose
`permits()` was True, so `register(permissive); register(human_only)` let an AI
actor through — a real R9 bypass, documented in
`docs/06_platform/AUTHORIZATION.md` §3 gap 1 and closed here.

The engine has no order-dependent behavior at all: the outcome of `check` is a
pure function of the *set* of registered rules and the actor.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.platform.identity.context import ActorContext, ActorType
from backend.platform.identity.directory import TenantDirectory


@dataclass(frozen=True, slots=True)
class Decision:
    """The outcome of a policy check."""

    allowed: bool
    reason: str

    @classmethod
    def allow(cls, reason: str = "explicit allow rule matched") -> Decision:
        return cls(allowed=True, reason=reason)

    @classmethod
    def deny(cls, reason: str) -> Decision:
        return cls(allowed=False, reason=reason)


@dataclass(frozen=True, slots=True)
class PolicyRule:
    """A registered ALLOW rule for a given (action, resource_type) pair.

    `allowed_actor_types`: if empty, all actor types are allowed by this
    rule (subject to the `human_only` override below). If non-empty, only
    actor types in this set are allowed.

    `human_only`: when True, this action can never be granted to an AI
    actor even if `allowed_actor_types` would otherwise include AI — this
    is the hard override backing R9 ("AI 推断只能生成 Perspective /
    Recommendation", never write canonical fact directly). It is enforced
    unconditionally by the engine, not merely by convention of what gets
    registered: the flag is a *veto over the whole (action, resource_type)
    key*, not a property of this one rule. If any rule for that key sets it,
    AI actors are denied for that key regardless of what other rules for the
    same key permit and regardless of registration order (see
    `PolicyEngine.check`).
    """

    action: str
    resource_type: str
    allowed_actor_types: frozenset[ActorType] = field(default_factory=frozenset)
    human_only: bool = False

    def matches(self, action: str, resource_type: str) -> bool:
        return self.action == action and self.resource_type == resource_type

    def permits(self, actor: ActorContext) -> bool:
        if self.human_only and actor.is_ai:
            return False
        if not self.allowed_actor_types:
            return True
        return actor.actor_type in self.allowed_actor_types


class PolicyEngine:
    """Fail-closed authorization decision point.

    Unregistered (action, resource_type) pairs always DENY. Registered
    rules only ever grant ALLOW — there is no mechanism to register an
    explicit DENY rule, because DENY is already the default; adding one
    would just be a way to accidentally shadow it.

    Two exceptions to "rules only grant", both vetoes rather than rules:
    `human_only` (R9) and tenant status (see `check`).

    `tenant_directory` is required. It is how the engine answers "is the
    actor's tenant active" without any route having to fabricate a
    `TenantContext`; see `backend/platform/identity/directory.py` for why it
    has no default.
    """

    def __init__(self, tenant_directory: TenantDirectory) -> None:
        self._rules: list[PolicyRule] = []
        self._tenant_directory = tenant_directory

    def register(self, rule: PolicyRule) -> None:
        self._rules.append(rule)

    def check(self, actor: ActorContext, action: str, resource_type: str) -> Decision:
        """Decide (actor, action, resource_type) with deny-overrides semantics.

        Pass 0 is the tenant veto and runs *before* any rule is looked at:
        `actor.tenant_id` is resolved through the `TenantDirectory`, and the
        decision is DENY when the tenant is unknown or when
        `TenantContext.is_active` is False. It is deliberately first so that a
        suspended tenant is reported as a suspended tenant rather than being
        masked by "no rule registered" — and so that no amount of rule
        registration can grant a suspended tenant anything.

        The remaining three passes run over *all* matching rules, never
        short-circuiting on the first permissive one:

        1. No matching rule at all → DENY (fail-closed default).
        2. Any matching rule with `human_only=True` and `actor.is_ai` → DENY.
           This pass runs to completion over the whole matching set before any
           ALLOW is possible, which is what makes the veto independent of
           registration order.
        3. Any matching rule that `permits(actor)` → ALLOW; otherwise DENY.

        Because pass 2 is a set-level quantifier rather than a per-rule check
        inside the granting loop, `register(permissive); register(human_only)`
        and `register(human_only); register(permissive)` produce identical
        decisions.
        """
        tenant = self._tenant_directory.resolve(actor.tenant_id)
        if tenant is None:
            return Decision.deny(
                f"tenant_id={actor.tenant_id!r} is not known to the tenant directory — "
                "fail-closed default DENY (unknown must never be more permissive "
                "than forbidden)"
            )
        if not tenant.is_active:
            return Decision.deny(
                f"tenant_id={actor.tenant_id!r} has status "
                f"{tenant.status.value!r}; only an ACTIVE tenant may act"
            )

        matching_rules = [r for r in self._rules if r.matches(action, resource_type)]

        if not matching_rules:
            return Decision.deny(
                f"no policy rule registered for action={action!r} "
                f"resource_type={resource_type!r} — fail-closed default DENY"
            )

        if actor.is_ai and any(rule.human_only for rule in matching_rules):
            return Decision.deny(
                f"action={action!r} on resource_type={resource_type!r} is "
                "human_only; AI actors are denied unconditionally"
            )

        if any(rule.permits(actor) for rule in matching_rules):
            return Decision.allow(
                f"actor_type={actor.actor_type.value!r} permitted by registered "
                f"rule for action={action!r} resource_type={resource_type!r}"
            )

        return Decision.deny(
            f"actor_type={actor.actor_type.value!r} does not match any registered "
            f"rule's allowed actor types for action={action!r} resource_type={resource_type!r}"
        )
