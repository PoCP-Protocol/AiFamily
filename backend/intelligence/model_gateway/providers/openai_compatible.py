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

import asyncio
import inspect
import json
import math
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from backend.intelligence.model_gateway.contracts import MediaInput, StructuredRequest, TokenUsage
from backend.intelligence.model_gateway.credentials import (
    CredentialLease,
    CredentialRevocationChecker,
)
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
    plan = request.prompt_execution_plan
    if plan is None:
        raise ModelGatewayError(
            "POLICY_REJECTED",
            "OpenAI-compatible invocation requires a reviewed PromptExecutionPlan",
        )
    policy_block = [
        "<reviewed_system_policy>",
        plan.system_policy,
        "</reviewed_system_policy>",
    ]
    knowledge_blocks: list[str] = []
    for item in plan.knowledge_materials:
        metadata = {
            "knowledge_ref": item.knowledge_ref,
            "source_ref": item.source_ref,
            "license_ref": item.license_ref,
            "evidence_level": item.evidence_level,
            "content_digest": item.content_digest,
        }
        knowledge_blocks.extend(
            [
                f"<reviewed_knowledge metadata={json.dumps(metadata, ensure_ascii=False)}>",
                item.content,
                "</reviewed_knowledge>",
            ]
        )
    return "\n".join(
        [
            *policy_block,
            *knowledge_blocks,
            "<reviewed_prompt_template>",
            plan.template,
            "</reviewed_prompt_template>",
            f"prompt_ref={plan.prompt_ref}",
            f"use_case={request.use_case}",
            f"prompt_version={request.prompt_version}",
            f"schema_version={request.schema_version}",
            f"system_policy_ref={plan.system_policy_ref}",
            f"safety_policy_version={plan.safety_policy_version}",
            f"knowledge_refs={json.dumps(plan.knowledge_refs, ensure_ascii=False)}",
            f"asset_digest={plan.asset_digest}",
            f"material_digest={plan.material_digest}",
            "Return exactly one JSON object matching the schema below.",
            "Do not wrap it in markdown fences and do not add prose.",
            f"output_schema={json.dumps(request.output_schema, ensure_ascii=False)}",
        ]
    )


class OpenAICompatibleProvider:
    """One vendor endpoint speaking the Chat Completions contract."""

    # The common Chat Completions contract currently supports text and image in
    # this adapter. Audio/video remain explicit capabilities of other adapters;
    # they must never be silently downgraded to text.
    supported_modalities = frozenset({"TEXT", "IMAGE"})

    def __init__(
        self,
        *,
        provider_id: str,
        base_url: str,
        api_key: str,
        model: str,
        client: httpx.AsyncClient | None = None,
        lease: CredentialLease | None = None,
        revocation_checker: CredentialRevocationChecker | None = None,
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
        if revocation_checker is not None and not callable(revocation_checker):
            raise ModelGatewayError(
                "CREDENTIAL_INVALID",
                "credential revocation checker is invalid",
                provider_id=provider_id,
            )
        self._lease = lease
        self._revocation_checker = revocation_checker

    async def invoke(
        self, request: StructuredRequest, *, timeout_seconds: float
    ) -> ProviderResponse:
        await self._assert_lease_active(timeout_seconds=timeout_seconds)
        user_content: list[dict[str, object]] = [
            {
                "type": "text",
                "text": json.dumps(request.payload, ensure_ascii=False),
            }
        ]
        for media in request.media_inputs:
            user_content.append(self._media_part(media))
        body = {
            "model": self._model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _system_prompt(request)},
                {
                    "role": "user",
                    "content": user_content if request.media_inputs else user_content[0]["text"],
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

    async def _assert_lease_active(self, *, timeout_seconds: float) -> None:
        lease = self._lease
        if lease is None:
            return
        if lease.revoked:
            raise ModelGatewayError(
                "CREDENTIAL_REVOKED",
                "credential lease has been revoked",
                provider_id=self.provider_id,
            )
        if (
            not isinstance(timeout_seconds, (int, float))
            or isinstance(timeout_seconds, bool)
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ModelGatewayError(
                "CREDENTIAL_INVALID",
                "provider request timeout is invalid",
                provider_id=self.provider_id,
            )
        now = datetime.now(UTC)
        if lease.expires_at <= now:
            raise ModelGatewayError(
                "CREDENTIAL_EXPIRED",
                "credential lease has expired",
                provider_id=self.provider_id,
            )
        if lease.expires_at <= now + timedelta(seconds=timeout_seconds):
            raise ModelGatewayError(
                "CREDENTIAL_EXPIRED",
                "credential lease expires before provider request deadline",
                provider_id=self.provider_id,
            )
        if self._revocation_checker is None:
            return
        try:
            result = await asyncio.to_thread(
                self._revocation_checker, self.provider_id, lease.lease_id
            )
            result = await result if inspect.isawaitable(result) else result
        except ModelGatewayError:
            raise
        except Exception as exc:  # noqa: BLE001 - revocation must fail closed
            raise ModelGatewayError(
                "CREDENTIAL_UNAVAILABLE",
                "credential revocation status unavailable",
                provider_id=self.provider_id,
            ) from exc
        if not isinstance(result, bool):
            raise ModelGatewayError(
                "CREDENTIAL_INVALID",
                "credential revocation status is invalid",
                provider_id=self.provider_id,
            )
        if result:
            raise ModelGatewayError(
                "CREDENTIAL_REVOKED",
                "credential lease has been revoked",
                provider_id=self.provider_id,
            )

    def _media_part(self, media: MediaInput) -> dict[str, object]:
        """Translate the provider-neutral media reference to Chat Completions.

        Image input is the first multimodal capability because it is supported
        consistently by mature vision models. Audio/video remain explicit
        unsupported capabilities until a provider contract is approved; they
        must not be silently downgraded to text and presented as multimodal.
        """
        if media.media_type == "IMAGE":
            return {"type": "image_url", "image_url": {"url": media.uri}}
        raise ModelGatewayError(
            "UNSUPPORTED_MODALITY",
            f"provider adapter does not support {media.media_type} input",
            provider_id=self.provider_id,
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


def build_openai_compatible_provider_from_lease(
    *,
    provider_id: str,
    model: str,
    base_url: str,
    lease: CredentialLease,
    client: httpx.AsyncClient | None = None,
    revocation_checker: CredentialRevocationChecker | None = None,
) -> OpenAICompatibleProvider:
    """Construct an adapter from a short-lived external credential lease.

    The lease is checked before the adapter is created and is never copied to a
    provenance record or exception.  Refresh/rotation is owned by the injected
    key-service implementation; callers should request a new lease when a
    composition root is rebuilt.
    """

    if lease.provider_id != provider_id:
        raise ModelGatewayError(
            "CREDENTIAL_PROVIDER_MISMATCH",
            f"credential lease belongs to {lease.provider_id!r}, not {provider_id!r}",
            provider_id=provider_id,
        )
    return OpenAICompatibleProvider(
        provider_id=provider_id,
        base_url=base_url,
        api_key=lease.api_key,
        model=model,
        client=client,
        lease=lease,
        revocation_checker=revocation_checker,
    )
