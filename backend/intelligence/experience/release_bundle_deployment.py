"""Bundle-aware deployment seam for the governed family-experience slice."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from backend.intelligence.evaluation.deployment import (
    DeploymentPhase,
    DeploymentPort,
    DeploymentReceipt,
    DeploymentReceiptStore,
    DeploymentResult,
    ReleaseDeploymentService,
)
from backend.intelligence.evaluation.release_catalog import ReleaseCandidate
from backend.intelligence.evaluation.release_control import ReleaseControlEvent
from backend.intelligence.observability import TelemetrySink

from .release_bundle import (
    FamilyExperienceReleaseBundle,
    FamilyExperienceReleaseBundleError,
)
from .release_bundle_persistence import FamilyExperienceReleaseBundleReader


class FamilyExperienceDeploymentPort(Protocol):
    """External platform port that receives the complete immutable bundle."""

    async def apply(
        self,
        bundle: FamilyExperienceReleaseBundle,
        candidate: ReleaseCandidate,
        control: ReleaseControlEvent,
        *,
        phase: DeploymentPhase,
        rollout_percent: int,
        idempotency_key: str,
    ) -> DeploymentResult: ...

    async def rollback(
        self,
        bundle: FamilyExperienceReleaseBundle,
        candidate: ReleaseCandidate,
        control: ReleaseControlEvent,
        *,
        idempotency_key: str,
    ) -> DeploymentResult: ...


@dataclass(frozen=True, slots=True)
class FamilyExperienceReleaseDeploymentService:
    """Fail closed unless a persisted bundle exactly matches deployment input."""

    port: FamilyExperienceDeploymentPort
    bundles: FamilyExperienceReleaseBundleReader
    receipts: DeploymentReceiptStore
    clock: Callable[[], datetime] | None = None
    telemetry_sink: TelemetrySink | None = None

    async def apply(
        self,
        candidate: ReleaseCandidate,
        control: ReleaseControlEvent,
        *,
        human_actor: str,
        phase: DeploymentPhase,
        rollout_percent: int,
        idempotency_key: str,
    ) -> DeploymentReceipt:
        bundle = await self._required_bundle(candidate)
        _validate_binding(bundle, candidate, control, require_approval_control=True)
        delegate = ReleaseDeploymentService(
            _BoundDeploymentPort(self.port, bundle),
            self.receipts,
            clock=self.clock,
            telemetry_sink=self.telemetry_sink,
        )
        return await delegate.apply(
            candidate,
            control,
            human_actor=human_actor,
            phase=phase,
            rollout_percent=rollout_percent,
            idempotency_key=idempotency_key,
        )

    async def rollback(
        self,
        candidate: ReleaseCandidate,
        control: ReleaseControlEvent,
        *,
        human_actor: str,
        idempotency_key: str,
    ) -> DeploymentReceipt:
        bundle = await self._required_bundle(candidate)
        _validate_binding(bundle, candidate, control, require_approval_control=False)
        delegate = ReleaseDeploymentService(
            _BoundDeploymentPort(self.port, bundle),
            self.receipts,
            clock=self.clock,
            telemetry_sink=self.telemetry_sink,
        )
        return await delegate.rollback(
            candidate,
            control,
            human_actor=human_actor,
            idempotency_key=idempotency_key,
        )

    async def _required_bundle(
        self, candidate: ReleaseCandidate
    ) -> FamilyExperienceReleaseBundle:
        bundle = await self.bundles.get_for_candidate(
            candidate.candidate_id, candidate.environment
        )
        if bundle is None:
            raise FamilyExperienceReleaseBundleError("RELEASE_BUNDLE_NOT_FOUND")
        return bundle


@dataclass(frozen=True, slots=True)
class _BoundDeploymentPort(DeploymentPort):
    port: FamilyExperienceDeploymentPort
    bundle: FamilyExperienceReleaseBundle

    async def apply(
        self,
        candidate: ReleaseCandidate,
        control: ReleaseControlEvent,
        *,
        phase: DeploymentPhase,
        rollout_percent: int,
        idempotency_key: str,
    ) -> DeploymentResult:
        return await self.port.apply(
            self.bundle,
            candidate,
            control,
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
    ) -> DeploymentResult:
        return await self.port.rollback(
            self.bundle,
            candidate,
            control,
            idempotency_key=idempotency_key,
        )


def _validate_binding(
    bundle: FamilyExperienceReleaseBundle,
    candidate: ReleaseCandidate,
    control: ReleaseControlEvent,
    *,
    require_approval_control: bool,
) -> None:
    candidate_fields = (
        bundle.candidate_id == candidate.candidate_id,
        bundle.environment == candidate.environment,
        bundle.decision_id == candidate.decision_id,
        bundle.provider_id == candidate.provider_id,
        bundle.model == candidate.model,
        bundle.model_version == candidate.model_version,
        bundle.report_ref == candidate.report_ref,
    )
    if not all(candidate_fields):
        raise FamilyExperienceReleaseBundleError("RELEASE_BUNDLE_CANDIDATE_MISMATCH")
    if (
        control.candidate_id != bundle.candidate_id
        or control.environment != bundle.environment
        or control.decision_id != bundle.decision_id
    ):
        raise FamilyExperienceReleaseBundleError("RELEASE_BUNDLE_CONTROL_MISMATCH")
    if require_approval_control and (
        control.kind != "APPROVAL" or control.control_id != bundle.control_id
    ):
        raise FamilyExperienceReleaseBundleError("RELEASE_BUNDLE_APPROVAL_MISMATCH")
    if not bundle.draft_only or bundle.may_mutate_business_state:
        raise FamilyExperienceReleaseBundleError("RELEASE_DRAFT_ONLY_BOUNDARY_REQUIRED")


__all__ = [
    "FamilyExperienceDeploymentPort",
    "FamilyExperienceReleaseDeploymentService",
]
