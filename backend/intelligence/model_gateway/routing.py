"""Routing across several separately-approved providers. Opt-in, tightly bounded.

Retry is 0 (see `gateway.py`), and this module does not reintroduce it. What it
adds is one narrow case: when two or more providers have *each independently*
cleared §16 admission for the data class at hand, an infrastructure failure on the
first need not fail the request.

Two rules keep that from becoming silent fallback:

1. **Only `INFRA_FAILURE_KINDS`** (`TIMEOUT` / `NETWORK_ERROR` / `PROVIDER_5XX`)
   moves to the next provider. `POLICY_REJECTED`, `INVALID_JSON`,
   `SCHEMA_INVALID`, `PROVIDER_4XX` and `CREDENTIAL_MISSING` fail closed
   immediately. In particular, asking vendor B the same question because vendor A
   returned unparseable output would be sampling until something looks like an
   answer — R9's exact prohibition.
2. **Every candidate is admitted independently.** Admission happens inside
   `ModelGateway.generate_structured` for each provider, so routing cannot smuggle
   a payload to a provider that was not approved for it. This is the point where
   不得转委托 could otherwise be defeated: "fall back to the other vendor" is,
   legally, a second delegated-processing relationship, not a retry.

Each attempt is recorded separately with an increasing `route_sequence`, so the
ledger shows the whole chain rather than only whichever provider answered.
"""

from __future__ import annotations

from backend.intelligence.model_gateway.contracts import ModelDraft, StructuredRequest
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.gateway import ModelGateway


class RoutingModelGateway:
    """Tries an ordered list of provider ids, advancing only on infra failures."""

    def __init__(self, gateway: ModelGateway, provider_order: list[str] | tuple[str, ...]) -> None:
        if not provider_order:
            raise ValueError("RoutingModelGateway requires at least one provider id")
        self._gateway = gateway
        self._order = tuple(provider_order)

    @property
    def provider_order(self) -> tuple[str, ...]:
        return self._order

    async def generate_structured(self, request: StructuredRequest) -> ModelDraft:
        last_error: ModelGatewayError | None = None
        for sequence, provider_id in enumerate(self._order):
            try:
                return await self._gateway.generate_structured(
                    request, provider_id=provider_id, route_sequence=sequence
                )
            except ModelGatewayError as error:
                last_error = error
                is_last = sequence == len(self._order) - 1
                if not error.is_infrastructure_failure or is_last:
                    raise
        # Unreachable: the loop either returns, raises, or exhausts with the final
        # iteration re-raising. Kept as a typed guard rather than an assert so a
        # future edit to the loop cannot silently return None.
        raise last_error if last_error is not None else ModelGatewayError(
            "POLICY_REJECTED", "no provider was attempted"
        )
