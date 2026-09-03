"""Production composition root for human-controlled AI release deployment.

This module owns the application-level assembly of identity, token exchange,
deployment transport, receipt storage and metadata-only telemetry.  It does not
read environment variables or invent credentials.  Staging and production use
the same runtime; only explicitly injected URLs, token sources and stores vary.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import httpx

from backend.intelligence.evaluation.deployment import (
    DeploymentPhase,
    DeploymentPort,
    DeploymentReceipt,
    DeploymentReceiptStore,
    ReleaseDeploymentService,
)
from backend.intelligence.evaluation.http_deployment import HttpDeploymentPort
from backend.intelligence.evaluation.operator_identity import (
    RELEASE_DEPLOY_SCOPE,
    HttpOperatorIdentityPort,
    HttpOperatorTokenProvider,
    OperatorIdentity,
    OperatorIdentityError,
    OperatorIdentityPort,
    OperatorTokenSource,
)
from backend.intelligence.evaluation.release_catalog import ReleaseCandidate
from backend.intelligence.evaluation.release_control import ReleaseControlEvent
from backend.intelligence.observability import TelemetrySink
from backend.platform.security.mtls import MtlsClientConfig

PRODUCTION_RELEASE_ENVIRONMENTS = frozenset({"staging", "production"})


class ProductionReleaseWiringError(ValueError):
    """Raised when release dependencies are not safe to compose."""


@dataclass(frozen=True, slots=True)
class ProductionReleaseRuntime:
    """Release facade that derives the human actor from an external identity."""

    environment: str
    identity_port: OperatorIdentityPort
    deployment: ReleaseDeploymentService
    required_scope: str = RELEASE_DEPLOY_SCOPE

    def __post_init__(self) -> None:
        if self.environment not in PRODUCTION_RELEASE_ENVIRONMENTS:
            raise ProductionReleaseWiringError("RELEASE_RUNTIME_REQUIRES_STAGING_OR_PRODUCTION")
        if not callable(getattr(self.identity_port, "resolve", None)):
            raise ProductionReleaseWiringError("RELEASE_IDENTITY_PORT_REQUIRED")
        if not isinstance(self.deployment, ReleaseDeploymentService):
            raise ProductionReleaseWiringError("RELEASE_DEPLOYMENT_SERVICE_REQUIRED")
        if not isinstance(self.required_scope, str) or not self.required_scope.strip():
            raise ProductionReleaseWiringError("RELEASE_SCOPE_REQUIRED")

    async def apply(
        self,
        candidate: ReleaseCandidate,
        control: ReleaseControlEvent,
        *,
        phase: DeploymentPhase,
        rollout_percent: int,
        idempotency_key: str,
    ) -> DeploymentReceipt:
        identity = await self._resolve_identity(candidate.environment)
        return await self.deployment.apply(
            candidate,
            control,
            human_actor=identity.operator_id,
            phase=phase,
            rollout_percent=rollout_percent,
            idempotency_key=idempotency_key,
        )

    async def rollback(
        self,
        candidate: ReleaseCandidate,
        control: ReleaseControlEvent,
        *,
        idempotency_key: str,
    ) -> DeploymentReceipt:
        identity = await self._resolve_identity(candidate.environment)
        return await self.deployment.rollback(
            candidate,
            control,
            human_actor=identity.operator_id,
            idempotency_key=idempotency_key,
        )

    async def _resolve_identity(self, candidate_environment: str) -> OperatorIdentity:
        if candidate_environment != self.environment:
            raise ProductionReleaseWiringError("RELEASE_ENVIRONMENT_MISMATCH")
        try:
            identity = await self.identity_port.resolve(environment=self.environment)
        except OperatorIdentityError:
            raise
        except Exception as exc:
            raise OperatorIdentityError("IDENTITY_UNAVAILABLE") from exc
        if not isinstance(identity, OperatorIdentity):
            raise OperatorIdentityError("IDENTITY_RESPONSE_INVALID")
        if identity.environment != self.environment:
            raise OperatorIdentityError("IDENTITY_ENVIRONMENT_MISMATCH")
        if self.required_scope not in identity.scopes:
            raise OperatorIdentityError("TOKEN_OPERATOR_SCOPE_MISSING")
        return identity


def build_production_release_runtime(
    *,
    environment: str,
    identity_port: OperatorIdentityPort,
    deployment_port: DeploymentPort,
    receipt_store: DeploymentReceiptStore,
    telemetry_sink: TelemetrySink | None = None,
    required_scope: str = RELEASE_DEPLOY_SCOPE,
    clock: Callable[[], datetime] | None = None,
) -> ProductionReleaseRuntime:
    """Compose an already-approved, provider-neutral release runtime.

    All external dependencies are explicit.  In particular, this function does
    not read a URL, token, model credential or family data from process state.
    """

    if environment not in PRODUCTION_RELEASE_ENVIRONMENTS:
        raise ProductionReleaseWiringError("RELEASE_RUNTIME_REQUIRES_STAGING_OR_PRODUCTION")
    if not callable(getattr(identity_port, "resolve", None)):
        raise ProductionReleaseWiringError("RELEASE_IDENTITY_PORT_REQUIRED")
    if not callable(getattr(deployment_port, "apply", None)) or not callable(
        getattr(deployment_port, "rollback", None)
    ):
        raise ProductionReleaseWiringError("RELEASE_DEPLOYMENT_PORT_REQUIRED")
    if not callable(getattr(receipt_store, "get", None)) or not callable(
        getattr(receipt_store, "append", None)
    ):
        raise ProductionReleaseWiringError("RELEASE_RECEIPT_STORE_REQUIRED")
    return ProductionReleaseRuntime(
        environment=environment,
        identity_port=identity_port,
        deployment=ReleaseDeploymentService(
            deployment_port,
            receipt_store,
            clock=clock,
            telemetry_sink=telemetry_sink,
        ),
        required_scope=required_scope,
    )


def build_http_production_release_runtime(
    *,
    environment: str,
    identity_base_url: str,
    deployment_base_url: str,
    bootstrap_token_provider: OperatorTokenSource,
    audience: str,
    receipt_store: DeploymentReceiptStore,
    telemetry_sink: TelemetrySink | None = None,
    identity_client: httpx.AsyncClient | None = None,
    deployment_client: httpx.AsyncClient | None = None,
    identity_client_config: MtlsClientConfig | None = None,
    deployment_client_config: MtlsClientConfig | None = None,
    required_scope: str = RELEASE_DEPLOY_SCOPE,
    clock: Callable[[], datetime] | None = None,
) -> ProductionReleaseRuntime:
    """Compose the HTTP identity/token/deployment adapters without hidden config."""

    identity_port = HttpOperatorIdentityPort(
        base_url=identity_base_url,
        bootstrap_token_provider=bootstrap_token_provider,
        client=identity_client,
        client_config=identity_client_config,
    )
    token_provider = HttpOperatorTokenProvider(
        base_url=identity_base_url,
        identity_port=identity_port,
        bootstrap_token_provider=bootstrap_token_provider,
        audience=audience,
        environment=environment,
        required_scope=required_scope,
        client=identity_client,
        client_config=identity_client_config,
    )
    deployment_port = HttpDeploymentPort(
        base_url=deployment_base_url,
        token_provider=token_provider,
        client=deployment_client,
        client_config=deployment_client_config,
    )
    return build_production_release_runtime(
        environment=environment,
        identity_port=identity_port,
        deployment_port=deployment_port,
        receipt_store=receipt_store,
        telemetry_sink=telemetry_sink,
        required_scope=required_scope,
        clock=clock,
    )


__all__ = [
    "PRODUCTION_RELEASE_ENVIRONMENTS",
    "ProductionReleaseRuntime",
    "ProductionReleaseWiringError",
    "build_http_production_release_runtime",
    "build_production_release_runtime",
]
