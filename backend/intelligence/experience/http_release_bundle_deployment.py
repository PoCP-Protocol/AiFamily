"""HTTP adapter that sends a complete family-experience release bundle."""

from __future__ import annotations

from urllib.parse import quote

import httpx

from backend.intelligence.evaluation.deployment import (
    DeploymentPhase,
    DeploymentResult,
)
from backend.intelligence.evaluation.http_deployment import (
    HttpDeploymentPort,
    TokenProvider,
)
from backend.intelligence.evaluation.release_catalog import ReleaseCandidate
from backend.intelligence.evaluation.release_control import ReleaseControlEvent
from backend.platform.security.mtls import MtlsClientConfig

from .release_bundle import FamilyExperienceReleaseBundle
from .release_bundle_deployment import FamilyExperienceDeploymentPort


class HttpFamilyExperienceDeploymentPort(FamilyExperienceDeploymentPort):
    """Use the common HTTP transport while preserving the complete Bundle."""

    def __init__(
        self,
        *,
        base_url: str,
        token_provider: TokenProvider,
        client: httpx.AsyncClient | None = None,
        client_config: MtlsClientConfig | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._transport = HttpDeploymentPort(
            base_url=base_url,
            token_provider=token_provider,
            client=client,
            client_config=client_config,
            timeout_seconds=timeout_seconds,
        )

    async def apply(
        self,
        bundle: FamilyExperienceReleaseBundle,
        candidate: ReleaseCandidate,
        control: ReleaseControlEvent,
        *,
        phase: DeploymentPhase,
        rollout_percent: int,
        idempotency_key: str,
    ) -> DeploymentResult:
        return await self._transport.request(
            "POST",
            f"/v1/releases/{quote(candidate.candidate_id, safe='')}/deployments",
            candidate,
            control,
            idempotency_key=idempotency_key,
            payload={
                "environment": candidate.environment,
                "phase": phase.value,
                "rollout_percent": rollout_percent,
                "provider_id": candidate.provider_id,
                "model": candidate.model,
                "model_version": candidate.model_version,
                "release_bundle": _bundle_payload(bundle),
            },
        )

    async def rollback(
        self,
        bundle: FamilyExperienceReleaseBundle,
        candidate: ReleaseCandidate,
        control: ReleaseControlEvent,
        *,
        idempotency_key: str,
    ) -> DeploymentResult:
        return await self._transport.request(
            "POST",
            f"/v1/releases/{quote(candidate.candidate_id, safe='')}/rollback",
            candidate,
            control,
            idempotency_key=idempotency_key,
            payload={
                "environment": candidate.environment,
                "target_candidate_id": control.target_candidate_id,
                "release_bundle": _bundle_payload(bundle),
            },
        )


def _bundle_payload(bundle: FamilyExperienceReleaseBundle) -> dict[str, object]:
    """Serialize metadata only; raw prompts, signatures and family data never enter it."""

    return {
        "bundle_id": bundle.bundle_id,
        "candidate_id": bundle.candidate_id,
        "environment": bundle.environment,
        "use_case": bundle.use_case,
        "agent_id": bundle.agent_id,
        "provider_id": bundle.provider_id,
        "model": bundle.model,
        "model_version": bundle.model_version,
        "prompt_ref": bundle.prompt_ref,
        "prompt_version": bundle.prompt_version,
        "schema_ref": bundle.schema_ref,
        "schema_version": bundle.schema_version,
        "safety_policy_version": bundle.safety_policy_version,
        "knowledge_refs": list(bundle.knowledge_refs),
        "data_class": bundle.data_class,
        "report_ref": bundle.report_ref,
        "decision_id": bundle.decision_id,
        "control_id": bundle.control_id,
        "approval_signature_ref": bundle.approval_signature_ref,
        "approval_signature_algorithm": bundle.approval_signature_algorithm,
        "approved_by": bundle.approved_by,
        "approved_at": bundle.approved_at.isoformat(),
        "asset_digest": bundle.asset_digest,
        "human_gate_rule": bundle.human_gate_rule,
        "draft_only": bundle.draft_only,
        "may_mutate_business_state": bundle.may_mutate_business_state,
    }


__all__ = ["HttpFamilyExperienceDeploymentPort"]
