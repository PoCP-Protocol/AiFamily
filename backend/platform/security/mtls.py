"""Explicit mTLS client construction for platform-owned service boundaries.

The platform never discovers certificates from environment variables and never
logs their paths or contents.  A deployment composition root supplies this
configuration and owns the returned client's lifecycle.  Keeping the factory
here lets identity, key-service and deployment adapters share one transport
policy without coupling domains to TLS details.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import httpx


class MtlsConfigurationError(ValueError):
    """Raised when an mTLS transport cannot be safely constructed."""


@dataclass(frozen=True, slots=True)
class MtlsClientConfig:
    """Filesystem references for a client certificate and trusted CA bundle."""

    ca_bundle: str = field(repr=False)
    client_cert: str = field(repr=False)
    client_key: str = field(repr=False)
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        for name, value in (
            ("ca_bundle", self.ca_bundle),
            ("client_cert", self.client_cert),
            ("client_key", self.client_key),
        ):
            if not isinstance(value, str) or not value.strip():
                raise MtlsConfigurationError(f"MTLS_{name.upper()}_REQUIRED")
            if not Path(value).is_absolute():
                raise MtlsConfigurationError(f"MTLS_{name.upper()}_MUST_BE_ABSOLUTE")
            if not Path(value).is_file():
                raise MtlsConfigurationError(f"MTLS_{name.upper()}_NOT_FOUND")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or self.timeout_seconds <= 0
        ):
            raise MtlsConfigurationError("MTLS_TIMEOUT_MUST_BE_POSITIVE")

    def build_async_client(self) -> httpx.AsyncClient:
        """Create an async client; the caller must close it after use."""

        return httpx.AsyncClient(
            verify=self.ca_bundle,
            cert=(self.client_cert, self.client_key),
            timeout=self.timeout_seconds,
        )

    def build_sync_client(self) -> httpx.Client:
        """Create a sync client; the caller must close it after use."""

        return httpx.Client(
            verify=self.ca_bundle,
            cert=(self.client_cert, self.client_key),
            timeout=self.timeout_seconds,
        )


__all__ = ["MtlsClientConfig", "MtlsConfigurationError"]
