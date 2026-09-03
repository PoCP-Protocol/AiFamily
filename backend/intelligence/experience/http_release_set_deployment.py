"""HTTP adapter for fenced, atomic family-experience ReleaseSet deployment."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import quote

import httpx

from backend.platform.security.mtls import MtlsClientConfig

from .release_set import FamilyExperienceReleaseSet
from .release_set_deployment import (
    ReleaseSetDeploymentAcknowledgement,
    ReleaseSetDeploymentError,
    ReleaseSetDeploymentPhase,
    ReleaseSetTransitionClaim,
)
from .release_set_reconciliation import ExternalTransitionObservation

ReleaseSetTokenProvider = Callable[[], str | Awaitable[str]]


class HttpReleaseSetDeploymentPort:
    """Send metadata-only release manifests with an external fencing token."""

    def __init__(
        self,
        *,
        base_url: str,
        token_provider: ReleaseSetTokenProvider,
        client: httpx.AsyncClient | None = None,
        client_config: MtlsClientConfig | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_BASE_URL_REQUIRED")
        if not callable(token_provider):
            raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_TOKEN_PORT_REQUIRED")
        if client is not None and client_config is not None:
            raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_CLIENT_CONFLICT")
        if client_config is not None and not isinstance(client_config, MtlsClientConfig):
            raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_MTLS_INVALID")
        if (
            not isinstance(timeout_seconds, (int, float))
            or isinstance(timeout_seconds, bool)
            or timeout_seconds <= 0
        ):
            raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_TIMEOUT_INVALID")
        self._base_url = base_url.rstrip("/")
        self._token_provider = token_provider
        self._client = client
        self._client_config = client_config
        self._timeout_seconds = float(timeout_seconds)

    async def apply(
        self,
        release_set: FamilyExperienceReleaseSet,
        *,
        phase: ReleaseSetDeploymentPhase,
        rollout_percent: int,
        idempotency_key: str,
        transition_id: str,
        control_id: str,
        expected_effective_sequence: int,
    ) -> ReleaseSetDeploymentAcknowledgement:
        return await self._request(
            f"/v1/release-sets/{quote(release_set.release_set_id, safe='')}/deployments",
            release_set,
            acknowledged=release_set,
            idempotency_key=idempotency_key,
            transition_id=transition_id,
            control_id=control_id,
            expected_effective_sequence=expected_effective_sequence,
            payload={
                **_manifest(release_set),
                "operation": "APPLY",
                "phase": phase,
                "rollout_percent": rollout_percent,
            },
        )

    async def rollback(
        self,
        source: FamilyExperienceReleaseSet,
        target: FamilyExperienceReleaseSet,
        *,
        idempotency_key: str,
        transition_id: str,
        control_id: str,
        expected_effective_sequence: int,
    ) -> ReleaseSetDeploymentAcknowledgement:
        return await self._request(
            f"/v1/release-sets/{quote(source.release_set_id, safe='')}/rollback",
            source,
            acknowledged=target,
            idempotency_key=idempotency_key,
            transition_id=transition_id,
            control_id=control_id,
            expected_effective_sequence=expected_effective_sequence,
            payload={
                **_manifest(source),
                "operation": "ROLLBACK",
                "phase": "ROLLED_BACK",
                "rollout_percent": 0,
                "target_release_set_id": target.release_set_id,
                "target_runtime_config_digest": target.runtime_config_digest,
            },
        )

    async def observe(
        self,
        transition: ReleaseSetTransitionClaim,
    ) -> ExternalTransitionObservation:
        """Query metadata-only external state without replaying deployment."""

        token = await self._token()
        headers = {
            "authorization": f"Bearer {token}",
            "x-ai-transition-id": transition.transition_id,
            "x-ai-control-id": transition.control_id,
            "x-ai-expected-sequence": str(transition.expected_effective_sequence),
            "x-ai-environment": transition.environment,
        }
        path = (
            "/v1/release-set-transitions/"
            f"{quote(transition.transition_id, safe='')}"
        )
        try:
            if self._client is not None:
                response = await self._client.get(
                    f"{self._base_url}{path}",
                    headers=headers,
                    timeout=self._timeout_seconds,
                )
            else:
                factory = (
                    self._client_config.build_async_client
                    if self._client_config is not None
                    else httpx.AsyncClient
                )
                async with factory() as client:
                    response = await client.get(
                        f"{self._base_url}{path}",
                        headers=headers,
                        timeout=self._timeout_seconds,
                    )
        except httpx.TimeoutException as error:
            raise ReleaseSetDeploymentError("RELEASE_SET_OBSERVATION_TIMEOUT") from error
        except httpx.HTTPError as error:
            raise ReleaseSetDeploymentError("RELEASE_SET_OBSERVATION_NETWORK_ERROR") from error
        if not 200 <= response.status_code < 300:
            raise ReleaseSetDeploymentError("RELEASE_SET_OBSERVATION_REJECTED")
        try:
            result = response.json()
        except ValueError as error:
            raise ReleaseSetDeploymentError(
                "RELEASE_SET_OBSERVATION_RESPONSE_INVALID_JSON"
            ) from error
        expected = {
            "transition_id": transition.transition_id,
            "control_id": transition.control_id,
            "expected_effective_sequence": transition.expected_effective_sequence,
        }
        if not isinstance(result, dict) or any(
            result.get(name) != value for name, value in expected.items()
        ):
            raise ReleaseSetDeploymentError("RELEASE_SET_OBSERVATION_FENCE_MISMATCH")
        state = result.get("state")
        if state == "APPLIED":
            acknowledgement = ReleaseSetDeploymentAcknowledgement(
                acknowledged_release_set_id=result.get(
                    "acknowledged_release_set_id", ""
                ),
                applied_config_digest=result.get("applied_config_digest", ""),
                external_ref=result.get("external_ref", ""),
                transition_id=transition.transition_id,
                control_id=transition.control_id,
                expected_effective_sequence=transition.expected_effective_sequence,
            )
            return ExternalTransitionObservation(
                state="APPLIED",
                acknowledgement=acknowledgement,
            )
        if state not in {"PENDING", "ABSENT", "FAILED"}:
            raise ReleaseSetDeploymentError("RELEASE_SET_OBSERVATION_STATE_INVALID")
        error_code = result.get("error_code")
        if error_code is not None and not isinstance(error_code, str):
            raise ReleaseSetDeploymentError("RELEASE_SET_OBSERVATION_ERROR_INVALID")
        return ExternalTransitionObservation(
            state=state,
            error_code=error_code,
        )

    async def _request(
        self,
        path: str,
        source: FamilyExperienceReleaseSet,
        *,
        acknowledged: FamilyExperienceReleaseSet,
        idempotency_key: str,
        transition_id: str,
        control_id: str,
        expected_effective_sequence: int,
        payload: dict[str, Any],
    ) -> ReleaseSetDeploymentAcknowledgement:
        token = await self._token()
        headers = {
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
            "idempotency-key": idempotency_key,
            "x-ai-transition-id": transition_id,
            "x-ai-control-id": control_id,
            "x-ai-expected-sequence": str(expected_effective_sequence),
            "x-ai-environment": source.environment,
        }
        body = {
            **payload,
            "transition_id": transition_id,
            "control_id": control_id,
            "expected_effective_sequence": expected_effective_sequence,
        }
        try:
            if self._client is not None:
                response = await self._client.post(
                    f"{self._base_url}{path}",
                    json=body,
                    headers=headers,
                    timeout=self._timeout_seconds,
                )
            else:
                factory = (
                    self._client_config.build_async_client
                    if self._client_config is not None
                    else httpx.AsyncClient
                )
                async with factory() as client:
                    response = await client.post(
                        f"{self._base_url}{path}",
                        json=body,
                        headers=headers,
                        timeout=self._timeout_seconds,
                    )
        except httpx.TimeoutException as error:
            raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_TIMEOUT") from error
        except httpx.HTTPError as error:
            raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_NETWORK_ERROR") from error
        if not 200 <= response.status_code < 300:
            code = (
                "RELEASE_SET_DEPLOYMENT_PLATFORM_5XX"
                if response.status_code >= 500
                else "RELEASE_SET_DEPLOYMENT_PLATFORM_REJECTED"
            )
            raise ReleaseSetDeploymentError(code)
        try:
            result = response.json()
        except ValueError as error:
            raise ReleaseSetDeploymentError(
                "RELEASE_SET_DEPLOYMENT_RESPONSE_INVALID_JSON"
            ) from error
        expected = {
            "acknowledged_release_set_id": acknowledged.release_set_id,
            "applied_config_digest": acknowledged.runtime_config_digest,
            "transition_id": transition_id,
            "control_id": control_id,
            "expected_effective_sequence": expected_effective_sequence,
        }
        if not isinstance(result, dict) or any(
            result.get(name) != value for name, value in expected.items()
        ):
            raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_ACK_MISMATCH")
        external_ref = result.get("external_ref")
        if not isinstance(external_ref, str) or not external_ref.strip():
            raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_EXTERNAL_REF_REQUIRED")
        return ReleaseSetDeploymentAcknowledgement(
            acknowledged_release_set_id=acknowledged.release_set_id,
            applied_config_digest=acknowledged.runtime_config_digest,
            external_ref=external_ref,
            transition_id=transition_id,
            control_id=control_id,
            expected_effective_sequence=expected_effective_sequence,
        )

    async def _token(self) -> str:
        try:
            value = self._token_provider()
            token = await value if inspect.isawaitable(value) else value
        except Exception as error:
            raise ReleaseSetDeploymentError(
                "RELEASE_SET_DEPLOYMENT_TOKEN_UNAVAILABLE"
            ) from error
        if not isinstance(token, str) or not token.strip():
            raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_TOKEN_REQUIRED")
        return token


def _manifest(release_set: FamilyExperienceReleaseSet) -> dict[str, Any]:
    return {
        "release_set_id": release_set.release_set_id,
        "environment": release_set.environment,
        "use_case": release_set.use_case,
        "data_class": release_set.data_class,
        "provider_bundle_ids": [
            {"provider_id": provider_id, "bundle_id": bundle_id}
            for provider_id, bundle_id in zip(
                release_set.provider_ids,
                release_set.bundle_ids,
                strict=True,
            )
        ],
        "routing_policy_version": release_set.routing_policy_version,
        "route_config_digest": release_set.route_config_digest,
        "rate_card_version": release_set.rate_card_version,
        "rate_card_digest": release_set.rate_card_digest,
        "budget_policy_version": release_set.budget_policy_version,
        "budget_policy_digest": release_set.budget_policy_digest,
        "prompt_ref": release_set.prompt_ref,
        "prompt_version": release_set.prompt_version,
        "schema_ref": release_set.schema_ref,
        "schema_version": release_set.schema_version,
        "safety_policy_version": release_set.safety_policy_version,
        "safety_policy_digest": release_set.safety_policy_digest,
        "knowledge_refs": list(release_set.knowledge_refs),
        "asset_digest": release_set.asset_digest,
        "runtime_config_digest": release_set.runtime_config_digest,
        "draft_only": release_set.draft_only,
        "may_mutate_business_state": release_set.may_mutate_business_state,
    }


__all__ = ["HttpReleaseSetDeploymentPort", "ReleaseSetTokenProvider"]
