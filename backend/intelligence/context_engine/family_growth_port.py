"""Context Engine adapter for the vertical family-growth runtime.

The vertical runtime consumes a small ``FamilyGrowthContext`` projection,
while the durable Context Engine exposes a scoped ``ContextSnapshot``.  This
adapter is the provider-neutral seam between them: it reconstructs the scope
server-side, asks the broker to enforce tenant/family/consent checks, and only
then projects observations into the AI input envelope.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable

from backend.intelligence.agi_vertical_runtime import FamilyGrowthContext

from .async_port import AsyncContextBrokerPort
from .contracts import ContextContractError, ContextScope, ContextSnapshot


class SqlFamilyGrowthContextPort:
    """Read vertical context from a durable Context Broker.

    ``scope_factory`` must derive a complete scope from the authenticated
    family identity; request payloads never supply tenant, subjects, consent,
    or purpose.  Broker errors intentionally propagate so the HTTP boundary
    can fail closed rather than fabricating context.
    """

    def __init__(
        self,
        broker: AsyncContextBrokerPort,
        scope_factory: Callable[[str], ContextScope],
    ) -> None:
        if getattr(broker, "durability_mode", None) != "DURABLE":
            raise ValueError("family-growth ContextPort requires durable broker")
        self._broker = broker
        self._scope_factory = scope_factory

    @property
    def durability_mode(self) -> str:
        """Expose the underlying broker's durability for composition guards."""

        return str(self._broker.durability_mode)

    @property
    def broker(self) -> AsyncContextBrokerPort:
        """Expose the exact durable broker selected by the composition root."""

        return self._broker

    async def read(self, *, family_id: str, context_snapshot_ref: str) -> FamilyGrowthContext:
        scope = self._scope_factory(family_id)
        if inspect.isawaitable(scope):
            scope = await scope
        if not isinstance(scope, ContextScope) or scope.family_id != family_id:
            raise ValueError("family-growth context scope mismatch")
        snapshot = await self._broker.read(context_snapshot_ref, scope)
        # The durable broker is the first enforcement point, but this adapter
        # is also a security boundary: a substituted/misbehaving implementation
        # must not be able to smuggle an unscoped projection into the model
        # request.  Require the canonical immutable snapshot contract and the
        # exact server-derived scope before projecting any observation.
        if not isinstance(snapshot, ContextSnapshot):
            raise ContextContractError("CONTEXT_SNAPSHOT_INVALID")
        if snapshot.scope != scope:
            raise ContextContractError("CONTEXT_SCOPE_MISMATCH")
        if snapshot.snapshot_ref != context_snapshot_ref:
            raise ContextContractError("CONTEXT_SNAPSHOT_REF_MISMATCH")
        values: dict[str, object] = {
            observation.dimension: observation.observed_value
            for observation in snapshot.observations
        }
        values.update(
            {
                "data_class": snapshot.data_class.value,
                "purpose": snapshot.purpose,
                "source_refs": snapshot.source_refs,
                "provenance": snapshot.provenance,
            }
        )
        return FamilyGrowthContext(
            tenant_id=snapshot.tenant_id,
            family_id=snapshot.family_id,
            subject_ids=snapshot.subject_ids,
            purpose=snapshot.purpose,
            consent_version=snapshot.consent_version,
            context_snapshot_ref=snapshot.snapshot_ref,
            values=values,
        )


__all__ = ["SqlFamilyGrowthContextPort"]
