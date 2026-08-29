"""ActorContext — the only source of `created_by`/`tenant_scope`/actor
identity for this domain (PR-001R, chief-architect review on PR #27, item
3: "客户端不能决定自己是谁,也不能决定自己属于哪个 tenant"). Request DTOs no
longer carry `created_by`/`tenant_scope`/`human_actor` fields; every
application-service command takes a `ActorContext` supplied by the API
layer's authentication dependency (`api/dependencies.py`), never by the
request body.

This PR does not implement real authentication — no JWT/session verification
exists yet. `api/dependencies.py::get_actor_context` fails closed
(`RuntimeError`) until a real auth mechanism is wired in by whichever PR
adds `apps/family_api`. Tests construct `ActorContext` directly, which is
legitimate for unit/integration tests but must never become how a real
request obtains one.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.value_objects import ActorType


@dataclass(frozen=True)
class ActorContext:
    actor_id: str
    actor_type: ActorType
    tenant_scope: str
    roles: tuple[str, ...] = field(default_factory=tuple)
    # `roles` (above) classifies who the actor is (identity classification);
    # `permissions` is a separate concept — the specific actions this actor
    # has been explicitly granted, e.g. "product_intelligence.hypothesis.
    # review". Application-layer policy checks (see `application/commands.py`)
    # consult `permissions`, not `roles`. Kept as a `frozenset` (not
    # list/set) so `ActorContext` stays hashable/immutable.
    permissions: frozenset[str] = field(default_factory=frozenset)
    trace_id: str | None = None
