"""OpenAI-compatible Chat Completions adapter.

Chosen as the one real adapter because the contract is shared by several vendors
(OpenAI, DeepSeek, Zhipu v4, and most self-hosted or proxied deployments), so one
adapter covers the plausible options without pre-committing to a vendor — which
matters here, since the vendor decision is blocked on a legal question
(不得转委托, `COMPLIANCE_HARD_CONSTRAINTS.md` §7) and not on engineering.

The code path is complete and exercised: `httpx.AsyncClient` is injectable, and
the tests drive it through `httpx.MockTransport`, so the request construction,
status-code classification, body handling and error mapping all run for real
without a network or a key. The registry entry for this adapter is deliberately
non-callable (`sub_delegates=None`) — see `provider_registry.py`.

Credential handling: `build_openai_compatible_provider` is the only function in
the repository that reads a model credential from the environment. R7 requires
credentials be read by the Model Gateway alone, and the key is held in a local
only, never copied into a `ProviderRecord`, a `ProviderResponse`, a provenance
record or an exception message.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from backend.intelligence.model_gateway.contracts import StructuredRequest, TokenUsage
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.providers.base import ProviderResponse

CHAT_COMPLETIONS_PATH = "/chat/completions"


def _system_prompt(request: StructuredRequest) -> str:
    """Instructions plus the schema.

    The version identifiers are included in the prompt as well as in provenance so
    that a captured provider-side request is self-describing during an audit —
    otherwise reconstructing "which prompt version produced this" depends on our
    own records surviving.
    """
    return "\n".join(
        [
            f"use_case={request.use_case}",
            f"prompt_version={request.prompt_version}",
            f"schema_version={request.schema_version}",
            "Return exactly one JSON object matching the schema below.",
            "Do not wrap it in markdown fences and do not add prose.",
            f"output_schema={json.dumps(request.output_schema, ensure_ascii=False)}",
        ]
    )


class OpenAICompatibleProvider:
    """One vendor endpoint speaking the Chat Completions contract."""

    def __init__(
        self,
        *,
        provider_id: str,
        base_url: str,
        api_key: str,
        model: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url:
            raise ModelGatewayError(
                "CREDENTIAL_MISSING", "base_url is required", provider_id=provider_id
            )
        if not api_key:
            raise ModelGatewayError(
                "CREDENTIAL_MISSING",
                "api key is required; the gateway does not fall back to an unauthenticated "
                "call, and it does not silently substitute a fake provider either — a "
                "misconfigured runtime must fail loudly rather than serve synthetic output "
                "that looks like a model answer (R5)",
                provider_id=provider_id,
            )
        self.provider_id = provider_id
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._client = client

    async def invoke(
        self, request: StructuredRequest, *, timeout_seconds: float
    ) -> ProviderResponse:
        body = {
            "model": self._model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _system_prompt(request)},
                {
                    "role": "user",
                    "content": json.dumps(request.payload, ensure_ascii=False),
                },
            ],
        }
        headers = {
            "authorization": f"Bearer {self._api_key}",
            "content-type": "application/json",
        }

        try:
            if self._client is not None:
                response = await self._client.post(
                    f"{self._base_url}{CHAT_COMPLETIONS_PATH}",
                    json=body,
                    headers=headers,
                    timeout=timeout_seconds,
                )
            else:
                async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                    response = await client.post(
                        f"{self._base_url}{CHAT_COMPLETIONS_PATH}",
                        json=body,
                        headers=headers,
                    )
        except httpx.TimeoutException as exc:
            raise ModelGatewayError(
                "TIMEOUT",
                f"provider did not respond within {timeout_seconds}s",
                provider_id=self.provider_id,
            ) from exc
        except httpx.HTTPError as exc:
            # Only the exception *class* name is propagated, not str(exc): httpx
            # error strings can include the request URL and, for some transports,
            # body fragments. Those may contain family data.
            raise ModelGatewayError(
                "NETWORK_ERROR",
                f"transport failure ({type(exc).__name__})",
                provider_id=self.provider_id,
            ) from exc

        if response.status_code >= 500:
            raise ModelGatewayError(
                "PROVIDER_5XX",
                f"provider returned HTTP {response.status_code}",
                provider_id=self.provider_id,
                status_code=response.status_code,
            )
        if response.status_code >= 400:
            raise ModelGatewayError(
                "PROVIDER_4XX",
                f"provider returned HTTP {response.status_code}",
                provider_id=self.provider_id,
                status_code=response.status_code,
            )

        try:
            envelope: dict[str, Any] = response.json()
        except ValueError as exc:
            raise ModelGatewayError(
                "INVALID_JSON",
                "provider response envelope is not JSON",
                provider_id=self.provider_id,
            ) from exc

        text = self._extract_message_content(envelope)
        return ProviderResponse(
            text=text,
            model=str(envelope.get("model") or self._model),
            # Vendors on this contract do not report a distinct version field, so
            # the model id doubles as the version. Recording the *reported* id
            # rather than the configured one means a silent vendor-side model
            # alias shows up in provenance instead of being papered over.
            model_version=str(envelope.get("model") or self._model),
            token_usage=self._extract_usage(envelope),
        )

    def _extract_message_content(self, envelope: dict[str, Any]) -> str:
        choices = envelope.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ModelGatewayError(
                "INVALID_JSON",
                "provider response contained no choices",
                provider_id=self.provider_id,
            )
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise ModelGatewayError(
                "INVALID_JSON",
                "provider response contained no message content",
                provider_id=self.provider_id,
            )
        return content

    @staticmethod
    def _extract_usage(envelope: dict[str, Any]) -> TokenUsage | None:
        usage = envelope.get("usage")
        if not isinstance(usage, dict):
            return None
        return TokenUsage(
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )


def build_openai_compatible_provider(
    *,
    provider_id: str,
    model: str,
    base_url_env_var: str,
    credential_env_var: str,
    env: dict[str, str] | None = None,
    client: httpx.AsyncClient | None = None,
) -> OpenAICompatibleProvider:
    """Construct the adapter from environment variables.

    The single credential-read point in the repository (R7). It raises
    `CREDENTIAL_MISSING` when configuration is absent rather than degrading to a
    fake provider: the source repository's `createAiGatewayFromEnv` fell back to
    `new FakeAiGateway()` whenever real settings were missing, which means a
    production misconfiguration would have quietly served deterministic canned
    output that a caller could not distinguish from a model answer. That is R5's
    "synthetic data on a production route" failure, and it is not reproduced here.
    """
    source = os.environ if env is None else env
    base_url = source.get(base_url_env_var, "")
    api_key = source.get(credential_env_var, "")
    if not base_url or not api_key:
        missing = [
            name
            for name, value in ((base_url_env_var, base_url), (credential_env_var, api_key))
            if not value
        ]
        raise ModelGatewayError(
            "CREDENTIAL_MISSING",
            f"missing environment variable(s) {missing} for provider {provider_id!r}",
            provider_id=provider_id,
        )
    return OpenAICompatibleProvider(
        provider_id=provider_id,
        base_url=base_url,
        api_key=api_key,
        model=model,
        client=client,
    )
