"""HTTP adapter for provider-neutral, metadata-only canary observations."""

from __future__ import annotations

import inspect
from datetime import datetime
from urllib.parse import quote

import httpx

from backend.intelligence.evaluation.deployment import DeploymentReceipt
from backend.intelligence.evaluation.http_deployment import TokenProvider
from backend.intelligence.evaluation.release_catalog import ReleaseCandidate
from backend.platform.security.mtls import MtlsClientConfig

from .canary_supervision import (
    CanaryObservation,
    CanaryObservationPort,
    CanarySupervisionError,
)


class HttpCanaryObservationPort(CanaryObservationPort):
    def __init__(
        self,
        *,
        base_url: str,
        token_provider: TokenProvider,
        client: httpx.AsyncClient | None = None,
        client_config: MtlsClientConfig | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise CanarySupervisionError("CANARY_OBSERVATION_BASE_URL_REQUIRED")
        if not callable(token_provider):
            raise CanarySupervisionError("CANARY_OBSERVATION_TOKEN_PROVIDER_REQUIRED")
        if client_config is not None and not isinstance(client_config, MtlsClientConfig):
            raise CanarySupervisionError("CANARY_OBSERVATION_MTLS_CONFIG_INVALID")
        if client is not None and client_config is not None:
            raise CanarySupervisionError("CANARY_OBSERVATION_MTLS_CLIENT_CONFLICT")
        if (
            not isinstance(timeout_seconds, (int, float))
            or isinstance(timeout_seconds, bool)
            or timeout_seconds <= 0
        ):
            raise CanarySupervisionError("CANARY_OBSERVATION_TIMEOUT_INVALID")
        self._base_url = base_url.rstrip("/")
        self._token_provider = token_provider
        self._client = client
        self._client_config = client_config
        self._timeout_seconds = float(timeout_seconds)

    async def observe(
        self,
        candidate: ReleaseCandidate,
        canary_receipt: DeploymentReceipt,
        *,
        idempotency_key: str,
    ) -> CanaryObservation:
        token = await self._token()
        path = (
            f"/v1/releases/{quote(candidate.candidate_id, safe='')}"
            "/canary-observations"
        )
        headers = {
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
            "idempotency-key": idempotency_key,
            "x-ai-environment": candidate.environment,
        }
        payload = {
            "candidate_id": candidate.candidate_id,
            "environment": candidate.environment,
            "receipt_id": canary_receipt.receipt_id,
            "deployment_ref": canary_receipt.external_ref,
        }
        try:
            response = await self._request(path, headers, payload)
        except httpx.TimeoutException as exc:
            raise CanarySupervisionError("CANARY_OBSERVATION_TIMEOUT") from exc
        except httpx.HTTPError as exc:
            raise CanarySupervisionError("CANARY_OBSERVATION_NETWORK_ERROR") from exc
        if response.status_code >= 500:
            raise CanarySupervisionError("CANARY_OBSERVATION_PLATFORM_5XX")
        if not 200 <= response.status_code < 300:
            raise CanarySupervisionError("CANARY_OBSERVATION_PLATFORM_REJECTED")
        try:
            body = response.json()
        except ValueError as exc:
            raise CanarySupervisionError("CANARY_OBSERVATION_RESPONSE_INVALID_JSON") from exc
        return _observation(body)

    async def _token(self) -> str:
        try:
            value = self._token_provider()
            value = await value if inspect.isawaitable(value) else value
        except Exception as exc:
            raise CanarySupervisionError("CANARY_OBSERVATION_TOKEN_UNAVAILABLE") from exc
        if not isinstance(value, str) or not value.strip():
            raise CanarySupervisionError("CANARY_OBSERVATION_TOKEN_REQUIRED")
        return value

    async def _request(
        self,
        path: str,
        headers: dict[str, str],
        payload: dict[str, str],
    ) -> httpx.Response:
        if self._client is not None:
            return await self._client.post(
                f"{self._base_url}{path}",
                json=payload,
                headers=headers,
                timeout=self._timeout_seconds,
            )
        client_factory = (
            self._client_config.build_async_client
            if self._client_config is not None
            else httpx.AsyncClient
        )
        async with client_factory() as client:
            return await client.post(
                f"{self._base_url}{path}",
                json=payload,
                headers=headers,
                timeout=self._timeout_seconds,
            )


def _observation(body: object) -> CanaryObservation:
    if not isinstance(body, dict):
        raise CanarySupervisionError("CANARY_OBSERVATION_RESPONSE_INVALID")
    try:
        observed_at_raw = body["observed_at"]
        if not isinstance(observed_at_raw, str):
            raise TypeError
        observed_at = datetime.fromisoformat(observed_at_raw.replace("Z", "+00:00"))
        return CanaryObservation(
            observation_id=_string(body, "observation_id"),
            receipt_id=_string(body, "receipt_id"),
            candidate_id=_string(body, "candidate_id"),
            environment=_string(body, "environment"),
            observed_at=observed_at,
            window_seconds=_integer(body, "window_seconds"),
            request_count=_integer(body, "request_count"),
            error_rate=_number(body, "error_rate"),
            p95_latency_ms=_optional_integer(body, "p95_latency_ms"),
            safety_violation_count=_integer(body, "safety_violation_count"),
            minor_safety_violation_count=_integer(body, "minor_safety_violation_count"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CanarySupervisionError("CANARY_OBSERVATION_RESPONSE_INVALID") from exc


def _string(body: dict[object, object], field: str) -> str:
    value = body[field]
    if not isinstance(value, str):
        raise TypeError
    return value


def _integer(body: dict[object, object], field: str) -> int:
    value = body[field]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError
    return value


def _optional_integer(body: dict[object, object], field: str) -> int | None:
    value = body[field]
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError
    return value


def _number(body: dict[object, object], field: str) -> float:
    value = body[field]
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError
    return float(value)


__all__ = ["HttpCanaryObservationPort"]
