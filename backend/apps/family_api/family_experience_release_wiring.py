"""Environment-parity composition for governed family-experience releases."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import httpx

from backend.intelligence.evaluation.deployment import (
    DeploymentPhase,
    DeploymentReceipt,
    DeploymentReceiptStore,
)
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
from backend.intelligence.experience.http_release_bundle_deployment import (
    HttpFamilyExperienceDeploymentPort,
)
from backend.intelligence.experience.release_bundle_deployment import (
    FamilyExperienceDeploymentPort,
    FamilyExperienceReleaseDeploymentService,
)
from backend.intelligence.experience.release_bundle_persistence import (
    FamilyExperienceReleaseBundleReader,
)
from backend.intelligence.observability import TelemetrySink
from backend.platform.security.mtls import MtlsClientConfig

FAMILY_EXPERIENCE_RELEASE_ENVIRONMENTS = frozenset(
    {"development", "test", "staging", "production"}
)


class FamilyExperienceReleaseWiringError(ValueError):
    """Raised when the bundle-aware release runtime cannot be composed safely."""


@dataclass(frozen=True, slots=True)
class FamilyExperienceReleaseRuntime:
    environment: str
    identity_port: OperatorIdentityPort
    deployment: FamilyExperienceReleaseDeploymentService
    required_scope: str = RELEASE_DEPLOY_SCOPE

    def __post_init__(self) -> None:
        if self.environment not in FAMILY_EXPERIENCE_RELEASE_ENVIRONMENTS:
            raise FamilyExperienceReleaseWiringError("RELEASE_ENVIRONMENT_INVALID")
        if not callable(getattr(self.identity_port, "resolve", None)):
            raise FamilyExperienceReleaseWiringError("RELEASE_IDENTITY_PORT_REQUIRED")
        if not isinstance(self.deployment, FamilyExperienceReleaseDeploymentService):
            raise FamilyExperienceReleaseWiringError("BUNDLE_DEPLOYMENT_SERVICE_REQUIRED")
        if not isinstance(self.required_scope, str) or not self.required_scope.strip():
            raise FamilyExperienceReleaseWiringError("RELEASE_SCOPE_REQUIRED")

    async def apply(
        self,
        candidate: ReleaseCandidate,
        control: ReleaseControlEvent,
        *,
        phase: DeploymentPhase,
        rollout_percent: int,
        idempotency_key: str,
    ) -> DeploymentReceipt:
        identity = await self._identity(candidate.environment)
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
        identity = await self._identity(candidate.environment)
        return await self.deployment.rollback(
            candidate,
            control,
            human_actor=identity.operator_id,
            idempotency_key=idempotency_key,
        )

    async def _identity(self, candidate_environment: str) -> OperatorIdentity:
        if candidate_environment != self.environment:
            raise FamilyExperienceReleaseWiringError("RELEASE_ENVIRONMENT_MISMATCH")
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


def build_family_experience_release_runtime(
    *,
    environment: str,
    identity_port: OperatorIdentityPort,
    deployment_port: FamilyExperienceDeploymentPort,
    bundle_store: FamilyExperienceReleaseBundleReader,
    receipt_store: DeploymentReceiptStore,
    telemetry_sink: TelemetrySink | None = None,
    required_scope: str = RELEASE_DEPLOY_SCOPE,
    clock: Callable[[], datetime] | None = None,
) -> FamilyExperienceReleaseRuntime:
    """Compose the identical release feature path for every environment."""

    if environment not in FAMILY_EXPERIENCE_RELEASE_ENVIRONMENTS:
        raise FamilyExperienceReleaseWiringError("RELEASE_ENVIRONMENT_INVALID")
    if not isinstance(required_scope, str) or not required_scope.strip():
        raise FamilyExperienceReleaseWiringError("RELEASE_SCOPE_REQUIRED")
    for dependency, methods, code in (
        (identity_port, ("resolve",), "RELEASE_IDENTITY_PORT_REQUIRED"),
        (deployment_port, ("apply", "rollback"), "BUNDLE_DEPLOYMENT_PORT_REQUIRED"),
        (bundle_store, ("get_for_candidate",), "RELEASE_BUNDLE_STORE_REQUIRED"),
        (receipt_store, ("get", "append"), "RELEASE_RECEIPT_STORE_REQUIRED"),
    ):
        if any(not callable(getattr(dependency, method, None)) for method in methods):
            raise FamilyExperienceReleaseWiringError(code)
    return FamilyExperienceReleaseRuntime(
        environment=environment,
        identity_port=identity_port,
        deployment=FamilyExperienceReleaseDeploymentService(
            port=deployment_port,
            bundles=bundle_store,
            receipts=receipt_store,
            clock=clock,
            telemetry_sink=telemetry_sink,
        ),
        required_scope=required_scope,
    )


def build_http_family_experience_release_runtime(
    *,
    environment: str,
    identity_base_url: str,
    deployment_base_url: str,
    bootstrap_token_provider: OperatorTokenSource,
    audience: str,
    bundle_store: FamilyExperienceReleaseBundleReader,
    receipt_store: DeploymentReceiptStore,
    telemetry_sink: TelemetrySink | None = None,
    identity_client: httpx.AsyncClient | None = None,
    deployment_client: httpx.AsyncClient | None = None,
    identity_client_config: MtlsClientConfig | None = None,
    deployment_client_config: MtlsClientConfig | None = None,
    required_scope: str = RELEASE_DEPLOY_SCOPE,
    clock: Callable[[], datetime] | None = None,
) -> FamilyExperienceReleaseRuntime:
    """Compose identical HTTP behavior; only injected infrastructure may differ."""

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
    deployment_port = HttpFamilyExperienceDeploymentPort(
        base_url=deployment_base_url,
        token_provider=token_provider,
        client=deployment_client,
        client_config=deployment_client_config,
    )
    return build_family_experience_release_runtime(
        environment=environment,
        identity_port=identity_port,
        deployment_port=deployment_port,
        bundle_store=bundle_store,
        receipt_store=receipt_store,
        telemetry_sink=telemetry_sink,
        required_scope=required_scope,
        clock=clock,
    )


__all__ = [
    "FAMILY_EXPERIENCE_RELEASE_ENVIRONMENTS",
    "FamilyExperienceReleaseRuntime",
    "FamilyExperienceReleaseWiringError",
    "build_family_experience_release_runtime",
    "build_http_family_experience_release_runtime",
]
