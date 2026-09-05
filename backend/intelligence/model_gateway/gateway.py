"""ModelGateway — admission, timeout, attempt ledger, validation, provenance.

## The call sequence, and why it is this order

    safety input → admit  →  begin attempt  →  invoke under deadline
      → decode → validate → safety output → build provenance → ModelDraft

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
import inspect
import json
import re
import time
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from backend.intelligence.model_gateway.attempts import (
    AttemptOutcome,
    AttemptSink,
    InMemoryAttemptSink,
)
from backend.intelligence.model_gateway.budget import (
    ModelBudgetError,
    ModelBudgetReservation,
    ModelBudgetRuntime,
)
from backend.intelligence.model_gateway.contracts import (
    AiProvenance,
    ModelDraft,
    StructuredRequest,
    TokenUsage,
)
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.provider_registry import (
    ProviderRecord,
    ProviderRegistry,
    default_provider_registry,
)
from backend.intelligence.model_gateway.providers.base import ProviderAdapter
from backend.intelligence.model_gateway.release_fence import (
    ModelInvocationFence,
    ModelInvocationFenceClaim,
    ModelInvocationFenceError,
)
from backend.intelligence.model_gateway.validation import SchemaValidator
from backend.intelligence.observability import (
    TelemetryContext,
    TelemetrySink,
    TelemetrySpanHandle,
)
from backend.intelligence.safety.persistence import SafetyDecisionSink
from backend.intelligence.safety.runtime import SafetyContext, SafetyDecision, SafetyRuntime

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
        "safety_input_output_checks_in_factory": True,
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
        safety_runtime: provider-neutral input/output policy checks. The low-level
            constructor accepts ``None`` for isolated unit tests; ``build_gateway``
            injects the default runtime and production composition roots reject a
            gateway without one.
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
        safety_runtime: SafetyRuntime | None = None,
        safety_sink: SafetyDecisionSink | None = None,
        telemetry_sink: TelemetrySink | None = None,
        budget_runtime: ModelBudgetRuntime | None = None,
        invocation_fence: ModelInvocationFence | None = None,
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
        # Safety is injected by the composition root.  Keeping the low-level
        # constructor optional preserves focused unit-test adapters, while the
        # supported ``build_gateway`` factory always wires the runtime.
        self._safety = safety_runtime
        if safety_sink is not None and safety_runtime is None:
            raise ValueError("safety_sink requires SafetyRuntime")
        self._safety_sink = safety_sink
        self._telemetry = telemetry_sink
        self._budget = budget_runtime
        self._invocation_fence = invocation_fence
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

    @property
    def safety_runtime(self) -> SafetyRuntime | None:
        """The policy runtime bound to this gateway, if explicitly supplied."""

        return self._safety

    @property
    def safety_sink(self) -> SafetyDecisionSink | None:
        """The optional decision ledger bound to this gateway."""

        return self._safety_sink

    @property
    def telemetry_sink(self) -> TelemetrySink | None:
        """Optional metadata-only span sink bound to this gateway."""

        return self._telemetry

    @property
    def budget_runtime(self) -> ModelBudgetRuntime | None:
        """The fail-closed pre-call budget gate, when configured."""

        return self._budget

    @property
    def invocation_fence(self) -> ModelInvocationFence | None:
        """The pre-I/O active-release linearization boundary, when configured."""

        return self._invocation_fence

    def available_provider_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))

    def provider_supported_modalities(self, provider_id: str) -> frozenset[str]:
        """Return the adapter's declared media capabilities for composition checks."""

        provider = self._providers.get(provider_id)
        if provider is None:
            raise ModelGatewayError(
                "POLICY_REJECTED",
                f"provider {provider_id!r} is not wired in this gateway",
                provider_id=provider_id,
            )
        capabilities = getattr(provider, "supported_modalities", None)
        if not isinstance(capabilities, frozenset) or any(
            not isinstance(item, str) or not item.strip() for item in capabilities
        ):
            raise ModelGatewayError(
                "POLICY_REJECTED",
                f"provider {provider_id!r} has no valid modality capability declaration",
                provider_id=provider_id,
            )
        return capabilities

    def with_attempt_sink(self, attempt_sink: AttemptSink) -> ModelGateway:
        """Return an equivalent gateway bound to a request-scoped sink.

        Production composition roots use this to bind an ``AsyncSession``-backed
        sink for one transaction without sharing sessions across requests.  The
        provider registry, validator and Safety Runtime are intentionally copied
        unchanged, so the request-scoped adapter cannot weaken policy.
        """

        if attempt_sink is None:
            raise ValueError("attempt_sink is required")
        return ModelGateway(
            dict(self._providers),
            environment=self._environment,
            registry=self._registry,
            attempt_sink=attempt_sink,
            validator=self._validator,
            safety_runtime=self._safety,
            safety_sink=self._safety_sink,
            telemetry_sink=self._telemetry,
            budget_runtime=self._budget,
            invocation_fence=self._invocation_fence,
            default_timeout_seconds=self._default_timeout_seconds,
        )

    def with_safety_sink(self, safety_sink: SafetyDecisionSink) -> ModelGateway:
        """Return an equivalent gateway bound to a request-scoped safety ledger."""

        if safety_sink is None:
            raise ValueError("safety_sink is required")
        if self._safety is None:
            raise ValueError("safety_sink requires SafetyRuntime")
        return ModelGateway(
            dict(self._providers),
            environment=self._environment,
            registry=self._registry,
            attempt_sink=self._attempts,
            validator=self._validator,
            safety_runtime=self._safety,
            safety_sink=safety_sink,
            telemetry_sink=self._telemetry,
            budget_runtime=self._budget,
            invocation_fence=self._invocation_fence,
            default_timeout_seconds=self._default_timeout_seconds,
        )

    def with_telemetry_sink(self, telemetry_sink: TelemetrySink) -> ModelGateway:
        """Return an equivalent gateway bound to a request-scoped telemetry sink."""

        if telemetry_sink is None:
            raise ValueError("telemetry_sink is required")
        return ModelGateway(
            dict(self._providers),
            environment=self._environment,
            registry=self._registry,
            attempt_sink=self._attempts,
            validator=self._validator,
            safety_runtime=self._safety,
            safety_sink=self._safety_sink,
            telemetry_sink=telemetry_sink,
            budget_runtime=self._budget,
            invocation_fence=self._invocation_fence,
            default_timeout_seconds=self._default_timeout_seconds,
        )

    def with_invocation_fence(
        self, invocation_fence: ModelInvocationFence
    ) -> ModelGateway:
        """Return an equivalent gateway with a request-safe release fence."""

        if invocation_fence is None:
            raise ValueError("invocation_fence is required")
        return ModelGateway(
            dict(self._providers),
            environment=self._environment,
            registry=self._registry,
            attempt_sink=self._attempts,
            validator=self._validator,
            safety_runtime=self._safety,
            safety_sink=self._safety_sink,
            telemetry_sink=self._telemetry,
            budget_runtime=self._budget,
            invocation_fence=invocation_fence,
            default_timeout_seconds=self._default_timeout_seconds,
        )

    async def generate_structured(
        self,
        request: StructuredRequest,
        *,
        provider_id: str,
        route_sequence: int = 0,
    ) -> ModelDraft:
        """Trace one governed model call without recording raw AI content."""

        handle = await self._start_telemetry(request, provider_id, route_sequence)
        try:
            draft = await self._generate_structured(
                request,
                provider_id=provider_id,
                route_sequence=route_sequence,
            )
        except ModelGatewayError as exc:
            await self._finish_telemetry(handle, status="ERROR", error_code=exc.kind)
            raise
        except Exception as exc:
            await self._finish_telemetry(
                handle, status="ERROR", error_code=type(exc).__name__[:128]
            )
            raise
        await self._finish_telemetry(
            handle,
            status="OK",
            attributes={"draft_status": draft.status},
        )
        return draft

    async def _generate_structured(
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
        safety_context = SafetyContext(
            use_case=request.use_case,
            subject_is_minor=request.data_class == "MINOR_PERSONAL_DATA",
            data_class=request.data_class,
            tenant_id=request.tenant_id,
            family_id=request.family_id,
        )
        if self._safety is not None:
            try:
                decision = self._safety.evaluate_input(safety_context, request.payload)
            except Exception as exc:
                # A policy implementation failure is itself a deny.  Never let
                # a custom safety provider exception reach a caller or provider.
                raise ModelGatewayError(
                    "POLICY_REJECTED",
                    "safety policy evaluation failed closed for the model request",
                    provider_id=provider_id,
                ) from exc
            await self._record_safety_decision(
                stage="input",
                context=safety_context,
                decision=decision,
                request=request,
                provider_id=provider_id,
            )
            if decision.status == "BLOCK":
                raise ModelGatewayError(
                    "POLICY_REJECTED",
                    "safety policy blocked the model request",
                    provider_id=provider_id,
                )

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

        budget_reservation = await self._reserve_budget(
            request,
            provider_id=provider_id,
            model=record.model,
            route_sequence=route_sequence,
        )

        try:
            attempt_id = await self._begin_attempt(record, request, route_sequence)
        except ModelGatewayError:
            await self._release_budget(
                budget_reservation,
                outcome_code="ATTEMPT_LEDGER_REJECTED",
                provider_id=provider_id,
            )
            raise
        try:
            fence_claim = await self._claim_invocation_fence(
                request,
                provider_id=provider_id,
                route_sequence=route_sequence,
            )
        except ModelGatewayError:
            await self._release_budget(
                budget_reservation,
                outcome_code="RELEASE_FENCE_REJECTED",
                provider_id=provider_id,
            )
            await self._finish_attempt(
                attempt_id,
                "FAILURE",
                0,
                failure_kind="RELEASE_FENCE_REJECTED",
            )
            raise
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
            await self._consume_uncertain_budget(
                budget_reservation, outcome_code="TIMEOUT", provider_id=provider_id
            )
            await self._finish_attempt(attempt_id, "FAILURE", latency_ms, failure_kind="TIMEOUT")
            raise ModelGatewayError(
                "TIMEOUT",
                f"provider {provider_id!r} exceeded the {timeout_seconds}s deadline",
                provider_id=provider_id,
            ) from exc
        except ModelGatewayError as exc:
            await self._consume_uncertain_budget(
                budget_reservation, outcome_code=exc.kind, provider_id=provider_id
            )
            await self._finish_attempt(
                attempt_id, "FAILURE", self._elapsed_ms(started), failure_kind=exc.kind
            )
            raise
        except Exception as exc:
            # An adapter is contractually required to raise ModelGatewayError. If
            # one leaks something else, it is mapped here rather than propagated:
            # a raw vendor exception can carry the request payload in its string
            # form, and this gateway's callers handle family data.
            latency_ms = self._elapsed_ms(started)
            await self._consume_uncertain_budget(
                budget_reservation,
                outcome_code="NETWORK_ERROR",
                provider_id=provider_id,
            )
            await self._finish_attempt(
                attempt_id, "FAILURE", latency_ms, failure_kind="NETWORK_ERROR"
            )
            raise ModelGatewayError(
                "NETWORK_ERROR",
                f"adapter for {provider_id!r} raised an unmapped "
                f"{type(exc).__name__}; adapters must raise ModelGatewayError",
                provider_id=provider_id,
            ) from exc

        latency_ms = self._elapsed_ms(started)
        try:
            await self._settle_budget(
                budget_reservation,
                token_usage=response.token_usage,
                media_item_count=len(request.media_inputs),
                provider_id=provider_id,
            )
        except ModelGatewayError:
            await self._finish_attempt(
                attempt_id,
                "FAILURE",
                latency_ms,
                failure_kind="BUDGET_REJECTED",
                model=response.model,
                model_version=response.model_version,
                token_usage=response.token_usage,
            )
            raise

        try:
            output = self._decode_and_validate(response.text, request, provider_id=provider_id)
        except ModelGatewayError as exc:
            await self._finish_attempt(
                attempt_id,
                "FAILURE",
                latency_ms,
                failure_kind=exc.kind,
                model=response.model,
                model_version=response.model_version,
                token_usage=response.token_usage,
            )
            raise

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
            release_set_id=(
                request.release_binding.release_set_id
                if request.release_binding is not None
                else None
            ),
            bundle_id=(
                request.release_binding.bundle_id_for(provider_id)
                if request.release_binding is not None
                else None
            ),
            deployment_receipt_id=(
                request.release_binding.deployment_receipt_id
                if request.release_binding is not None
                else None
            ),
            runtime_config_digest=(
                request.release_binding.runtime_config_digest
                if request.release_binding is not None
                else None
            ),
            deployment_sequence=(
                request.release_binding.deployment_sequence
                if request.release_binding is not None
                else None
            ),
            control_id=(
                request.release_binding.control_id
                if request.release_binding is not None
                else None
            ),
            fence_claim_id=(fence_claim.claim_id if fence_claim is not None else None),
        )
        draft = ModelDraft(output=output, provenance=provenance)
        if self._safety is not None:
            try:
                decision = self._safety.evaluate_output(safety_context, draft)
            except Exception as exc:
                await self._finish_attempt(
                    attempt_id,
                    "FAILURE",
                    latency_ms,
                    failure_kind="POLICY_REJECTED",
                    model=response.model,
                    model_version=response.model_version,
                    token_usage=response.token_usage,
                )
                raise ModelGatewayError(
                    "POLICY_REJECTED",
                    "safety policy evaluation failed closed for the model output",
                    provider_id=provider_id,
                ) from exc
            try:
                await self._record_safety_decision(
                    stage="output",
                    context=safety_context,
                    decision=decision,
                    request=request,
                    provider_id=provider_id,
                )
            except ModelGatewayError:
                await self._finish_attempt(
                    attempt_id,
                    "FAILURE",
                    latency_ms,
                    failure_kind="POLICY_REJECTED",
                    model=response.model,
                    model_version=response.model_version,
                    token_usage=response.token_usage,
                )
                raise
            if decision.status == "BLOCK":
                await self._finish_attempt(
                    attempt_id,
                    "FAILURE",
                    latency_ms,
                    failure_kind="POLICY_REJECTED",
                    model=response.model,
                    model_version=response.model_version,
                    token_usage=response.token_usage,
                )
                raise ModelGatewayError(
                    "POLICY_REJECTED",
                    "safety policy blocked the model output",
                    provider_id=provider_id,
                )

        await self._finish_attempt(
            attempt_id,
            "SUCCESS",
            latency_ms,
            model=response.model,
            model_version=response.model_version,
            token_usage=response.token_usage,
        )
        return draft

    async def _reserve_budget(
        self,
        request: StructuredRequest,
        *,
        provider_id: str,
        model: str,
        route_sequence: int,
    ) -> ModelBudgetReservation | None:
        if self._budget is None:
            return None
        try:
            return await self._budget.reserve(
                request,
                provider_id=provider_id,
                model=model,
                route_sequence=route_sequence,
            )
        except ModelBudgetError as exc:
            raise ModelGatewayError(
                "BUDGET_REJECTED",
                f"model budget rejected the request ({exc.code})",
                provider_id=provider_id,
            ) from exc

    async def _settle_budget(
        self,
        reservation: ModelBudgetReservation | None,
        *,
        token_usage: TokenUsage | None,
        media_item_count: int,
        provider_id: str,
    ) -> ModelInvocationFenceClaim | None:
        if reservation is None or self._budget is None:
            return None
        try:
            await self._budget.settle(
                reservation,
                usage=token_usage,
                media_item_count=media_item_count,
            )
        except ModelBudgetError as exc:
            raise ModelGatewayError(
                "BUDGET_REJECTED",
                f"model budget settlement failed closed ({exc.code})",
                provider_id=provider_id,
            ) from exc

    async def _consume_uncertain_budget(
        self,
        reservation: ModelBudgetReservation | None,
        *,
        outcome_code: str,
        provider_id: str,
    ) -> None:
        if reservation is None or self._budget is None:
            return
        try:
            await self._budget.consume_uncertain(
                reservation,
                outcome_code=outcome_code,
            )
        except ModelBudgetError as exc:
            raise ModelGatewayError(
                "BUDGET_REJECTED",
                f"model budget outcome recording failed closed ({exc.code})",
                provider_id=provider_id,
            ) from exc

    async def _release_budget(
        self,
        reservation: ModelBudgetReservation | None,
        *,
        outcome_code: str,
        provider_id: str,
    ) -> None:
        if reservation is None or self._budget is None:
            return
        try:
            await self._budget.release(reservation, outcome_code=outcome_code)
        except ModelBudgetError as exc:
            raise ModelGatewayError(
                "BUDGET_REJECTED",
                f"model budget release failed closed ({exc.code})",
                provider_id=provider_id,
            ) from exc

    async def _claim_invocation_fence(
        self,
        request: StructuredRequest,
        *,
        provider_id: str,
        route_sequence: int,
    ) -> None:
        if request.release_binding is None and self._invocation_fence is None:
            return
        if self._invocation_fence is None:
            raise ModelGatewayError(
                "RELEASE_FENCE_REJECTED",
                "release-bound model request requires an invocation fence",
                provider_id=provider_id,
            )
        try:
            return await self._invocation_fence.claim(
                request,
                provider_id=provider_id,
                route_sequence=route_sequence,
            )
        except ModelInvocationFenceError as exc:
            raise ModelGatewayError(
                "RELEASE_FENCE_REJECTED",
                f"active release fence rejected the request ({exc})",
                provider_id=provider_id,
            ) from exc
        except Exception as exc:
            raise ModelGatewayError(
                "RELEASE_FENCE_REJECTED",
                "active release fence failed closed before provider invocation",
                provider_id=provider_id,
            ) from exc

    async def _start_telemetry(
        self, request: StructuredRequest, provider_id: str, route_sequence: int
    ) -> TelemetrySpanHandle | None:
        if self._telemetry is None:
            return None
        try:
            context = TelemetryContext(
                trace_id=request.request_id or f"trace-{uuid4().hex}",
                request_id=request.request_id,
                session_id=request.session_id,
                tenant_id=request.tenant_id,
                family_id=request.family_id,
                use_case=request.use_case,
                data_class=request.data_class,
                operation_id=(
                    f"{request.request_id or request.use_case}:{provider_id}:{route_sequence}"
                ),
            )
            return await self._telemetry.start_span(
                name="ai.model_gateway.generate_structured",
                context=context,
                attributes={
                    "provider_id": provider_id,
                    "environment": self._environment,
                    "route_sequence": route_sequence,
                    "has_media": bool(request.media_inputs),
                    "media_count": len(request.media_inputs),
                },
            )
        except Exception:
            # Telemetry is diagnostic, not a policy gate.  A broken exporter
            # must not mask the model/safety outcome or cause a duplicate call.
            return None

    async def _finish_telemetry(
        self,
        handle: TelemetrySpanHandle | None,
        *,
        status: str,
        error_code: str | None = None,
        attributes: dict[str, str | int | float | bool] | None = None,
    ) -> None:
        if handle is None or self._telemetry is None:
            return
        try:
            await self._telemetry.finish_span(
                handle,
                status=status,  # type: ignore[arg-type]
                error_code=error_code,
                attributes=attributes or {},
            )
        except Exception:
            return

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

    async def _begin_attempt(
        self, record: ProviderRecord, request: StructuredRequest, route_sequence: int
    ) -> str | None:
        try:
            begin_kwargs: dict[str, object] = {
                "provider_id": record.provider_id,
                "use_case": request.use_case,
                "data_class": request.data_class,
                "environment": self._environment,
                "route_sequence": route_sequence,
                "request_id": request.request_id,
                "session_id": request.session_id,
            }
            if request.tenant_id is not None:
                begin_kwargs["tenant_id"] = request.tenant_id
                begin_kwargs["family_id"] = request.family_id
            if request.release_binding is not None:
                begin_kwargs["release_set_id"] = request.release_binding.release_set_id
                begin_kwargs["bundle_id"] = request.release_binding.bundle_id_for(
                    record.provider_id
                )
                begin_kwargs["deployment_receipt_id"] = (
                    request.release_binding.deployment_receipt_id
                )
                begin_kwargs["deployment_sequence"] = (
                    request.release_binding.deployment_sequence
                )
                begin_kwargs["runtime_config_digest"] = (
                    request.release_binding.runtime_config_digest
                )
                begin_kwargs["control_id"] = request.release_binding.control_id
            result = self._attempts.begin(
                **begin_kwargs,
            )
            if inspect.isawaitable(result):
                return await result
            return result
        except Exception as exc:
            if request.release_binding is not None:
                raise ModelGatewayError(
                    "ATTEMPT_LEDGER_REJECTED",
                    "release-bound attempt START persistence failed closed",
                    provider_id=record.provider_id,
                ) from exc
            # Legacy unbound low-level calls retain best-effort diagnostics.
            return None

    async def _finish_attempt(
        self,
        attempt_id: str | None,
        status: str,
        latency_ms: int,
        *,
        failure_kind: str | None = None,
        model: str | None = None,
        model_version: str | None = None,
        token_usage: TokenUsage | None = None,
    ) -> None:
        try:
            result = self._attempts.finish(
                attempt_id,
                AttemptOutcome(
                    status=status,  # type: ignore[arg-type]
                    latency_ms=latency_ms,
                    failure_kind=failure_kind,
                    model=model,
                    model_version=model_version,
                    token_usage=token_usage,
                ),
            )
            if inspect.isawaitable(result):
                await result
        except Exception:
            return

    async def _record_safety_decision(
        self,
        *,
        stage: str,
        context: SafetyContext,
        decision: SafetyDecision,
        request: StructuredRequest,
        provider_id: str,
    ) -> None:
        if self._safety_sink is None:
            return
        try:
            result = self._safety_sink.record(
                stage=stage,
                context=context,
                decision=decision,
                request_id=request.request_id,
                session_id=request.session_id,
            )
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            raise ModelGatewayError(
                "POLICY_REJECTED",
                "safety decision persistence failed; model execution blocked",
                provider_id=provider_id,
            ) from exc

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, int((time.perf_counter() - started) * 1000))


def build_gateway(
    *,
    environment: str,
    providers: dict[str, ProviderAdapter] | None = None,
    registry: ProviderRegistry | None = None,
    attempt_sink: AttemptSink | None = None,
    safety_runtime: SafetyRuntime | None = None,
    safety_sink: SafetyDecisionSink | None = None,
    telemetry_sink: TelemetrySink | None = None,
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
        safety_runtime=(safety_runtime if safety_runtime is not None else SafetyRuntime()),
        safety_sink=safety_sink,
        telemetry_sink=telemetry_sink,
    )
