"""ActorContext / TenantContext — immutable identity primitives.

These are pure value objects: no database access, no HTTP, no model
provider calls. They exist so every other platform module (authorization,
audit, consent, idempotency) has a single, shared notion of "who is acting"
and "on behalf of which tenant" instead of each domain inventing its own
(the failure mode this capability's manifest entry documents: the only
prior equivalent, ``membership/application/context.py``'s ``ActionContext``,
was private to one domain).

R9 relevance: ``ActorContext.is_ai`` is the seam every higher layer (starting
with backend/platform/authorization) must use to answer "is this actor
allowed to write canonical state" — an AI actor must never be able to write
Family-authoritative facts directly (see REPOSITORY_CONSTITUTION.md R9,
"AI 推断只能生成 Perspective / Recommendation"). This module does not
implement that policy decision itself; it only guarantees the actor can be
asked, honestly, whether it is AI.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ActorType(StrEnum):
    """Who (or what) is performing an action."""

    HUMAN = "human"
    AI = "ai"
    SYSTEM = "system"


class TenantStatus(StrEnum):
    """Lifecycle status of a tenant."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class ActorContext:
    """Immutable description of the actor performing an action.

    Frozen + slots: an ActorContext must not be mutated after construction.
    Any code that needs a "different" actor (e.g. escalating to a system
    actor for a background job) must construct a new instance, never flip
    a field on an existing one — this keeps audit trails (R6) honest about
    who actually initiated an action.
    """

    actor_id: str
    actor_type: ActorType
    tenant_id: str
    correlation_id: str

    def __post_init__(self) -> None:
        if not self.actor_id:
            raise ValueError("ActorContext.actor_id must not be empty")
        if not self.tenant_id:
            raise ValueError("ActorContext.tenant_id must not be empty")
        if not self.correlation_id:
            raise ValueError("ActorContext.correlation_id must not be empty")

    @property
    def is_ai(self) -> bool:
        """True if this actor is an AI system, never a human or platform job.

        This is the seam R9-derived policy is built on: any layer deciding
        whether to allow a write to canonical/authoritative state must be
        able to ask this question honestly. This property makes no policy
        decision itself — it only reports fact.
        """
        return self.actor_type is ActorType.AI

    @property
    def is_human(self) -> bool:
        return self.actor_type is ActorType.HUMAN

    @property
    def is_system(self) -> bool:
        return self.actor_type is ActorType.SYSTEM


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Immutable description of the tenant an operation is scoped to."""

    tenant_id: str
    status: TenantStatus

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("TenantContext.tenant_id must not be empty")

    @property
    def is_active(self) -> bool:
        return self.status is TenantStatus.ACTIVE
