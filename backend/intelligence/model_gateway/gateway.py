"""ModelGateway — admission, timeout, attempt ledger, validation, provenance.

## The call sequence, and why it is this order

    admit  →  begin attempt  →  invoke under deadline  →  finish attempt
           →  decode  →  validate  →  build provenance  →  ModelDraft

`admit` is first because a rejected request must never touch a provider; if
admission ran concurrently with the call, family data would already have left the
process by the time the verdict arrived. `begin attempt` is second because a call
that never returns must still leave a trace (see `attempts.py`). Provenance is
last because it records what actually answered — the model the provider *reported*,
and the measured latency — not what was requested.

## Retry policy: 0, inherited deliberately

The source repository set `automatic_retry: 0` with fail-closed. Reading its
comments, the reasoning is that a retry is only safe when the failure is known to
be transient and the operation is known to be idempotent, and neither holds here:
a timeout may mean the provider is mid-generation (so a retry duplicates a paid,
logged, third-party processing event), and cross-provider fallback would send the
same family payload to a *second* vendor — which under
《儿童个人信息网络保护规定》第16条 is a second delegated-processing relationship,
each needing its own security assessment and agreement. A retry loop would make
the number of processors a function of network weather.

This repository keeps retry at 0, and adds a reason of its own that the source
repository did not have to make: R9. Retrying until a model finally produces
parseable JSON optimises for *producing an answer*, and an answer produced that
way is indistinguishable to the caller from a well-grounded one. Failing closed
makes the absence of an answer visible, which is the honest outcome.

`RoutingModelGateway` (see `routing.py`) exists for the narrow legitimate case —
several *separately approved* providers, moving on only for genuine infrastructure
failures — and it is opt-in, never a default.

## What this module does not do

It does not import a business domain, hold a database session, or produce a
business entity. Its output is a `ModelDraft`, whose `may_mutate_business_state`
cannot be `True`.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from types import MappingProxyType
from typing import Any

from backend.intelligence.model_gateway.attempts import (
    AttemptOutcome,
    AttemptSink,
    InMemoryAttemptSink,
)
from backend.intelligence.model_gateway.contracts import (
    AiProvenance,
    ModelDraft,
    StructuredRequest,
)
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.provider_registry import (
    ProviderRecord,
    ProviderRegistry,
    default_provider_registry,
)
from backend.intelligence.model_gateway.providers.base import ProviderAdapter
from backend.intelligence.model_gateway.validation import SchemaValidator

GATEWAY_POLICY = MappingProxyType(
    {
        "provider_sdk_access": "gateway_only",
        "domain_direct_provider_call": "forbidden",
        "canonical_mutation_by_ai": "forbidden",
        "structured_output_required": True,
        "schema_validation_required": True,
        "human_confirmation_required": True,
        "on_failure": "fail_closed",
        "automatic_retry": 0,
        "cross_provider_fallback": "opt_in_infrastructure_failures_only",
        "schema_failure_returns_raw_text": False,
        "timeout_enforced": True,
        "unregistered_provider": "rejected",
        "sub_delegating_provider_for_regulated_data": "rejected",
    }
)
"""The policy, stated for readers — and *only* for readers.

Every line above is enforced by code in this package plus the architecture tests,
and this mapping is documentation of that fact, not the mechanism. R14 exists
because the source repository shipped exactly such a constant
(`AI_GATEWAY_POLICY.business_module_direct_provider_call = 'forbidden'`) and then
violated it from a business service, since nothing executed the constant. It is
`MappingProxyType` so it cannot be mutated at runtime, but that is hygiene: if this
mapping disagrees with the code, the code is what happens.
"""

_CODE_FENCE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL | re.IGNORECASE)


def _strip_code_fence(text: str) -> str:
    """Remove a single outer markdown fence, changing nothing inside it.

    Not leniency for its own sake: models on the OpenAI-compatible contract wrap
    JSON in ```json fences often enough that treating it as a hard failure would
    reject well-formed answers over a formatting habit. The content is untouched,
    and anything still unparseable afterwards fails closed as normal.
    """
    stripped = text.strip()
    match = _CODE_FENCE.match(stripped)
    return match.group(1).strip() if match else stripped


class ModelGateway:
    """The single entry point for model access in AiFamily.

    Args:
        providers: adapters by `provider_id`. Every id must be registered; the
            constructor refuses otherwise, so an unregistered provider cannot even
            be wired in — the check does not wait for a request to arrive.
        registry: provider governance records. Defaults to the shipped registry.
        environment: which environment this runtime is; matched against each
            record's `approved_environments`. Required, with no default: a default
            of `"production"` would be dangerous and a default of `"test"` would be
            a bypass, so the caller states it.
        attempt_sink: ledger. Defaults to an in-memory one, making recording
            opt-out rather than opt-in.
        default_timeout_seconds: outer deadline when a record does not set one.
    """

    def __init__(
        self,
        providers: dict[str, ProviderAdapter],
        *,
        environment: str,
        registry: ProviderRegistry | None = None,
        attempt_sink: AttemptSink | None = None,
        validator: SchemaValidator | None = None,
        default_timeout_seconds: float = 30.0,
    ) -> None:
        if not environment:
            raise ValueError("ModelGateway requires an explicit environment name")
        self._registry = registry if registry is not None else default_provider_registry()
        self._environment = environment
        self._attempts: AttemptSink = (
            attempt_sink if attempt_sink is not None else InMemoryAttemptSink()
        )
        self._validator = validator if validator is not None else SchemaValidator()
        self._default_timeout_seconds = default_timeout_seconds

        unknown = sorted(pid for pid in providers if pid not in self._registry)
        if unknown:
            raise ModelGatewayError(
                "POLICY_REJECTED",
                f"cannot wire unregistered provider(s) {unknown}; register them in the "
                "provider registry with their 第16条 compliance posture first. Wiring is "
                "refused at construction so that a governance gap surfaces at startup "
                "rather than on the first family request.",
            )
        self._providers = dict(providers)

    @property
    def environment(self) -> str:
        return self._environment

    @property
    def attempt_sink(self) -> AttemptSink:
        return self._attempts

    @property
    def registry(self) -> ProviderRegistry:
        return self._registry

    def available_provider_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))

    async def generate_structured(
        self,
        request: StructuredRequest,
        *,
        provider_id: str,
        route_sequence: int = 0,
    ) -> ModelDraft:
        """Run one attempt against one provider, or raise `ModelGatewayError`.

        There is no success-with-warnings outcome and no degraded return value.
        Either a schema-valid draft with complete provenance comes back, or the
        caller gets an exception naming the failure kind.
        """
        record = self._registry.admit(
            provider_id,
            data_class=request.data_class,
            environment=self._environment,
        )
        adapter = self._providers.get(provider_id)
        if adapter is None:
            raise ModelGatewayError(
                "POLICY_REJECTED",
                f"provider {provider_id!r} is registered and admitted but no adapter is "
                f"wired in this runtime (wired: {list(self.available_provider_ids())})",
                provider_id=provider_id,
            )

        attempt_id = self._begin_attempt(record, request, route_sequence)
        started = time.perf_counter()
        timeout_seconds = record.timeout_seconds or self._default_timeout_seconds

        try:
            response = await asyncio.wait_for(
                adapter.invoke(request, timeout_seconds=timeout_seconds),
                timeout=timeout_seconds,
            )
        except TimeoutError as exc:
            # Outer deadline. Enforced here as well as inside the adapter so that
            # an adapter which ignores or mishandles its timeout parameter cannot
            # hold a request open indefinitely — the guarantee belongs to the
            # gateway, not to each adapter's diligence.
            latency_ms = self._elapsed_ms(started)
            self._finish_attempt(attempt_id, "FAILURE", latency_ms, failure_kind="TIMEOUT")
            raise ModelGatewayError(
                "TIMEOUT",
                f"provider {provider_id!r} exceeded the {timeout_seconds}s deadline",
                provider_id=provider_id,
            ) from exc
        except ModelGatewayError as exc:
            self._finish_attempt(
                attempt_id, "FAILURE", self._elapsed_ms(started), failure_kind=exc.kind
            )
            raise
        except Exception as exc:
            # An adapter is contractually required to raise ModelGatewayError. If
            # one leaks something else, it is mapped here rather than propagated:
            # a raw vendor exception can carry the request payload in its string
            # form, and this gateway's callers handle family data.
            latency_ms = self._elapsed_ms(started)
            self._finish_attempt(attempt_id, "FAILURE", latency_ms, failure_kind="NETWORK_ERROR")
            raise ModelGatewayError(
                "NETWORK_ERROR",
                f"adapter for {provider_id!r} raised an unmapped "
                f"{type(exc).__name__}; adapters must raise ModelGatewayError",
                provider_id=provider_id,
            ) from exc

        latency_ms = self._elapsed_ms(started)

        try:
            output = self._decode_and_validate(response.text, request, provider_id=provider_id)
        except ModelGatewayError as exc:
            self._finish_attempt(
                attempt_id,
                "FAILURE",
                latency_ms,
                failure_kind=exc.kind,
                model=response.model,
                model_version=response.model_version,
            )
            raise

        self._finish_attempt(
            attempt_id,
            "SUCCESS",
            latency_ms,
            model=response.model,
            model_version=response.model_version,
        )

        provenance = AiProvenance(
            provider_id=provider_id,
            model=response.model,
            model_version=response.model_version,
            prompt_version=request.prompt_version,
            schema_version=request.schema_version,
            context_snapshot_ref=request.context_snapshot_ref,
            latency_ms=latency_ms,
            data_class=request.data_class,
            use_case=request.use_case,
            confidence=response.confidence,
            token_usage=response.token_usage,
        )
        return ModelDraft(output=output, provenance=provenance)

    # -- internals ---------------------------------------------------------

    def _decode_and_validate(
        self, text: str, request: StructuredRequest, *, provider_id: str
    ) -> dict[str, Any]:
        try:
            decoded = json.loads(_strip_code_fence(text))
        except (json.JSONDecodeError, TypeError) as exc:
            # FAIL CLOSED. The raw text is dropped on purpose: returning it, or
            # attaching it to the error, is how prose reaches a family UI looking
            # like a structured recommendation.
            raise ModelGatewayError(
                "INVALID_JSON",
                f"provider {provider_id!r} returned content that is not valid JSON "
                "(raw text discarded, not returned to the caller)",
                provider_id=provider_id,
            ) from exc
        return self._validator.validate(decoded, request.output_schema, provider_id=provider_id)

    def _begin_attempt(
        self, record: ProviderRecord, request: StructuredRequest, route_sequence: int
    ) -> str | None:
        try:
            return self._attempts.begin(
                provider_id=record.provider_id,
                use_case=request.use_case,
                data_class=request.data_class,
                environment=self._environment,
                route_sequence=route_sequence,
                request_id=request.request_id,
                session_id=request.session_id,
            )
        except Exception:
            # Best-effort: a broken ledger must not become the reason a family
            # request fails, and it must not mask the provider's own outcome.
            return None

    def _finish_attempt(
        self,
        attempt_id: str | None,
        status: str,
        latency_ms: int,
        *,
        failure_kind: str | None = None,
        model: str | None = None,
        model_version: str | None = None,
    ) -> None:
        try:
            self._attempts.finish(
                attempt_id,
                AttemptOutcome(
                    status=status,  # type: ignore[arg-type]
                    latency_ms=latency_ms,
                    failure_kind=failure_kind,
                    model=model,
                    model_version=model_version,
                ),
            )
        except Exception:
            return

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, int((time.perf_counter() - started) * 1000))


def build_gateway(
    *,
    environment: str,
    providers: dict[str, ProviderAdapter] | None = None,
    registry: ProviderRegistry | None = None,
    attempt_sink: AttemptSink | None = None,
) -> ModelGateway:
    """The one supported construction path (R10).

    R10's scar is that the source repository had a single gateway implementation
    reached through three inconsistent wiring patterns — "重复的不是实现，是纪律".
    So there is one factory, and it never guesses: it does not read the
    environment to auto-select a vendor, and it does not substitute a fake when
    real configuration is missing. Callers pass the adapters they mean to use.

    With no `providers` argument the gateway has none, so every call raises
    `POLICY_REJECTED`. That is the correct default for this repository today: no
    external vendor has cleared the §16 assessment, so none is callable.
    """
    return ModelGateway(
        providers or {},
        environment=environment,
        registry=registry,
        attempt_sink=attempt_sink,
    )
