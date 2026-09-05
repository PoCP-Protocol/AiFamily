"""HTTP deployment adapter for the provider-neutral deployment port.

The adapter is deliberately infrastructure-only.  It receives an injected
credential/token provider and ``httpx.AsyncClient`` so test, staging, and
production use the same request/error contract.  It never reads environment
secrets, model credentials, family payloads, or provider SDKs itself.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import quote

import httpx

from backend.intelligence.evaluation.deployment import (
    DeploymentError,
    DeploymentPhase,
    DeploymentPort,
    DeploymentResult,
)
from backend.intelligence.evaluation.release_catalog import ReleaseCandidate
from backend.intelligence.evaluation.release_control import ReleaseControlEvent
from backend.platform.security.mtls import MtlsClientConfig

TokenProvider = Callable[[], str | Awaitable[str]]


class HttpDeploymentPort(DeploymentPort):
    """Call an external rollout API using an explicit, injected client."""

    def __init__(
        self,
        *,
        base_url: str,
        token_provider: TokenProvider,
        client: httpx.AsyncClient | None = None,
        client_config: MtlsClientConfig | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise DeploymentError("DEPLOYMENT_BASE_URL_REQUIRED")
        if not callable(token_provider):
            raise DeploymentError("DEPLOYMENT_TOKEN_PROVIDER_REQUIRED")
        if client_config is not None and not isinstance(client_config, MtlsClientConfig):
            raise DeploymentError("DEPLOYMENT_MTLS_CONFIG_INVALID")
        if client is not None and client_config is not None:
            raise DeploymentError("DEPLOYMENT_MTLS_CLIENT_CONFLICT")
        if (
            not isinstance(timeout_seconds, (int, float))
            or isinstance(timeout_seconds, bool)
            or timeout_seconds <= 0
        ):
            raise DeploymentError("DEPLOYMENT_TIMEOUT_INVALID")
        self._base_url = base_url.rstrip("/")
        self._token_provider = token_provider
        self._client = client
        self._client_config = client_config
        self._timeout_seconds = float(timeout_seconds)

    async def apply(
        self,
        candidate: ReleaseCandidate,
        control: ReleaseControlEvent,
        *,
        phase: DeploymentPhase,
        rollout_percent: int,
        idempotency_key: str,
    ) -> DeploymentResult:
        return await self.request(
            "POST",
            f"/v1/releases/{quote(candidate.candidate_id, safe='')}/deployments",
            candidate,
            control,
            idempotency_key=idempotency_key,
            payload={
                "environment": candidate.environment,
                "phase": phase.value,
                "rollout_percent": rollout_percent,
                "provider_id": candidate.provider_id,
                "model": candidate.model,
                "model_version": candidate.model_version,
            },
        )

    async def rollback(
        self,
        candidate: ReleaseCandidate,
        control: ReleaseControlEvent,
        *,
        idempotency_key: str,
    ) -> DeploymentResult:
        return await self.request(
            "POST",
            f"/v1/releases/{quote(candidate.candidate_id, safe='')}/rollback",
            candidate,
            control,
            idempotency_key=idempotency_key,
            payload={
                "environment": candidate.environment,
                "target_candidate_id": control.target_candidate_id,
            },
        )

    async def request(
        self,
        method: str,
        path: str,
        candidate: ReleaseCandidate,
        control: ReleaseControlEvent,
        *,
        idempotency_key: str,
        payload: dict[str, Any],
    ) -> DeploymentResult:
        """Send one governed deployment request for specialized port adapters."""
        try:
            token = self._token_provider()
            token = await token if inspect.isawaitable(token) else token
        except DeploymentError:
            raise
        except Exception as exc:
            raise DeploymentError("DEPLOYMENT_TOKEN_UNAVAILABLE") from exc
        if not isinstance(token, str) or not token.strip():
            raise DeploymentError("DEPLOYMENT_TOKEN_REQUIRED")
        headers = {
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
            "idempotency-key": idempotency_key,
            "x-ai-control-id": control.control_id,
            "x-ai-environment": candidate.environment,
        }
        try:
            if self._client is not None:
                response = await self._client.request(
                    method,
                    f"{self._base_url}{path}",
                    json=payload,
                    headers=headers,
                    timeout=self._timeout_seconds,
                )
            else:
                client_factory = (
                    self._client_config.build_async_client
                    if self._client_config is not None
                    else httpx.AsyncClient
                )
                async with client_factory() as client:
                    response = await client.request(
                        method,
                        f"{self._base_url}{path}",
                        json=payload,
                        headers=headers,
                        timeout=self._timeout_seconds,
                    )
        except httpx.TimeoutException as exc:
            raise DeploymentError("DEPLOYMENT_TIMEOUT") from exc
        except httpx.HTTPError as exc:
            raise DeploymentError("DEPLOYMENT_NETWORK_ERROR") from exc
        if response.status_code < 200 or 300 <= response.status_code < 400:
            raise DeploymentError("DEPLOYMENT_PLATFORM_UNEXPECTED_STATUS")
        if response.status_code >= 500:
            raise DeploymentError("DEPLOYMENT_PLATFORM_5XX")
        if response.status_code >= 400:
            raise DeploymentError("DEPLOYMENT_PLATFORM_4XX")
        try:
            body = response.json()
        except ValueError as exc:
            raise DeploymentError("DEPLOYMENT_RESPONSE_INVALID_JSON") from exc
        if not isinstance(body, dict) or not isinstance(body.get("external_ref"), str):
            raise DeploymentError("DEPLOYMENT_EXTERNAL_REF_REQUIRED")
        return DeploymentResult(external_ref=body["external_ref"])


__all__ = ["HttpDeploymentPort", "TokenProvider"]
