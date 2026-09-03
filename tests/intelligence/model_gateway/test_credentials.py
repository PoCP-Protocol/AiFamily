import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from backend.intelligence.model_gateway.credentials import (
    CredentialLease,
    CredentialLeaseMetadata,
    HttpProviderCredentialPort,
    SecretManagerCredentialPort,
)
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.platform.security.mtls import MtlsClientConfig


def test_http_credential_port_returns_scoped_expiring_lease() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "provider_id": "vision-vendor",
                "api_key": "secret-from-kms",
                "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
                "lease_id": "lease-1",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        port = HttpProviderCredentialPort(
            base_url="https://secrets.example.invalid",
            bootstrap_token_provider=lambda: "bootstrap-token",
            audience="aifamily-model-gateway",
            client=client,
        )
        lease = port.resolve(provider_id="vision-vendor", environment="production")

    assert lease.provider_id == "vision-vendor"
    assert lease.lease_id == "lease-1"
    assert "secret-from-kms" not in repr(lease)
    assert calls[0].url.path == "/v1/provider-credentials/leases"
    assert calls[0].headers["authorization"] == "Bearer bootstrap-token"
    assert calls[0].headers["x-ai-environment"] == "production"


def test_http_credential_port_rejects_provider_mismatch_without_secret() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "provider_id": "other-vendor",
                "api_key": "secret-from-kms",
                "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
                "lease_id": "lease-2",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        port = HttpProviderCredentialPort(
            base_url="https://secrets.example.invalid",
            bootstrap_token_provider=lambda: "bootstrap-token",
            audience="aifamily-model-gateway",
            client=client,
        )
        with pytest.raises(ModelGatewayError) as excinfo:
            port.resolve(provider_id="vision-vendor", environment="production")

    assert excinfo.value.kind == "CREDENTIAL_PROVIDER_MISMATCH"
    assert "secret-from-kms" not in str(excinfo.value)


def test_http_credential_port_rejects_revoked_lease() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "provider_id": "vision-vendor",
                "api_key": "secret-from-kms",
                "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
                "lease_id": "lease-revoked",
                "revoked": True,
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        port = HttpProviderCredentialPort(
            base_url="https://secrets.example.invalid",
            bootstrap_token_provider=lambda: "bootstrap-token",
            audience="aifamily-model-gateway",
            client=client,
        )
        with pytest.raises(ModelGatewayError) as excinfo:
            port.resolve(provider_id="vision-vendor", environment="production")

    assert excinfo.value.kind == "CREDENTIAL_REVOKED"
    assert "secret-from-kms" not in str(excinfo.value)


def test_http_credential_port_maps_platform_and_token_failures() -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(403))
    ) as client:
        port = HttpProviderCredentialPort(
            base_url="https://secrets.example.invalid",
            bootstrap_token_provider=lambda: "bootstrap-token",
            audience="aifamily-model-gateway",
            client=client,
        )
        with pytest.raises(ModelGatewayError) as excinfo:
            port.resolve(provider_id="vision-vendor", environment="production")
    assert excinfo.value.kind == "CREDENTIAL_PLATFORM_REJECTED"

    failing = HttpProviderCredentialPort(
        base_url="https://secrets.example.invalid",
        bootstrap_token_provider=lambda: (_ for _ in ()).throw(
            RuntimeError("secret-manager body must not leak")
        ),
        audience="aifamily-model-gateway",
    )
    with pytest.raises(ModelGatewayError) as excinfo:
        failing.resolve(provider_id="vision-vendor", environment="production")
    assert excinfo.value.kind == "CREDENTIAL_UNAVAILABLE"
    assert "secret-manager body" not in str(excinfo.value)


def test_http_credential_port_requires_positive_timeout() -> None:
    with pytest.raises(ValueError, match="TIMEOUT_MUST_BE_POSITIVE"):
        HttpProviderCredentialPort(
            base_url="https://secrets.example.invalid",
            bootstrap_token_provider=lambda: "bootstrap-token",
            audience="aifamily-model-gateway",
            timeout_seconds=0,
        )


def test_http_credential_port_rejects_client_and_mtls_config_together(tmp_path: Path) -> None:
    cert_paths = []
    for name in ("ca.pem", "client.pem", "client.key"):
        path = tmp_path / name
        path.write_text("placeholder", encoding="utf-8")
        cert_paths.append(str(path))

    with pytest.raises(ValueError, match="MTLS_CLIENT_CONFLICT"):
        HttpProviderCredentialPort(
            base_url="https://secrets.example.invalid",
            bootstrap_token_provider=lambda: "bootstrap-token",
            audience="aifamily-model-gateway",
            client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200))),
            client_config=MtlsClientConfig(*cert_paths),
        )


def test_http_credential_port_can_construct_a_temporary_mtls_client(tmp_path: Path) -> None:
    cert_paths = []
    for name in ("ca.pem", "client.pem", "client.key"):
        path = tmp_path / name
        path.write_text("placeholder", encoding="utf-8")
        cert_paths.append(str(path))
    config = MtlsClientConfig(*cert_paths)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "provider_id": "vision-vendor",
                "api_key": "secret-from-kms",
                "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
                "lease_id": "lease-mtls",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    port = HttpProviderCredentialPort(
        base_url="https://secrets.example.invalid",
        bootstrap_token_provider=lambda: "bootstrap-token",
        audience="aifamily-model-gateway",
        client_config=config,
    )
    with patch(
        "backend.platform.security.mtls.MtlsClientConfig.build_sync_client",
        return_value=client,
    ):
        lease = port.resolve(provider_id="vision-vendor", environment="production")

    assert lease.lease_id == "lease-mtls"


def test_http_credential_port_reads_revocation_status_without_secret() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"revoked": True})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        port = HttpProviderCredentialPort(
            base_url="https://secrets.example.invalid",
            bootstrap_token_provider=lambda: "bootstrap-token",
            audience="aifamily-model-gateway",
            client=client,
        )
        assert port.check_revocation(
            provider_id="vision-vendor", lease_id="lease-1", environment="production"
        ) is True

    assert calls[0].url.path == "/v1/provider-credentials/leases/revocation-status"
    assert calls[0].headers["x-ai-environment"] == "production"
    assert json.loads(calls[0].content) == {
        "provider_id": "vision-vendor",
        "lease_id": "lease-1",
        "environment": "production",
        "audience": "aifamily-model-gateway",
    }


def test_http_credential_port_rejects_invalid_revocation_response() -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"revoked": 1}))
    ) as client:
        port = HttpProviderCredentialPort(
            base_url="https://secrets.example.invalid",
            bootstrap_token_provider=lambda: "bootstrap-token",
            audience="aifamily-model-gateway",
            client=client,
        )
        with pytest.raises(ModelGatewayError) as excinfo:
            port.check_revocation(
                provider_id="vision-vendor", lease_id="lease-1", environment="production"
            )
    assert excinfo.value.kind == "CREDENTIAL_INVALID"


def test_secret_manager_credential_port_reads_secret_after_metadata_and_hides_value() -> None:
    calls: list[tuple[str, str]] = []

    def metadata(provider_id: str, environment: str) -> CredentialLeaseMetadata:
        calls.append(("metadata", f"{provider_id}:{environment}"))
        return CredentialLeaseMetadata(
            provider_id=provider_id,
            lease_id="lease-secret-manager",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )

    def read(reference: str) -> str:
        calls.append(("secret", reference))
        return "secret-from-kms"

    port = SecretManagerCredentialPort(
        secret_reference_resolver=lambda provider_id, environment: (
            f"kv/{environment}/{provider_id}"
        ),
        metadata_resolver=metadata,
        secret_reader=read,
    )
    lease = port.resolve(provider_id="vision-vendor", environment="production")

    assert lease.lease_id == "lease-secret-manager"
    assert "secret-from-kms" not in repr(lease)
    assert calls == [
        ("metadata", "vision-vendor:production"),
        ("secret", "kv/production/vision-vendor"),
    ]


def test_secret_manager_port_rejects_provider_mismatch_before_secret_read() -> None:
    read_called = False

    def read(_reference: str) -> str:
        nonlocal read_called
        read_called = True
        return "secret"

    port = SecretManagerCredentialPort(
        secret_reference_resolver=lambda _provider_id, _environment: "kv/ref",
        metadata_resolver=lambda _provider_id, _environment: CredentialLeaseMetadata(
            provider_id="other-vendor",
            lease_id="lease-mismatch",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        ),
        secret_reader=read,
    )

    with pytest.raises(ModelGatewayError) as excinfo:
        port.resolve(provider_id="vision-vendor", environment="production")

    assert excinfo.value.kind == "CREDENTIAL_PROVIDER_MISMATCH"
    assert read_called is False


@pytest.mark.parametrize(
    ("revoked", "expires_at", "expected_kind"),
    [
        (True, datetime.now(UTC) + timedelta(minutes=5), "CREDENTIAL_REVOKED"),
        (False, datetime.now(UTC) - timedelta(seconds=1), "CREDENTIAL_EXPIRED"),
    ],
)
def test_secret_manager_port_rejects_revoked_or_expired_metadata_before_secret_read(
    revoked: bool,
    expires_at: datetime,
    expected_kind: str,
) -> None:
    read_called = False

    def read(_reference: str) -> str:
        nonlocal read_called
        read_called = True
        return "secret"

    port = SecretManagerCredentialPort(
        secret_reference_resolver=lambda _provider_id, _environment: "kv/ref",
        metadata_resolver=lambda provider_id, _environment: CredentialLeaseMetadata(
            provider_id=provider_id,
            lease_id="lease-invalid-state",
            expires_at=expires_at,
            revoked=revoked,
        ),
        secret_reader=read,
    )

    with pytest.raises(ModelGatewayError) as excinfo:
        port.resolve(provider_id="vision-vendor", environment="production")

    assert excinfo.value.kind == expected_kind
    assert read_called is False


def test_secret_manager_credential_port_maps_secret_reader_failure_without_leak() -> None:
    port = SecretManagerCredentialPort(
        secret_reference_resolver=lambda _provider_id, _environment: "kv/ref",
        metadata_resolver=lambda provider_id, _environment: CredentialLeaseMetadata(
            provider_id=provider_id,
            lease_id="lease-1",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        ),
        secret_reader=lambda _reference: (_ for _ in ()).throw(
            RuntimeError("secret payload must not leak")
        ),
    )

    with pytest.raises(ModelGatewayError) as excinfo:
        port.resolve(provider_id="vision-vendor", environment="production")

    assert excinfo.value.kind == "CREDENTIAL_UNAVAILABLE"
    assert "secret payload" not in str(excinfo.value)


def test_credential_lease_rejects_non_string_secret_and_non_datetime_expiry() -> None:
    with pytest.raises(ModelGatewayError) as secret_error:
        CredentialLease(
            provider_id="vision-vendor",
            api_key=b"secret",  # type: ignore[arg-type]
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
            lease_id="lease-invalid-secret",
        )
    assert secret_error.value.kind == "CREDENTIAL_MISSING"

    with pytest.raises(ValueError, match="must be a datetime"):
        CredentialLease(
            provider_id="vision-vendor",
            api_key="secret",
            expires_at="tomorrow",  # type: ignore[arg-type]
            lease_id="lease-invalid-expiry",
        )
