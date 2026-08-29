"""FakeProvider — deterministic, in-process, no network.

Its purpose is to make the *gateway* testable, not to imitate intelligence.
`docs/05_ai/AI_NATIVE_PRINCIPLES.md` §4 item 3 is explicit that a deterministic
fallback is legitimate infrastructure but must never be presented as an AI
capability, and R5 says a `SYNTHETIC` artifact is not a business capability. So
this class is registered as a real provider subject to real admission (there is no
test-only bypass), while its output is honestly synthetic.

It can also be told to misbehave — timeout, non-JSON, schema-violating — because
fail-closed behaviour that has never been observed failing is an assumption.
Injecting those conditions through the normal provider seam means the tests
exercise the same code path production would.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

from backend.intelligence.model_gateway.contracts import StructuredRequest, TokenUsage
from backend.intelligence.model_gateway.errors import FailureKind, ModelGatewayError
from backend.intelligence.model_gateway.providers.base import ProviderResponse


class FakeProvider:
    """Returns a canned response per use case.

    Args:
        responses_by_use_case: `use_case` -> the object to return. An unknown use
            case yields `{}`, which the gateway rejects as `SCHEMA_INVALID` when
            the schema has required properties — the same treatment a real
            provider returning an empty object gets. No special case for "the
            fake was not configured".
        raw_text_by_use_case: bypasses JSON encoding to return an exact string.
            This is how the malformed-response tests inject `"not json at all"`.
        fail_with: raise this failure kind instead of responding.
        delay_seconds: sleep before responding, to exercise the timeout path.
        model: the model identity to report.
    """

    def __init__(
        self,
        responses_by_use_case: dict[str, dict[str, Any]] | None = None,
        *,
        raw_text_by_use_case: dict[str, str] | None = None,
        fail_with: FailureKind | None = None,
        delay_seconds: float = 0.0,
        model: str = "fake-deterministic",
        model_version: str = "1.0.0",
        confidence: float | None = None,
        provider_id: str = "fake-deterministic",
    ) -> None:
        self.provider_id = provider_id
        self._responses = dict(responses_by_use_case or {})
        self._raw_text = dict(raw_text_by_use_case or {})
        self._fail_with = fail_with
        self._delay_seconds = delay_seconds
        self._model = model
        self._model_version = model_version
        self._confidence = confidence
        self.invocations: list[StructuredRequest] = []
        """Every request this provider was asked to run.

        Recorded so tests can assert what *did not* happen — chiefly, that a
        rejected admission never reached the provider at all. Asserting the
        absence of a call is the only way to show admission runs before the call
        rather than alongside it.
        """

    async def invoke(
        self, request: StructuredRequest, *, timeout_seconds: float
    ) -> ProviderResponse:
        self.invocations.append(request)

        if self._delay_seconds:
            # Sleeps rather than raising TIMEOUT directly: the gateway's own
            # deadline must be the thing that fires, otherwise the test would
            # prove the fake can raise TIMEOUT, not that the gateway enforces one.
            await asyncio.sleep(self._delay_seconds)

        if self._fail_with is not None:
            raise ModelGatewayError(
                self._fail_with,
                f"FakeProvider was configured to fail with {self._fail_with}",
                provider_id=self.provider_id,
            )

        if request.use_case in self._raw_text:
            text = self._raw_text[request.use_case]
        else:
            text = json.dumps(self._responses.get(request.use_case, {}), ensure_ascii=False)

        return ProviderResponse(
            text=text,
            model=self._model,
            model_version=self._model_version,
            token_usage=TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
            confidence=self._confidence,
        )


def deterministic_provider(
    build: Callable[[StructuredRequest], dict[str, Any]],
    *,
    provider_id: str = "fake-deterministic",
) -> FakeProvider:
    """A `FakeProvider` whose response is computed from the request.

    Useful where a canned dict is not enough (e.g. echoing `use_case` back to
    prove the gateway forwarded it unchanged) while keeping output fully
    determined by input — no clocks, no randomness, so a failing assertion means a
    real defect rather than a flake.
    """

    class _Computed(FakeProvider):
        async def invoke(
            self, request: StructuredRequest, *, timeout_seconds: float
        ) -> ProviderResponse:
            self._responses[request.use_case] = build(request)
            return await super().invoke(request, timeout_seconds=timeout_seconds)

    return _Computed(provider_id=provider_id)
