"""Environment-parity composition root for family-experience canary safety."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import httpx

from backend.apps.family_api.family_experience_release_wiring import (
    FAMILY_EXPERIENCE_RELEASE_ENVIRONMENTS,
)
from backend.intelligence.evaluation.deployment import DeploymentReceipt
from backend.intelligence.evaluation.http_deployment import TokenProvider
from backend.intelligence.evaluation.release_catalog import ReleaseCandidate
from backend.intelligence.experience.canary_supervision import (
    CanaryAssessmentStore,
    CanaryObservationPort,
    CanarySloPolicy,
    CanarySupervisionError,
    CanarySupervisionResult,
    FamilyExperienceCanarySupervisor,
    RollbackControlReader,
)
from backend.intelligence.experience.http_canary_observation import (
    HttpCanaryObservationPort,
)
from backend.intelligence.experience.release_bundle_deployment import (
    FamilyExperienceReleaseDeploymentService,
)
from backend.platform.security.mtls import MtlsClientConfig


@dataclass(frozen=True, slots=True)
class FamilyExperienceCanaryRuntime:
    environment: str
    supervisor: FamilyExperienceCanarySupervisor

    def __post_init__(self) -> None:
        if self.environment not in FAMILY_EXPERIENCE_RELEASE_ENVIRONMENTS:
            raise CanarySupervisionError("CANARY_RUNTIME_ENVIRONMENT_INVALID")
        if not isinstance(self.supervisor, FamilyExperienceCanarySupervisor):
            raise CanarySupervisionError("CANARY_SUPERVISOR_REQUIRED")

    async def supervise(
        self,
        candidate: ReleaseCandidate,
        canary_receipt: DeploymentReceipt,
        *,
        rollback_control_id: str | None,
        idempotency_key: str,
    ) -> CanarySupervisionResult:
        if (
            candidate.environment != self.environment
            or canary_receipt.environment != self.environment
        ):
            raise CanarySupervisionError("CANARY_RUNTIME_ENVIRONMENT_MISMATCH")
        return await self.supervisor.supervise(
            candidate,
            canary_receipt,
            rollback_control_id=rollback_control_id,
            idempotency_key=idempotency_key,
        )


def build_family_experience_canary_runtime(
    *,
    environment: str,
    observation_port: CanaryObservationPort,
    rollback_controls: RollbackControlReader,
    deployment: FamilyExperienceReleaseDeploymentService,
    assessments: CanaryAssessmentStore,
    policy: CanarySloPolicy,
    clock: Callable[[], datetime] | None = None,
) -> FamilyExperienceCanaryRuntime:
    if environment not in FAMILY_EXPERIENCE_RELEASE_ENVIRONMENTS:
        raise CanarySupervisionError("CANARY_RUNTIME_ENVIRONMENT_INVALID")
    for dependency, methods, code in (
        (observation_port, ("observe",), "CANARY_OBSERVATION_PORT_REQUIRED"),
        (rollback_controls, ("get",), "ROLLBACK_CONTROL_READER_REQUIRED"),
        (assessments, ("get", "append"), "CANARY_ASSESSMENT_STORE_REQUIRED"),
    ):
        if any(not callable(getattr(dependency, method, None)) for method in methods):
            raise CanarySupervisionError(code)
    if not isinstance(deployment, FamilyExperienceReleaseDeploymentService):
        raise CanarySupervisionError("BUNDLE_DEPLOYMENT_SERVICE_REQUIRED")
    if not isinstance(policy, CanarySloPolicy):
        raise CanarySupervisionError("CANARY_POLICY_REQUIRED")
    return FamilyExperienceCanaryRuntime(
        environment=environment,
        supervisor=FamilyExperienceCanarySupervisor(
            observation_port=observation_port,
            rollback_controls=rollback_controls,
            deployment=deployment,
            assessments=assessments,
            policy=policy,
            clock=clock,
        ),
    )


def build_http_family_experience_canary_runtime(
    *,
    environment: str,
    observation_base_url: str,
    token_provider: TokenProvider,
    rollback_controls: RollbackControlReader,
    deployment: FamilyExperienceReleaseDeploymentService,
    assessments: CanaryAssessmentStore,
    policy: CanarySloPolicy,
    observation_client: httpx.AsyncClient | None = None,
    observation_client_config: MtlsClientConfig | None = None,
    observation_timeout_seconds: float = 15.0,
    clock: Callable[[], datetime] | None = None,
) -> FamilyExperienceCanaryRuntime:
    observation_port = HttpCanaryObservationPort(
        base_url=observation_base_url,
        token_provider=token_provider,
        client=observation_client,
        client_config=observation_client_config,
        timeout_seconds=observation_timeout_seconds,
    )
    return build_family_experience_canary_runtime(
        environment=environment,
        observation_port=observation_port,
        rollback_controls=rollback_controls,
        deployment=deployment,
        assessments=assessments,
        policy=policy,
        clock=clock,
    )


__all__ = [
    "FamilyExperienceCanaryRuntime",
    "build_family_experience_canary_runtime",
    "build_http_family_experience_canary_runtime",
]
