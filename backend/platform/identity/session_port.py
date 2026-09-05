"""Provider-neutral identity-session issuance and rotation boundary.

AI request scopes consume an already authenticated bearer session; they must
not mint one from an ``external_ref``.  The production composition root
therefore injects this port from the real ``auth_identity`` service.  This
module only transports opaque session metadata and never persists, hashes, or
logs a token.  Dev/test continues to use the existing process-local fixture.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

import httpx

from backend.platform.security.mtls import MtlsClientConfig

SessionBootstrapTokenSource = Callable[[], str | Awaitable[str]]


class IdentitySessionError(ValueError):
    """Stable, non-sensitive failure from the identity-session boundary."""


@dataclass(frozen=True, slots=True)
class IssuedIdentitySession:
    """Opaque access token returned once by the external identity service."""

    session_id: str
    access_token: str = field(repr=False, compare=False)
    account_id: str
    family_id: str | None
    expires_at: datetime

    def __post_init__(self) -> None:
        for name, value in (("session_id", self.session_id), ("account_id", self.account_id)):
            if not isinstance(value, str) or not value.strip():
                raise IdentitySessionError(f"{name.upper()}_REQUIRED")
        if not isinstance(self.access_token, str) or not self.access_token.strip():
            raise IdentitySessionError("ACCESS_TOKEN_REQUIRED")
        if self.family_id is not None and (
            not isinstance(self.family_id, str) or not self.family_id.strip()
        ):
            raise IdentitySessionError("FAMILY_ID_INVALID")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise IdentitySessionError("EXPIRES_AT_MUST_BE_TIMEZONE_AWARE")


@dataclass(frozen=True, slots=True)
class VerifiedIdentitySession:
    """Metadata returned when auth_identity validates an existing bearer."""

    session_id: str
    account_id: str
    family_id: str | None
    expires_at: datetime

    def __post_init__(self) -> None:
        for name, value in (("session_id", self.session_id), ("account_id", self.account_id)):
            if not isinstance(value, str) or not value.strip():
                raise IdentitySessionError(f"{name.upper()}_REQUIRED")
        if self.family_id is not None and (
            not isinstance(self.family_id, str) or not self.family_id.strip()
        ):
            raise IdentitySessionError("FAMILY_ID_INVALID")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise IdentitySessionError("EXPIRES_AT_MUST_BE_TIMEZONE_AWARE")


class IdentitySessionPort(Protocol):
    """Port owned by auth_identity; callers provide verified identity only."""

    async def issue(
        self, *, account_id: str, person_id: str, family_id: str | None = None
    ) -> IssuedIdentitySession: ...

    async def rotate(self, *, access_token: str) -> IssuedIdentitySession: ...

    async def revoke(self, *, access_token: str) -> None: ...

    async def introspect(self, *, access_token: str) -> VerifiedIdentitySession: ...


class HttpIdentitySessionPort:
    """Call the real auth_identity service over an injected HTTP/mTLS client."""

    def __init__(
        self,
        *,
        base_url: str,
        bootstrap_token_provider: SessionBootstrapTokenSource,
        audience: str,
        client: httpx.AsyncClient | None = None,
        client_config: MtlsClientConfig | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise IdentitySessionError("SESSION_BASE_URL_REQUIRED")
        if not callable(bootstrap_token_provider):
            raise IdentitySessionError("SESSION_BOOTSTRAP_PROVIDER_REQUIRED")
        if not isinstance(audience, str) or not audience.strip():
            raise IdentitySessionError("SESSION_AUDIENCE_REQUIRED")
        if client is not None and client_config is not None:
            raise IdentitySessionError("SESSION_MTLS_CLIENT_CONFLICT")
        if client_config is not None and not isinstance(client_config, MtlsClientConfig):
            raise IdentitySessionError("SESSION_MTLS_CONFIG_INVALID")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or timeout_seconds <= 0
        ):
            raise IdentitySessionError("SESSION_TIMEOUT_INVALID")
        self._base_url = base_url.rstrip("/")
        self._bootstrap_token_provider = bootstrap_token_provider
        self._audience = audience
        self._client = client
        self._client_config = client_config
        self._timeout_seconds = float(timeout_seconds)

    async def issue(
        self, *, account_id: str, person_id: str, family_id: str | None = None
    ) -> IssuedIdentitySession:
        self._required(account_id, "ACCOUNT_ID_REQUIRED")
        self._required(person_id, "PERSON_ID_REQUIRED")
        if family_id is not None:
            self._required(family_id, "FAMILY_ID_INVALID")
        return await self._call(
            "/v1/identity/sessions",
            payload={
                "account_id": account_id,
                "person_id": person_id,
                "family_id": family_id,
                "audience": self._audience,
            },
        )

    async def rotate(self, *, access_token: str) -> IssuedIdentitySession:
        self._required(access_token, "ACCESS_TOKEN_REQUIRED")
        return await self._call(
            "/v1/identity/sessions/rotate",
            session_token=access_token,
            payload={"audience": self._audience},
        )

    async def revoke(self, *, access_token: str) -> None:
        self._required(access_token, "ACCESS_TOKEN_REQUIRED")
        await self._call(
            "/v1/identity/sessions/revoke",
            session_token=access_token,
            payload={"audience": self._audience},
            expect_session=False,
        )

    async def introspect(self, *, access_token: str) -> VerifiedIdentitySession:
        self._required(access_token, "ACCESS_TOKEN_REQUIRED")
        result = await self._call(
            "/v1/identity/sessions/introspect",
            session_token=access_token,
            payload={"audience": self._audience},
            require_access_token=False,
        )
        if not isinstance(result, VerifiedIdentitySession):  # pragma: no cover - guard
            raise IdentitySessionError("SESSION_RESPONSE_INVALID")
        return result

    async def _call(
        self,
        path: str,
        *,
        payload: dict[str, object],
        session_token: str | None = None,
        expect_session: bool = True,
        require_access_token: bool = True,
    ) -> IssuedIdentitySession | VerifiedIdentitySession | None:
        bootstrap = await self._bootstrap_token()
        headers = {
            "authorization": f"Bearer {bootstrap}",
            "content-type": "application/json",
            "x-identity-audience": self._audience,
        }
        # The user session is deliberately separate from the service bootstrap
        # credential and never placed in JSON or an exception message.
        if session_token is not None:
            headers["x-identity-session"] = session_token
        try:
            response = await self._request(path, headers=headers, payload=payload)
        except httpx.TimeoutException as exc:
            raise IdentitySessionError("SESSION_TIMEOUT") from exc
        except httpx.HTTPError as exc:
            raise IdentitySessionError("SESSION_NETWORK_ERROR") from exc
        if not 200 <= response.status_code < 300:
            raise IdentitySessionError("SESSION_PLATFORM_REJECTED")
        if not expect_session:
            return None
        try:
            body = response.json()
        except ValueError as exc:
            raise IdentitySessionError("SESSION_RESPONSE_INVALID_JSON") from exc
        if not isinstance(body, dict):
            raise IdentitySessionError("SESSION_RESPONSE_INVALID")
        try:
            expires_at = _parse_expiry(body["expires_at"])
            if require_access_token:
                result: IssuedIdentitySession | VerifiedIdentitySession = IssuedIdentitySession(
                    session_id=body["session_id"],
                    access_token=body.get("access_token", body.get("token")),
                    account_id=body["account_id"],
                    family_id=body.get("family_id"),
                    expires_at=expires_at,
                )
            else:
                result = VerifiedIdentitySession(
                    session_id=body["session_id"],
                    account_id=body["account_id"],
                    family_id=body.get("family_id"),
                    expires_at=expires_at,
                )
        except (KeyError, TypeError, IdentitySessionError) as exc:
            raise IdentitySessionError("SESSION_RESPONSE_INVALID") from exc
        if result.expires_at <= datetime.now(UTC):
            raise IdentitySessionError("SESSION_RESPONSE_EXPIRED")
        return result

    async def _bootstrap_token(self) -> str:
        try:
            value = self._bootstrap_token_provider()
            value = await value if inspect.isawaitable(value) else value
        except Exception as exc:  # noqa: BLE001 - identity boundary is fail-closed
            raise IdentitySessionError("SESSION_BOOTSTRAP_UNAVAILABLE") from exc
        if not isinstance(value, str) or not value.strip():
            raise IdentitySessionError("SESSION_BOOTSTRAP_REQUIRED")
        return value

    async def _request(
        self, path: str, *, headers: dict[str, str], payload: dict[str, object]
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

    @staticmethod
    def _required(value: str, code: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise IdentitySessionError(code)


def _parse_expiry(value: object) -> datetime:
    if not isinstance(value, str):
        raise IdentitySessionError("SESSION_RESPONSE_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IdentitySessionError("SESSION_RESPONSE_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise IdentitySessionError("SESSION_RESPONSE_INVALID")
    return parsed.astimezone(UTC)


__all__ = [
    "HttpIdentitySessionPort",
    "IdentitySessionError",
    "IdentitySessionPort",
    "IssuedIdentitySession",
    "SessionBootstrapTokenSource",
    "VerifiedIdentitySession",
]
