"""Governed production construction for OpenAI-compatible model adapters.

This is the only convenience factory that turns a ``ProviderRegistry`` record
into a real network adapter.  It deliberately requires an explicit provider
list and rejects records that are not callable in the requested environment;
the request-time ``ProviderRegistry.admit`` check in ``ModelGateway`` remains
the authoritative data-class gate.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping

import httpx

from backend.intelligence.model_gateway.attempts import AttemptSink
from backend.intelligence.model_gateway.credentials import (
    CredentialLease,
    CredentialLeaseMetadata,
    CredentialRevocationChecker,
    HttpProviderCredentialPort,
    ProviderCredentialPort,
    SecretManagerCredentialPort,
)
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.gateway import ModelGateway, build_gateway
from backend.intelligence.model_gateway.provider_registry import (
    CALLABLE_STATUSES,
    ProviderRecord,
    ProviderRegistry,
)
from backend.intelligence.model_gateway.providers.base import ProviderAdapter
from backend.intelligence.model_gateway.providers.openai_compatible import (
    build_openai_compatible_provider,
    build_openai_compatible_provider_from_lease,
)
from backend.intelligence.observability import TelemetrySink
from backend.intelligence.safety.persistence import SafetyDecisionSink
from backend.intelligence.safety.runtime import SafetyRuntime
from backend.platform.security.mtls import MtlsClientConfig

ClientFactory = Callable[[ProviderRecord], httpx.AsyncClient | None]
CredentialClientFactory = Callable[[], httpx.Client | None]


def build_openai_compatible_gateway_from_registry(
    *,
    environment: str,
    provider_ids: tuple[str, ...],
    registry: ProviderRegistry,
    env: Mapping[str, str] | None = None,
    client_factory: ClientFactory | None = None,
    attempt_sink: AttemptSink | None = None,
    safety_runtime: SafetyRuntime | None = None,
    safety_sink: SafetyDecisionSink | None = None,
    telemetry_sink: TelemetrySink | None = None,
    credential_port: ProviderCredentialPort | None = None,
    credential_revocation_checker: CredentialRevocationChecker | None = None,
) -> ModelGateway:
    """Build one Gateway from explicitly approved registry records.

    ``provider_ids`` is intentionally not inferred from environment variables.
    A deployment must state which models it intends to expose, making startup
    review and rollback deterministic.  Records with ``TECHNICALLY_VALIDATED``
    or ``REGISTERED`` status fail before credentials are read.
    """

    if not isinstance(environment, str) or not environment.strip():
        raise ValueError("environment is required")
    if not provider_ids:
        raise ValueError("provider_ids must not be empty")
    if len(set(provider_ids)) != len(provider_ids):
        raise ValueError("provider_ids must not contain duplicates")
    if not isinstance(registry, ProviderRegistry):
        raise TypeError("registry must be a ProviderRegistry")
    if client_factory is not None and not callable(client_factory):
        raise TypeError("client_factory must be callable")
    if credential_revocation_checker is not None and credential_port is None:
        raise ValueError("credential_revocation_checker requires credential_port")

    adapters: dict[str, ProviderAdapter] = {}
    for provider_id in provider_ids:
        record = registry.get(provider_id)
        _assert_startup_admitted(record, environment)
        if not record.base_url_env_var:
            raise ModelGatewayError(
                "CREDENTIAL_MISSING",
                f"provider {provider_id!r} has no base_url environment binding",
                provider_id=provider_id,
            )
        client = client_factory(record) if client_factory is not None else None
        source = os.environ if env is None else env
        base_url = source.get(record.base_url_env_var, "")
        if not base_url:
            raise ModelGatewayError(
                "CREDENTIAL_MISSING",
                f"missing environment variable {record.base_url_env_var!r} for "
                f"provider {provider_id!r}",
                provider_id=provider_id,
            )
        if credential_port is not None:
            try:
                lease = credential_port.resolve(provider_id=provider_id, environment=environment)
            except ModelGatewayError:
                raise
            except Exception as exc:
                raise ModelGatewayError(
                    "CREDENTIAL_UNAVAILABLE",
                    f"credential port failed ({type(exc).__name__})",
                    provider_id=provider_id,
                ) from exc
            if not isinstance(lease, CredentialLease):
                raise ModelGatewayError(
                    "CREDENTIAL_INVALID",
                    f"credential port returned an invalid lease for provider {provider_id!r}",
                    provider_id=provider_id,
                )
            adapters[provider_id] = build_openai_compatible_provider_from_lease(
                provider_id=record.provider_id,
                model=record.model,
                base_url=base_url,
                lease=lease,
                client=client,
                revocation_checker=credential_revocation_checker,
            )
        else:
            if not record.credential_env_var:
                raise ModelGatewayError(
                    "CREDENTIAL_MISSING",
                    f"provider {provider_id!r} has no credential environment binding",
                    provider_id=provider_id,
                )
            adapters[provider_id] = build_openai_compatible_provider(
                provider_id=record.provider_id,
                model=record.model,
                base_url_env_var=record.base_url_env_var,
                credential_env_var=record.credential_env_var,
                env=dict(env) if env is not None else None,
                client=client,
            )
    return build_gateway(
        environment=environment,
        providers=adapters,
        registry=registry,
        attempt_sink=attempt_sink,
        safety_runtime=safety_runtime,
        safety_sink=safety_sink,
        telemetry_sink=telemetry_sink,
    )


def build_http_openai_compatible_gateway_from_registry(
    *,
    environment: str,
    provider_ids: tuple[str, ...],
    registry: ProviderRegistry,
    credential_service_base_url: str,
    bootstrap_token_provider: Callable[[], str],
    credential_audience: str,
    env: Mapping[str, str] | None = None,
    client_factory: ClientFactory | None = None,
    credential_client: httpx.Client | None = None,
    credential_client_config: MtlsClientConfig | None = None,
    check_credential_revocation: bool = False,
    attempt_sink: AttemptSink | None = None,
    safety_runtime: SafetyRuntime | None = None,
    safety_sink: SafetyDecisionSink | None = None,
    telemetry_sink: TelemetrySink | None = None,
) -> ModelGateway:
    """Build a Gateway whose provider secrets come from an external HTTP service.

    ``credential_client`` is intentionally injectable so a deployment can
    configure mTLS, CA verification and connection pooling in its composition
    root.  The helper never reads an API-key environment variable; the registry
    still supplies non-secret base URLs for provider adapters.
    """

    credential_port = HttpProviderCredentialPort(
        base_url=credential_service_base_url,
        bootstrap_token_provider=bootstrap_token_provider,
        audience=credential_audience,
        client=credential_client,
        client_config=credential_client_config,
    )
    if not isinstance(check_credential_revocation, bool):
        raise ValueError("check_credential_revocation must be a bool")
    return build_openai_compatible_gateway_from_registry(
        environment=environment,
        provider_ids=provider_ids,
        registry=registry,
        env=env,
        client_factory=client_factory,
        attempt_sink=attempt_sink,
        safety_runtime=safety_runtime,
        safety_sink=safety_sink,
        telemetry_sink=telemetry_sink,
        credential_port=credential_port,
        credential_revocation_checker=(
            credential_port.revocation_checker(environment=environment)
            if check_credential_revocation
            else None
        ),
    )


def build_secret_manager_openai_compatible_gateway_from_registry(
    *,
    environment: str,
    provider_ids: tuple[str, ...],
    registry: ProviderRegistry,
    secret_reference_resolver: Callable[[str, str], str],
    metadata_resolver: Callable[[str, str], CredentialLeaseMetadata],
    secret_reader: Callable[[str], str],
    env: Mapping[str, str] | None = None,
    client_factory: ClientFactory | None = None,
    credential_revocation_checker: CredentialRevocationChecker | None = None,
    attempt_sink: AttemptSink | None = None,
    safety_runtime: SafetyRuntime | None = None,
    safety_sink: SafetyDecisionSink | None = None,
    telemetry_sink: TelemetrySink | None = None,
) -> ModelGateway:
    """Build a Gateway from provider-neutral KMS/Secret Manager callbacks.

    The callbacks are supplied by the deployment composition root.  This
    helper owns no SDK client or secret storage and therefore remains usable in
    dev/test with deterministic fakes while preserving the production path.
    """

    credential_port = SecretManagerCredentialPort(
        secret_reference_resolver=secret_reference_resolver,
        metadata_resolver=metadata_resolver,
        secret_reader=secret_reader,
    )
    return build_openai_compatible_gateway_from_registry(
        environment=environment,
        provider_ids=provider_ids,
        registry=registry,
        env=env,
        client_factory=client_factory,
        attempt_sink=attempt_sink,
        safety_runtime=safety_runtime,
        safety_sink=safety_sink,
        telemetry_sink=telemetry_sink,
        credential_port=credential_port,
        credential_revocation_checker=credential_revocation_checker,
    )


def _assert_startup_admitted(record: ProviderRecord, environment: str) -> None:
    if record.status not in CALLABLE_STATUSES:
        raise ModelGatewayError(
            "POLICY_REJECTED",
            f"provider {record.provider_id!r} has status {record.status!r}; "
            f"startup requires one of {sorted(CALLABLE_STATUSES)}",
            provider_id=record.provider_id,
        )
    if environment not in record.approved_environments:
        raise ModelGatewayError(
            "POLICY_REJECTED",
            f"provider {record.provider_id!r} is not approved for environment "
            f"{environment!r}",
            provider_id=record.provider_id,
        )


__all__ = [
    "ClientFactory",
    "CredentialClientFactory",
    "build_http_openai_compatible_gateway_from_registry",
    "build_secret_manager_openai_compatible_gateway_from_registry",
    "build_openai_compatible_gateway_from_registry",
]
