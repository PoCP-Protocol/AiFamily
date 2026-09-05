"""Provider credential lease boundary.

The Model Gateway may hold a provider credential only for the duration of an
adapter lease.  Secret-manager, mTLS and rotation details stay outside the
gateway behind :class:`ProviderCredentialPort`; this module deliberately has
no persistence or logging implementation.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

import httpx

from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.platform.security.mtls import MtlsClientConfig


@dataclass(frozen=True, slots=True)
class CredentialLease:
    """Short-lived provider credential returned by an external key service."""

    provider_id: str
    api_key: str = field(repr=False, compare=False)
    expires_at: datetime
    lease_id: str
    revoked: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, str):
            raise ValueError("CredentialLease.provider_id must be a string")
        if not self.provider_id.strip():
            raise ValueError("CredentialLease.provider_id is required")
        if not isinstance(self.api_key, str) or not self.api_key:
            raise ModelGatewayError(
                "CREDENTIAL_MISSING",
                f"credential lease for provider {self.provider_id!r} is empty",
                provider_id=self.provider_id,
            )
        if not isinstance(self.lease_id, str):
            raise ValueError("CredentialLease.lease_id must be a string")
        if not self.lease_id.strip():
            raise ValueError("CredentialLease.lease_id is required")
        if not isinstance(self.revoked, bool):
            raise ValueError("CredentialLease.revoked must be a bool")
        if self.revoked:
            raise ModelGatewayError(
                "CREDENTIAL_REVOKED",
                f"credential lease for provider {self.provider_id!r} is revoked",
                provider_id=self.provider_id,
            )
        if not isinstance(self.expires_at, datetime):
            raise ValueError("CredentialLease.expires_at must be a datetime")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("CredentialLease.expires_at must be timezone-aware")
        if self.expires_at <= datetime.now(UTC):
            raise ModelGatewayError(
                "CREDENTIAL_EXPIRED",
                f"credential lease for provider {self.provider_id!r} is expired",
                provider_id=self.provider_id,
            )


class ProviderCredentialPort(Protocol):
    """External key-service contract; implementations must not log the secret."""

    def resolve(self, *, provider_id: str, environment: str) -> CredentialLease:
        """Return a currently valid lease or raise a stable gateway error."""


CredentialRevocationChecker = Callable[[str, str], bool | Awaitable[bool]]


@dataclass(frozen=True, slots=True)
class CredentialLeaseMetadata:
    """Non-secret lease metadata returned by a key-management service."""

    provider_id: str
    lease_id: str
    expires_at: datetime
    revoked: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, str) or not self.provider_id.strip():
            raise ValueError("CredentialLeaseMetadata.provider_id is required")
        if not isinstance(self.lease_id, str) or not self.lease_id.strip():
            raise ValueError("CredentialLeaseMetadata.lease_id is required")
        if not isinstance(self.expires_at, datetime):
            raise ValueError("CredentialLeaseMetadata.expires_at must be a datetime")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("CredentialLeaseMetadata.expires_at must be timezone-aware")
        if not isinstance(self.revoked, bool):
            raise ValueError("CredentialLeaseMetadata.revoked must be a bool")


class SecretManagerCredentialPort:
    """Adapt a KMS/Secret Manager into the Gateway credential port.

    Secret material is read by ``secret_reader`` only after provider-scoped
    metadata has been resolved.  The adapter never logs or stores the secret
    reference, and all resolver failures become stable, non-sensitive gateway
    errors.  Rotation and revocation remain owned by the metadata resolver.
    """

    def __init__(
        self,
        *,
        secret_reference_resolver: Callable[[str, str], str],
        metadata_resolver: Callable[[str, str], CredentialLeaseMetadata],
        secret_reader: Callable[[str], str],
    ) -> None:
        for name, resolver in (
            ("secret_reference_resolver", secret_reference_resolver),
            ("metadata_resolver", metadata_resolver),
            ("secret_reader", secret_reader),
        ):
            if not callable(resolver):
                raise ValueError(f"{name} must be callable")
        self._secret_reference_resolver = secret_reference_resolver
        self._metadata_resolver = metadata_resolver
        self._secret_reader = secret_reader

    def resolve(self, *, provider_id: str, environment: str) -> CredentialLease:
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise ModelGatewayError("CREDENTIAL_INVALID", "provider id is required")
        if not isinstance(environment, str) or not environment.strip():
            raise ModelGatewayError(
                "CREDENTIAL_INVALID", "credential environment is required", provider_id=provider_id
            )
        try:
            metadata = self._metadata_resolver(provider_id, environment)
        except ModelGatewayError:
            raise
        except Exception as exc:  # noqa: BLE001 - secret boundary is fail-closed
            raise ModelGatewayError(
                "CREDENTIAL_UNAVAILABLE",
                "credential lease metadata unavailable",
                provider_id=provider_id,
            ) from exc
        if not isinstance(metadata, CredentialLeaseMetadata):
            raise ModelGatewayError(
                "CREDENTIAL_INVALID",
                "credential lease metadata is invalid",
                provider_id=provider_id,
            )
        if metadata.provider_id != provider_id:
            raise ModelGatewayError(
                "CREDENTIAL_PROVIDER_MISMATCH",
                "credential lease metadata belongs to another provider",
                provider_id=provider_id,
            )
        if metadata.revoked:
            raise ModelGatewayError(
                "CREDENTIAL_REVOKED",
                f"credential lease for provider {provider_id!r} is revoked",
                provider_id=provider_id,
            )
        if metadata.expires_at <= datetime.now(UTC):
            raise ModelGatewayError(
                "CREDENTIAL_EXPIRED",
                f"credential lease for provider {provider_id!r} is expired",
                provider_id=provider_id,
            )
        try:
            secret_ref = self._secret_reference_resolver(provider_id, environment)
            if not isinstance(secret_ref, str) or not secret_ref.strip():
                raise ValueError("secret reference is empty")
            secret = self._secret_reader(secret_ref)
            if not isinstance(secret, str) or not secret:
                raise ValueError("credential secret is empty")
        except ModelGatewayError:
            raise
        except Exception as exc:  # noqa: BLE001 - never expose secret-manager details
            raise ModelGatewayError(
                "CREDENTIAL_UNAVAILABLE",
                "credential secret unavailable",
                provider_id=provider_id,
            ) from exc
        try:
            return CredentialLease(
                provider_id=metadata.provider_id,
                api_key=secret,
                expires_at=metadata.expires_at,
                lease_id=metadata.lease_id,
                revoked=metadata.revoked,
            )
        except ModelGatewayError:
            raise
        except (TypeError, ValueError) as exc:
            raise ModelGatewayError(
                "CREDENTIAL_INVALID", "credential lease is invalid", provider_id=provider_id
            ) from exc


class HttpProviderCredentialPort:
    """Synchronous HTTP adapter for an external credential/secret service.

    The HTTP client is injected so a production composition root can configure
    mTLS, CA pinning and connection pooling there.  This adapter owns neither
    certificates nor secret persistence; it only holds the returned lease long
    enough for the caller to construct a provider adapter.
    """

    def __init__(
        self,
        *,
        base_url: str,
        bootstrap_token_provider: Callable[[], str],
        audience: str,
        client: httpx.Client | None = None,
        client_config: MtlsClientConfig | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("CREDENTIAL_BASE_URL_REQUIRED")
        if not callable(bootstrap_token_provider):
            raise ValueError("CREDENTIAL_TOKEN_PROVIDER_REQUIRED")
        if client_config is not None and not isinstance(client_config, MtlsClientConfig):
            raise ValueError("CREDENTIAL_MTLS_CONFIG_INVALID")
        if client is not None and client_config is not None:
            raise ValueError("CREDENTIAL_MTLS_CLIENT_CONFLICT")
        if not isinstance(audience, str) or not audience.strip():
            raise ValueError("CREDENTIAL_AUDIENCE_REQUIRED")
        if timeout_seconds <= 0:
            raise ValueError("CREDENTIAL_TIMEOUT_MUST_BE_POSITIVE")
        self._base_url = base_url.rstrip("/")
        self._bootstrap_token_provider = bootstrap_token_provider
        self._audience = audience
        self._client = client
        self._client_config = client_config
        self._timeout_seconds = timeout_seconds

    def resolve(self, *, provider_id: str, environment: str) -> CredentialLease:
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise ModelGatewayError("CREDENTIAL_INVALID", "provider id is required")
        if not isinstance(environment, str) or not environment.strip():
            raise ModelGatewayError(
                "CREDENTIAL_INVALID", "credential environment is required", provider_id=provider_id
            )
        token = self._resolve_bootstrap_token(provider_id)
        headers = {
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
            "x-ai-environment": environment,
        }
        payload = {
            "provider_id": provider_id,
            "environment": environment,
            "audience": self._audience,
        }
        try:
            response = self._request("POST", "/v1/provider-credentials/leases", headers, payload)
        except httpx.TimeoutException as exc:
            raise ModelGatewayError(
                "CREDENTIAL_TIMEOUT", "credential service timed out", provider_id=provider_id
            ) from exc
        except httpx.HTTPError as exc:
            raise ModelGatewayError(
                "CREDENTIAL_NETWORK_ERROR",
                f"credential service transport failure ({type(exc).__name__})",
                provider_id=provider_id,
            ) from exc
        if not 200 <= response.status_code < 300:
            raise ModelGatewayError(
                "CREDENTIAL_PLATFORM_REJECTED",
                f"credential service returned HTTP {response.status_code}",
                provider_id=provider_id,
                status_code=response.status_code,
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise ModelGatewayError(
                "CREDENTIAL_INVALID",
                "credential service response is not JSON",
                provider_id=provider_id,
            ) from exc
        if not isinstance(body, dict):
            raise ModelGatewayError(
                "CREDENTIAL_INVALID",
                "credential service response is invalid",
                provider_id=provider_id,
            )
        try:
            lease = CredentialLease(
                provider_id=body["provider_id"],
                api_key=body["api_key"],
                expires_at=_parse_expiry(body["expires_at"]),
                lease_id=body["lease_id"],
                revoked=body.get("revoked", False),
            )
        except (KeyError, TypeError, ValueError, ModelGatewayError) as exc:
            if isinstance(exc, ModelGatewayError):
                raise
            raise ModelGatewayError(
                "CREDENTIAL_INVALID",
                "credential service response is invalid",
                provider_id=provider_id,
            ) from exc
        if lease.provider_id != provider_id:
            raise ModelGatewayError(
                "CREDENTIAL_PROVIDER_MISMATCH",
                "credential service returned a lease for another provider",
                provider_id=provider_id,
            )
        return lease

    def check_revocation(
        self, *, provider_id: str, lease_id: str, environment: str
    ) -> bool:
        """Read the current revocation bit from the external lease service.

        The status endpoint is deliberately separate from lease issuance: a
        provider adapter can therefore fail closed when an operator revokes a
        lease after startup.  The response is metadata-only and never returns
        the credential itself.
        """

        if not isinstance(provider_id, str) or not provider_id.strip():
            raise ModelGatewayError("CREDENTIAL_INVALID", "provider id is required")
        if not isinstance(lease_id, str) or not lease_id.strip():
            raise ModelGatewayError(
                "CREDENTIAL_INVALID", "credential lease id is required", provider_id=provider_id
            )
        if not isinstance(environment, str) or not environment.strip():
            raise ModelGatewayError(
                "CREDENTIAL_INVALID", "credential environment is required", provider_id=provider_id
            )
        token = self._resolve_bootstrap_token(provider_id)
        headers = {
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
            "x-ai-environment": environment,
        }
        payload = {
            "provider_id": provider_id,
            "lease_id": lease_id,
            "environment": environment,
            "audience": self._audience,
        }
        try:
            response = self._request(
                "POST",
                "/v1/provider-credentials/leases/revocation-status",
                headers,
                payload,
            )
        except httpx.TimeoutException as exc:
            raise ModelGatewayError(
                "CREDENTIAL_TIMEOUT", "credential service timed out", provider_id=provider_id
            ) from exc
        except httpx.HTTPError as exc:
            raise ModelGatewayError(
                "CREDENTIAL_NETWORK_ERROR",
                f"credential service transport failure ({type(exc).__name__})",
                provider_id=provider_id,
            ) from exc
        if not 200 <= response.status_code < 300:
            raise ModelGatewayError(
                "CREDENTIAL_PLATFORM_REJECTED",
                f"credential service returned HTTP {response.status_code}",
                provider_id=provider_id,
                status_code=response.status_code,
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise ModelGatewayError(
                "CREDENTIAL_INVALID",
                "credential revocation response is not JSON",
                provider_id=provider_id,
            ) from exc
        if not isinstance(body, dict) or not isinstance(body.get("revoked"), bool):
            raise ModelGatewayError(
                "CREDENTIAL_INVALID",
                "credential revocation response is invalid",
                provider_id=provider_id,
            )
        return body["revoked"]

    def revocation_checker(self, *, environment: str) -> CredentialRevocationChecker:
        """Return a provider-neutral checker bound to one deployment environment."""

        if not isinstance(environment, str) or not environment.strip():
            raise ValueError("CREDENTIAL_ENVIRONMENT_REQUIRED")

        def check(provider_id: str, lease_id: str) -> bool:
            return self.check_revocation(
                provider_id=provider_id, lease_id=lease_id, environment=environment
            )

        return check

    def _resolve_bootstrap_token(self, provider_id: str) -> str:
        try:
            token = self._bootstrap_token_provider()
        except Exception as exc:
            raise ModelGatewayError(
                "CREDENTIAL_UNAVAILABLE",
                f"credential token source failed ({type(exc).__name__})",
                provider_id=provider_id,
            ) from exc
        if not isinstance(token, str) or not token.strip():
            raise ModelGatewayError(
                "CREDENTIAL_MISSING", "credential bootstrap token is empty", provider_id=provider_id
            )
        return token

    def _request(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        payload: dict[str, str],
    ) -> httpx.Response:
        if self._client is not None:
            return self._client.request(
                method,
                f"{self._base_url}{path}",
                json=payload,
                headers=headers,
                timeout=self._timeout_seconds,
            )
        client_factory = (
            self._client_config.build_sync_client
            if self._client_config is not None
            else lambda: httpx.Client(timeout=self._timeout_seconds)
        )
        with client_factory() as client:
            return client.request(
                method,
                f"{self._base_url}{path}",
                json=payload,
                headers=headers,
            )


def _parse_expiry(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("expires_at must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("expires_at must be timezone-aware")
    return parsed.astimezone(UTC)


__all__ = [
    "CredentialLeaseMetadata",
    "CredentialLease",
    "CredentialRevocationChecker",
    "HttpProviderCredentialPort",
    "ProviderCredentialPort",
    "SecretManagerCredentialPort",
]
