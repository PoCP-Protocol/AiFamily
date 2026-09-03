"""Environment-parity composition for atomic family-experience ReleaseSets."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.intelligence.evaluation.operator_identity import (
    RELEASE_DEPLOY_SCOPE,
    OperatorIdentity,
    OperatorIdentityError,
    OperatorIdentityPort,
)
from backend.intelligence.experience.http_release_set_deployment import (
    HttpReleaseSetDeploymentPort,
    ReleaseSetTokenProvider,
)
from backend.intelligence.experience.release_set import FamilyExperienceReleaseSet
from backend.intelligence.experience.release_set_control import (
    SessionPerCallReleaseSetControlReader,
)
from backend.intelligence.experience.release_set_deployment import (
    FamilyExperienceReleaseSetDeploymentService,
    ReleaseSetDeploymentAuthorization,
    ReleaseSetDeploymentPhase,
    ReleaseSetDeploymentPort,
    ReleaseSetDeploymentReceipt,
    SessionPerCallReleaseSetDeploymentStore,
    SqlAlchemyReleaseSetTransitionCoordinator,
)
from backend.intelligence.experience.release_set_persistence import (
    SessionPerCallFamilyExperienceReleaseSetReader,
)
from backend.intelligence.experience.release_set_reconciliation import (
    ReleaseSetReconciliationScheduler,
)
from backend.platform.security.mtls import MtlsClientConfig

RELEASE_SET_ENVIRONMENTS = frozenset(
    {"development", "test", "staging", "production"}
)


class FamilyExperienceReleaseSetWiringError(ValueError):
    """The atomic release runtime is not safe to compose."""


@dataclass(frozen=True, slots=True)
class FamilyExperienceReleaseSetRuntime:
    environment: str
    identity_port: OperatorIdentityPort
    deployment: FamilyExperienceReleaseSetDeploymentService
    required_scope: str = RELEASE_DEPLOY_SCOPE

    async def apply(
        self,
        release_set: FamilyExperienceReleaseSet,
        *,
        control_id: str,
        phase: ReleaseSetDeploymentPhase,
        rollout_percent: int,
        idempotency_key: str,
    ) -> ReleaseSetDeploymentReceipt:
        identity = await self._identity(release_set.environment)
        return await self.deployment.apply(
            release_set,
            ReleaseSetDeploymentAuthorization(control_id, identity.operator_id),
            phase=phase,
            rollout_percent=rollout_percent,
            idempotency_key=idempotency_key,
        )

    async def rollback(
        self,
        source: FamilyExperienceReleaseSet,
        target: FamilyExperienceReleaseSet,
        *,
        control_id: str,
        idempotency_key: str,
    ) -> ReleaseSetDeploymentReceipt:
        identity = await self._identity(source.environment)
        return await self.deployment.rollback(
            source,
            target,
            ReleaseSetDeploymentAuthorization(control_id, identity.operator_id),
            idempotency_key=idempotency_key,
        )

    async def _identity(self, release_environment: str) -> OperatorIdentity:
        if release_environment != self.environment:
            raise FamilyExperienceReleaseSetWiringError(
                "RELEASE_SET_ENVIRONMENT_MISMATCH"
            )
        try:
            identity = await self.identity_port.resolve(environment=self.environment)
        except OperatorIdentityError:
            raise
        except Exception as error:
            raise OperatorIdentityError("IDENTITY_UNAVAILABLE") from error
        if not isinstance(identity, OperatorIdentity):
            raise OperatorIdentityError("IDENTITY_RESPONSE_INVALID")
        if identity.environment != self.environment:
            raise OperatorIdentityError("IDENTITY_ENVIRONMENT_MISMATCH")
        if self.required_scope not in identity.scopes:
            raise OperatorIdentityError("TOKEN_OPERATOR_SCOPE_MISSING")
        return identity


def build_sql_family_experience_release_set_runtime(
    *,
    environment: str,
    identity_port: OperatorIdentityPort,
    deployment_port: ReleaseSetDeploymentPort,
    session_factory: async_sessionmaker[AsyncSession],
    required_scope: str = RELEASE_DEPLOY_SCOPE,
    clock: Callable[[], datetime] | None = None,
) -> FamilyExperienceReleaseSetRuntime:
    """Use the same durable transition path in all four environments."""

    if environment not in RELEASE_SET_ENVIRONMENTS:
        raise FamilyExperienceReleaseSetWiringError("RELEASE_SET_ENVIRONMENT_INVALID")
    if not callable(getattr(identity_port, "resolve", None)):
        raise FamilyExperienceReleaseSetWiringError("RELEASE_SET_IDENTITY_PORT_REQUIRED")
    if not callable(getattr(deployment_port, "apply", None)) or not callable(
        getattr(deployment_port, "rollback", None)
    ):
        raise FamilyExperienceReleaseSetWiringError(
            "RELEASE_SET_DEPLOYMENT_PORT_REQUIRED"
        )
    if not isinstance(session_factory, async_sessionmaker):
        raise FamilyExperienceReleaseSetWiringError("RELEASE_SET_SESSION_FACTORY_REQUIRED")
    if not required_scope.strip():
        raise FamilyExperienceReleaseSetWiringError("RELEASE_SET_SCOPE_REQUIRED")
    store = SessionPerCallReleaseSetDeploymentStore(session_factory)
    controls = SessionPerCallReleaseSetControlReader(session_factory)
    transitions = SqlAlchemyReleaseSetTransitionCoordinator(
        session_factory,
        clock=clock,
    )
    return FamilyExperienceReleaseSetRuntime(
        environment=environment,
        identity_port=identity_port,
        deployment=FamilyExperienceReleaseSetDeploymentService(
            port=deployment_port,
            store=store,
            controls=controls,
            transitions=transitions,
            clock=clock,
        ),
        required_scope=required_scope,
    )


def build_http_sql_family_experience_release_set_runtime(
    *,
    environment: str,
    identity_port: OperatorIdentityPort,
    deployment_base_url: str,
    deployment_token_provider: ReleaseSetTokenProvider,
    session_factory: async_sessionmaker[AsyncSession],
    deployment_client: httpx.AsyncClient | None = None,
    deployment_client_config: MtlsClientConfig | None = None,
    required_scope: str = RELEASE_DEPLOY_SCOPE,
    clock: Callable[[], datetime] | None = None,
) -> FamilyExperienceReleaseSetRuntime:
    """Compose the fenced SQL runtime with the real provider-neutral HTTP port."""

    return build_sql_family_experience_release_set_runtime(
        environment=environment,
        identity_port=identity_port,
        deployment_port=HttpReleaseSetDeploymentPort(
            base_url=deployment_base_url,
            token_provider=deployment_token_provider,
            client=deployment_client,
            client_config=deployment_client_config,
        ),
        session_factory=session_factory,
        required_scope=required_scope,
        clock=clock,
    )


def build_sql_family_experience_release_set_reconciliation_scheduler(
    *,
    environment: str,
    worker_id: str,
    deployment_port: ReleaseSetDeploymentPort,
    session_factory: async_sessionmaker[AsyncSession],
    stale_after: timedelta = timedelta(minutes=2),
    lease_ttl: timedelta = timedelta(seconds=30),
    retry_base: timedelta = timedelta(seconds=30),
    retry_max: timedelta = timedelta(minutes=30),
    limit: int = 20,
    clock: Callable[[], datetime] | None = None,
) -> ReleaseSetReconciliationScheduler:
    """Compose one bounded reconciler without creating new release authority."""

    if environment not in RELEASE_SET_ENVIRONMENTS:
        raise FamilyExperienceReleaseSetWiringError("RELEASE_SET_ENVIRONMENT_INVALID")
    if not callable(getattr(deployment_port, "observe", None)):
        raise FamilyExperienceReleaseSetWiringError(
            "RELEASE_SET_OBSERVATION_PORT_REQUIRED"
        )
    transitions = SqlAlchemyReleaseSetTransitionCoordinator(
        session_factory,
        clock=clock,
    )
    deployment = FamilyExperienceReleaseSetDeploymentService(
        port=deployment_port,
        store=SessionPerCallReleaseSetDeploymentStore(session_factory),
        controls=SessionPerCallReleaseSetControlReader(session_factory),
        transitions=transitions,
        clock=clock,
    )
    return ReleaseSetReconciliationScheduler(
        environment=environment,
        worker_id=worker_id,
        transitions=transitions,
        release_sets=SessionPerCallFamilyExperienceReleaseSetReader(session_factory),
        observer=deployment_port,  # type: ignore[arg-type]
        deployment=deployment,
        stale_after=stale_after,
        lease_ttl=lease_ttl,
        retry_base=retry_base,
        retry_max=retry_max,
        limit=limit,
        clock=clock or (lambda: datetime.now(UTC)),
    )


def build_http_sql_family_experience_release_set_reconciliation_scheduler(
    *,
    environment: str,
    worker_id: str,
    deployment_base_url: str,
    deployment_token_provider: ReleaseSetTokenProvider,
    session_factory: async_sessionmaker[AsyncSession],
    deployment_client: httpx.AsyncClient | None = None,
    deployment_client_config: MtlsClientConfig | None = None,
    stale_after: timedelta = timedelta(minutes=2),
    lease_ttl: timedelta = timedelta(seconds=30),
    retry_base: timedelta = timedelta(seconds=30),
    retry_max: timedelta = timedelta(minutes=30),
    limit: int = 20,
    clock: Callable[[], datetime] | None = None,
) -> ReleaseSetReconciliationScheduler:
    """Compose the same HTTP observation contract in all environments."""

    return build_sql_family_experience_release_set_reconciliation_scheduler(
        environment=environment,
        worker_id=worker_id,
        deployment_port=HttpReleaseSetDeploymentPort(
            base_url=deployment_base_url,
            token_provider=deployment_token_provider,
            client=deployment_client,
            client_config=deployment_client_config,
        ),
        session_factory=session_factory,
        stale_after=stale_after,
        lease_ttl=lease_ttl,
        retry_base=retry_base,
        retry_max=retry_max,
        limit=limit,
        clock=clock,
    )


__all__ = [
    "FamilyExperienceReleaseSetRuntime",
    "FamilyExperienceReleaseSetWiringError",
    "RELEASE_SET_ENVIRONMENTS",
    "build_http_sql_family_experience_release_set_reconciliation_scheduler",
    "build_http_sql_family_experience_release_set_runtime",
    "build_sql_family_experience_release_set_reconciliation_scheduler",
    "build_sql_family_experience_release_set_runtime",
]
