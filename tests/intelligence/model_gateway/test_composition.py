from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import httpx
import pytest

from backend.intelligence.model_gateway.composition import (
    build_http_openai_compatible_gateway_from_registry,
    build_openai_compatible_gateway_from_registry,
    build_secret_manager_openai_compatible_gateway_from_registry,
)
from backend.intelligence.model_gateway.credentials import (
    CredentialLease,
    CredentialLeaseMetadata,
    HttpProviderCredentialPort,
)
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import (
    ProviderRecord,
    ProviderRegistry,
)


def _record(**overrides: object) -> ProviderRecord:
    values: dict[str, object] = {
        "provider_id": "vision-vendor",
        "vendor": "vision-vendor",
        "model": "vision-1",
        "model_version": "2026-01",
        "status": "PRODUCTION_APPROVED",
        "approved_environments": ("production",),
        "sub_delegates": False,
        "minor_data_allowed": True,
        "private_text_allowed": True,
        "security_assessment_ref": "security:approved",
        "processing_agreement_ref": "dpa:approved",
        "deletion_on_termination_committed": True,
        "credential_env_var": "VISION_API_KEY",
        "base_url_env_var": "VISION_BASE_URL",
    }
    values.update(overrides)
    return ProviderRecord(**values)  # type: ignore[arg-type]


def test_factory_builds_gateway_from_explicit_approved_provider() -> None:
    gateway = build_openai_compatible_gateway_from_registry(
        environment="production",
        provider_ids=("vision-vendor",),
        registry=ProviderRegistry([_record()]),
        env={
            "VISION_BASE_URL": "https://vision.example.invalid/v1",
            "VISION_API_KEY": "test-key",
        },
    )
    assert gateway.available_provider_ids() == ("vision-vendor",)
    assert gateway.registry.get("vision-vendor").model == "vision-1"


def test_factory_rejects_unapproved_record_before_reading_credentials() -> None:
    with pytest.raises(ModelGatewayError) as excinfo:
        build_openai_compatible_gateway_from_registry(
            environment="production",
            provider_ids=("vision-vendor",),
            registry=ProviderRegistry([_record(status="TECHNICALLY_VALIDATED")]),
            env={},
        )
    assert excinfo.value.kind == "POLICY_REJECTED"


def test_factory_rejects_missing_credentials_for_approved_record() -> None:
    with pytest.raises(ModelGatewayError) as excinfo:
        build_openai_compatible_gateway_from_registry(
            environment="production",
            provider_ids=("vision-vendor",),
            registry=ProviderRegistry([_record()]),
            env={},
        )
    assert excinfo.value.kind == "CREDENTIAL_MISSING"


def test_factory_requires_explicit_unique_provider_ids() -> None:
    registry = ProviderRegistry([_record()])
    with pytest.raises(ValueError, match="must not be empty"):
        build_openai_compatible_gateway_from_registry(
            environment="production", provider_ids=(), registry=registry
        )
    with pytest.raises(ValueError, match="duplicates"):
        build_openai_compatible_gateway_from_registry(
            environment="production",
            provider_ids=("vision-vendor", "vision-vendor"),
            registry=registry,
        )


def test_gateway_rejects_adapter_without_modality_capability_declaration() -> None:
    class UndeclaredAdapter:
        provider_id = "vision-vendor"

    gateway = ModelGateway(
        {"vision-vendor": UndeclaredAdapter()},
        environment="production",
        registry=ProviderRegistry([_record()]),
    )
    with pytest.raises(ModelGatewayError, match="no valid modality capability"):
        gateway.provider_supported_modalities("vision-vendor")


def test_factory_rejects_revocation_checker_without_credential_lease_port() -> None:
    with pytest.raises(ValueError, match="requires credential_port"):
        build_openai_compatible_gateway_from_registry(
            environment="production",
            provider_ids=("vision-vendor",),
            registry=ProviderRegistry([_record()]),
            credential_revocation_checker=lambda provider_id, lease_id: False,
            env={
                "VISION_BASE_URL": "https://vision.example.invalid/v1",
                "VISION_API_KEY": "test-key",
            },
        )


class _CredentialPort:
    def __init__(self, lease: CredentialLease) -> None:
        self.lease = lease
        self.calls: list[tuple[str, str]] = []

    def resolve(self, *, provider_id: str, environment: str) -> CredentialLease:
        self.calls.append((provider_id, environment))
        return self.lease


def test_factory_can_use_external_credential_lease_without_api_key_env() -> None:
    port = _CredentialPort(
        CredentialLease(
            provider_id="vision-vendor",
            api_key="lease-secret",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
            lease_id="lease-1",
        )
    )
    gateway = build_openai_compatible_gateway_from_registry(
        environment="production",
        provider_ids=("vision-vendor",),
        registry=ProviderRegistry([_record(credential_env_var=None)]),
        env={"VISION_BASE_URL": "https://vision.example.invalid/v1"},
        credential_port=port,
    )
    assert gateway.available_provider_ids() == ("vision-vendor",)
    assert port.calls == [("vision-vendor", "production")]


def test_credential_lease_rejects_expired_secret_without_exposing_it() -> None:
    with pytest.raises(ModelGatewayError) as excinfo:
        CredentialLease(
            provider_id="vision-vendor",
            api_key="super-secret",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
            lease_id="lease-expired",
        )
    assert "super-secret" not in repr(excinfo.value)


def test_credential_port_failures_are_stable_and_do_not_expose_exception_text() -> None:
    class FailingPort:
        def resolve(self, *, provider_id: str, environment: str) -> CredentialLease:
            raise RuntimeError("secret-manager response contained super-secret")

    with pytest.raises(ModelGatewayError) as excinfo:
        build_openai_compatible_gateway_from_registry(
            environment="production",
            provider_ids=("vision-vendor",),
            registry=ProviderRegistry([_record(credential_env_var=None)]),
            env={"VISION_BASE_URL": "https://vision.example.invalid/v1"},
            credential_port=FailingPort(),
        )
    assert excinfo.value.kind == "CREDENTIAL_UNAVAILABLE"
    assert "super-secret" not in str(excinfo.value)


def test_http_composition_factory_uses_explicit_credential_service() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/provider-credentials/leases"
        return httpx.Response(
            200,
            json={
                "provider_id": "vision-vendor",
                "api_key": "lease-secret",
                "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
                "lease_id": "lease-3",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        gateway = build_http_openai_compatible_gateway_from_registry(
            environment="production",
            provider_ids=("vision-vendor",),
            registry=ProviderRegistry([_record(credential_env_var=None)]),
            credential_service_base_url="https://secrets.example.invalid",
            bootstrap_token_provider=lambda: "bootstrap-token",
            credential_audience="aifamily-model-gateway",
            env={"VISION_BASE_URL": "https://vision.example.invalid/v1"},
            credential_client=client,
        )

    assert gateway.available_provider_ids() == ("vision-vendor",)


def test_http_composition_can_bind_external_revocation_checker() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "provider_id": "vision-vendor",
                "api_key": "lease-secret",
                "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
                "lease_id": "lease-4",
            },
        )

    def checker(provider_id: str, lease_id: str) -> bool:
        return False

    with httpx.Client(transport=httpx.MockTransport(handler)) as client, patch.object(
        HttpProviderCredentialPort, "revocation_checker", return_value=checker
    ) as factory:
        gateway = build_http_openai_compatible_gateway_from_registry(
            environment="production",
            provider_ids=("vision-vendor",),
            registry=ProviderRegistry([_record(credential_env_var=None)]),
            credential_service_base_url="https://secrets.example.invalid",
            bootstrap_token_provider=lambda: "bootstrap-token",
            credential_audience="aifamily-model-gateway",
            env={"VISION_BASE_URL": "https://vision.example.invalid/v1"},
            credential_client=client,
            check_credential_revocation=True,
        )

    assert gateway.available_provider_ids() == ("vision-vendor",)
    factory.assert_called_once_with(environment="production")


def test_secret_manager_composition_factory_keeps_secret_outside_gateway_configuration() -> None:
    gateway = build_secret_manager_openai_compatible_gateway_from_registry(
        environment="production",
        provider_ids=("vision-vendor",),
        registry=ProviderRegistry([_record(credential_env_var=None)]),
        secret_reference_resolver=lambda provider_id, environment: (
            f"kv/{environment}/{provider_id}"
        ),
        metadata_resolver=lambda provider_id, _environment: CredentialLeaseMetadata(
            provider_id=provider_id,
            lease_id="lease-sm",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        ),
        secret_reader=lambda _reference: "lease-secret",
        env={"VISION_BASE_URL": "https://vision.example.invalid/v1"},
    )

    assert gateway.available_provider_ids() == ("vision-vendor",)
