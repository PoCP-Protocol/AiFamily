"""Explicit operator identity and deployment-token boundaries.

Release/deployment code must not read environment variables or own signing
keys.  The composition root injects an ``OperatorIdentityPort`` and a token
exchange adapter.  This module only transports short-lived tokens in memory and
never persists or logs them.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

import httpx

from backend.intelligence.evaluation.request_operator_identity import current_operator_bearer
from backend.platform.security.mtls import MtlsClientConfig

OperatorTokenSource = Callable[[], str | Awaitable[str]]
RELEASE_DEPLOY_SCOPE = "ai.release.deploy"


class OperatorIdentityError(ValueError):
    """Raised when identity or token exchange is unavailable or malformed."""


@dataclass(frozen=True, slots=True)
class OperatorIdentity:
    """Non-secret operator metadata supplied by an external identity service."""

    operator_id: str
    environment: str
    authorization_ref: str
    scopes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name, value in (
            ("operator_id", self.operator_id),
            ("environment", self.environment),
            ("authorization_ref", self.authorization_ref),
        ):
            if not isinstance(value, str) or not value.strip():
                raise OperatorIdentityError(f"{name.upper()}_REQUIRED")
        if not isinstance(self.scopes, tuple) or any(
            not isinstance(scope, str) or not scope.strip() for scope in self.scopes
        ):
            raise OperatorIdentityError("OPERATOR_SCOPES_INVALID")
        if len(set(self.scopes)) != len(self.scopes):
            raise OperatorIdentityError("OPERATOR_SCOPES_MUST_BE_UNIQUE")


class OperatorIdentityPort(Protocol):
    """Resolve the authenticated human/operator identity for one environment."""

    async def resolve(self, *, environment: str) -> OperatorIdentity: ...


class HttpOperatorIdentityPort:
    """Resolve identity through an injected HTTP client and bootstrap token source."""

    def __init__(
        self,
        *,
        base_url: str,
        bootstrap_token_provider: OperatorTokenSource,
        client: httpx.AsyncClient | None = None,
        client_config: MtlsClientConfig | None = None,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise OperatorIdentityError("IDENTITY_BASE_URL_REQUIRED")
        if not callable(bootstrap_token_provider):
            raise OperatorIdentityError("IDENTITY_TOKEN_PROVIDER_REQUIRED")
        if client_config is not None and not isinstance(client_config, MtlsClientConfig):
            raise OperatorIdentityError("IDENTITY_MTLS_CONFIG_INVALID")
        if client is not None and client_config is not None:
            raise OperatorIdentityError("IDENTITY_MTLS_CLIENT_CONFLICT")
        self._base_url = base_url.rstrip("/")
        self._bootstrap_token_provider = bootstrap_token_provider
        self._client = client
        self._client_config = client_config

    async def resolve(self, *, environment: str) -> OperatorIdentity:
        if not isinstance(environment, str) or not environment.strip():
            raise OperatorIdentityError("IDENTITY_ENVIRONMENT_REQUIRED")
        token = await _resolve_token_source(
            self._bootstrap_token_provider,
            missing_code="IDENTITY_BOOTSTRAP_TOKEN_REQUIRED",
            unavailable_code="IDENTITY_BOOTSTRAP_UNAVAILABLE",
        )
        headers = {"authorization": f"Bearer {token}", "x-ai-environment": environment}
        try:
            response = await self._request("GET", "/v1/operator/identity", headers=headers)
        except httpx.TimeoutException as exc:
            raise OperatorIdentityError("IDENTITY_TIMEOUT") from exc
        except httpx.HTTPError as exc:
            raise OperatorIdentityError("IDENTITY_NETWORK_ERROR") from exc
        if not 200 <= response.status_code < 300:
            raise OperatorIdentityError("IDENTITY_PLATFORM_REJECTED")
        try:
            body = response.json()
        except ValueError as exc:
            raise OperatorIdentityError("IDENTITY_RESPONSE_INVALID_JSON") from exc
        if not isinstance(body, dict):
            raise OperatorIdentityError("IDENTITY_RESPONSE_INVALID")
        try:
            raw_scopes = body.get("scopes", ())
            if not isinstance(raw_scopes, (list, tuple)):
                raise OperatorIdentityError("IDENTITY_RESPONSE_INVALID")
            identity = OperatorIdentity(
                operator_id=body["operator_id"],
                environment=body["environment"],
                authorization_ref=body["authorization_ref"],
                scopes=tuple(raw_scopes),
            )
        except (KeyError, TypeError, OperatorIdentityError) as exc:
            raise OperatorIdentityError("IDENTITY_RESPONSE_INVALID") from exc
        if identity.environment != environment:
            raise OperatorIdentityError("IDENTITY_ENVIRONMENT_MISMATCH")
        return identity

    async def _request(self, method: str, path: str, *, headers: dict[str, str]) -> httpx.Response:
        if self._client is not None:
            return await self._client.request(method, f"{self._base_url}{path}", headers=headers)
        client_factory = (
            self._client_config.build_async_client
            if self._client_config is not None
            else httpx.AsyncClient
        )
        async with client_factory() as client:
            return await client.request(method, f"{self._base_url}{path}", headers=headers)


class HttpRequestOperatorIdentityPort:
    """Resolve identity using the bearer bound to the current HTTP request."""

    def __init__(
        self,
        *,
        base_url: str,
        client: httpx.AsyncClient | None = None,
        client_config: MtlsClientConfig | None = None,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise OperatorIdentityError("IDENTITY_BASE_URL_REQUIRED")
        if client_config is not None and not isinstance(client_config, MtlsClientConfig):
            raise OperatorIdentityError("IDENTITY_MTLS_CONFIG_INVALID")
        if client is not None and client_config is not None:
            raise OperatorIdentityError("IDENTITY_MTLS_CLIENT_CONFLICT")
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._client_config = client_config

    async def resolve(self, *, environment: str) -> OperatorIdentity:
        if not isinstance(environment, str) or not environment.strip():
            raise OperatorIdentityError("IDENTITY_ENVIRONMENT_REQUIRED")
        token = current_operator_bearer()
        try:
            response = await self._request(
                "GET",
                "/v1/operator/identity",
                headers={
                    "authorization": f"Bearer {token}",
                    "x-ai-environment": environment,
                },
            )
        except httpx.TimeoutException as exc:
            raise OperatorIdentityError("IDENTITY_TIMEOUT") from exc
        except httpx.HTTPError as exc:
            raise OperatorIdentityError("IDENTITY_NETWORK_ERROR") from exc
        if not 200 <= response.status_code < 300:
            raise OperatorIdentityError("IDENTITY_PLATFORM_REJECTED")
        try:
            body = response.json()
        except ValueError as exc:
            raise OperatorIdentityError("IDENTITY_RESPONSE_INVALID_JSON") from exc
        if not isinstance(body, dict):
            raise OperatorIdentityError("IDENTITY_RESPONSE_INVALID")
        try:
            raw_scopes = body.get("scopes", ())
            if not isinstance(raw_scopes, (list, tuple)):
                raise OperatorIdentityError("IDENTITY_RESPONSE_INVALID")
            identity = OperatorIdentity(
                operator_id=body["operator_id"],
                environment=body["environment"],
                authorization_ref=body["authorization_ref"],
                scopes=tuple(raw_scopes),
            )
        except (KeyError, TypeError, OperatorIdentityError) as exc:
            raise OperatorIdentityError("IDENTITY_RESPONSE_INVALID") from exc
        if identity.environment != environment:
            raise OperatorIdentityError("IDENTITY_ENVIRONMENT_MISMATCH")
        return identity

    async def _request(self, method: str, path: str, *, headers: dict[str, str]) -> httpx.Response:
        if self._client is not None:
            return await self._client.request(method, f"{self._base_url}{path}", headers=headers)
        client_factory = (
            self._client_config.build_async_client
            if self._client_config is not None
            else httpx.AsyncClient
        )
        async with client_factory() as client:
            return await client.request(method, f"{self._base_url}{path}", headers=headers)


class HttpOperatorTokenProvider:
    """Exchange an explicitly resolved identity for a short-lived bearer token."""

    def __init__(
        self,
        *,
        base_url: str,
        identity_port: OperatorIdentityPort,
        bootstrap_token_provider: OperatorTokenSource,
        audience: str,
        environment: str,
        required_scope: str = RELEASE_DEPLOY_SCOPE,
        client: httpx.AsyncClient | None = None,
        client_config: MtlsClientConfig | None = None,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise OperatorIdentityError("TOKEN_BASE_URL_REQUIRED")
        if not callable(getattr(identity_port, "resolve", None)):
            raise OperatorIdentityError("IDENTITY_PORT_REQUIRED")
        if not callable(bootstrap_token_provider):
            raise OperatorIdentityError("TOKEN_PROVIDER_REQUIRED")
        if not isinstance(audience, str) or not audience.strip():
            raise OperatorIdentityError("TOKEN_AUDIENCE_REQUIRED")
        if not isinstance(environment, str) or not environment.strip():
            raise OperatorIdentityError("TOKEN_ENVIRONMENT_REQUIRED")
        if not isinstance(required_scope, str) or not required_scope.strip():
            raise OperatorIdentityError("TOKEN_SCOPE_REQUIRED")
        if client_config is not None and not isinstance(client_config, MtlsClientConfig):
            raise OperatorIdentityError("TOKEN_MTLS_CONFIG_INVALID")
        if client is not None and client_config is not None:
            raise OperatorIdentityError("TOKEN_MTLS_CLIENT_CONFLICT")
        self._base_url = base_url.rstrip("/")
        self._identity_port = identity_port
        self._bootstrap_token_provider = bootstrap_token_provider
        self._audience = audience
        self._environment = environment
        self._required_scope = required_scope
        self._client = client
        self._client_config = client_config

    async def __call__(self) -> str:
        identity = await self._identity_port.resolve(environment=self._environment)
        if not isinstance(identity, OperatorIdentity):
            raise OperatorIdentityError("TOKEN_IDENTITY_INVALID")
        if identity.environment != self._environment:
            raise OperatorIdentityError("TOKEN_IDENTITY_ENVIRONMENT_MISMATCH")
        if self._required_scope not in identity.scopes:
            raise OperatorIdentityError("TOKEN_OPERATOR_SCOPE_MISSING")
        bootstrap = await _resolve_token_source(
            self._bootstrap_token_provider,
            missing_code="TOKEN_BOOTSTRAP_REQUIRED",
            unavailable_code="TOKEN_BOOTSTRAP_UNAVAILABLE",
        )
        headers = {
            "authorization": f"Bearer {bootstrap}",
            "content-type": "application/json",
            "x-ai-environment": self._environment,
        }
        payload = {
            "operator_id": identity.operator_id,
            "authorization_ref": identity.authorization_ref,
            "audience": self._audience,
            "environment": self._environment,
        }
        try:
            response = await self._request("POST", "/v1/operator/tokens", headers, payload)
        except httpx.TimeoutException as exc:
            raise OperatorIdentityError("TOKEN_TIMEOUT") from exc
        except httpx.HTTPError as exc:
            raise OperatorIdentityError("TOKEN_NETWORK_ERROR") from exc
        if not 200 <= response.status_code < 300:
            raise OperatorIdentityError("TOKEN_PLATFORM_REJECTED")
        try:
            body = response.json()
        except ValueError as exc:
            raise OperatorIdentityError("TOKEN_RESPONSE_INVALID_JSON") from exc
        token = body.get("access_token") if isinstance(body, dict) else None
        if not isinstance(token, str) or not token.strip():
            raise OperatorIdentityError("TOKEN_RESPONSE_INVALID")
        return token

    async def _request(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        payload: dict[str, str],
    ) -> httpx.Response:
        if self._client is not None:
            return await self._client.request(
                method, f"{self._base_url}{path}", json=payload, headers=headers
            )
        client_factory = (
            self._client_config.build_async_client
            if self._client_config is not None
            else httpx.AsyncClient
        )
        async with client_factory() as client:
            return await client.request(
                method, f"{self._base_url}{path}", json=payload, headers=headers
            )


async def _resolve_token_source(
    source: OperatorTokenSource,
    *,
    missing_code: str,
    unavailable_code: str,
) -> str:
    """Read an injected bootstrap token without leaking source exceptions."""

    try:
        value = source()
        value = await value if inspect.isawaitable(value) else value
    except OperatorIdentityError:
        raise
    except Exception as exc:
        raise OperatorIdentityError(unavailable_code) from exc
    if not isinstance(value, str) or not value.strip():
        raise OperatorIdentityError(missing_code)
    return value


__all__ = [
    "HttpOperatorIdentityPort",
    "HttpRequestOperatorIdentityPort",
    "HttpOperatorTokenProvider",
    "OperatorIdentity",
    "OperatorIdentityError",
    "OperatorIdentityPort",
    "OperatorTokenSource",
    "RELEASE_DEPLOY_SCOPE",
]
