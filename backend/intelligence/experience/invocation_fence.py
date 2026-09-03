"""Durable release-projection fence immediately before external model I/O."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.intelligence.model_gateway.contracts import StructuredRequest
from backend.intelligence.model_gateway.release_fence import (
    ModelInvocationFenceClaim,
    ModelInvocationFenceError,
)

from .release_set_deployment import (
    ActiveReleaseBindingRow,
    ModelInvocationFenceClaimRow,
)
from .release_set_persistence import SqlAlchemyFamilyExperienceReleaseSetStore


class SqlAlchemyModelInvocationFence:
    """Serialize each invocation claim with deployment/rollback projection writes."""

    durability_mode = "DURABLE"

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        environment: str,
    ) -> None:
        if not isinstance(session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        if not environment.strip():
            raise ValueError("environment is required")
        self._session_factory = session_factory
        self._environment = environment

    async def claim(
        self,
        request: StructuredRequest,
        *,
        provider_id: str,
        route_sequence: int,
    ) -> ModelInvocationFenceClaim:
        binding = request.release_binding
        if binding is None:
            raise ModelInvocationFenceError("MODEL_RELEASE_BINDING_REQUIRED")
        if not request.request_id:
            raise ModelInvocationFenceError("MODEL_INVOCATION_REQUEST_ID_REQUIRED")
        try:
            bundle_id = binding.bundle_id_for(provider_id)
        except ValueError as error:
            raise ModelInvocationFenceError(
                "MODEL_RELEASE_PROVIDER_NOT_AUTHORIZED"
            ) from error
        now = datetime.now(UTC)
        claim_id = uuid4().hex
        request_ref = hashlib.sha256(request.request_id.encode()).hexdigest()
        claim_key = hashlib.sha256(
            (
                f"{request_ref}:{provider_id}:{route_sequence}:"
                f"{binding.deployment_sequence}"
            ).encode()
        ).hexdigest()
        async with self._session_factory() as session, session.begin():
            projection = await session.scalar(
                select(ActiveReleaseBindingRow)
                .where(
                    ActiveReleaseBindingRow.environment == self._environment,
                    ActiveReleaseBindingRow.use_case == request.use_case,
                    ActiveReleaseBindingRow.data_class == request.data_class,
                )
                .with_for_update()
            )
            if projection is None:
                raise ModelInvocationFenceError("ACTIVE_RELEASE_BINDING_NOT_FOUND")
            observed = (
                projection.release_set_id,
                projection.deployment_receipt_id,
                projection.deployment_sequence,
                projection.runtime_config_digest,
                projection.control_id,
            )
            expected = (
                binding.release_set_id,
                binding.deployment_receipt_id,
                binding.deployment_sequence,
                binding.runtime_config_digest,
                binding.control_id,
            )
            if observed != expected:
                raise ModelInvocationFenceError("MODEL_RELEASE_BINDING_STALE")
            release_set = await SqlAlchemyFamilyExperienceReleaseSetStore(session).get(
                binding.release_set_id
            )
            if release_set is None:
                raise ModelInvocationFenceError("ACTIVE_RELEASE_SET_MANIFEST_NOT_FOUND")
            provider_bundles = dict(
                zip(release_set.provider_ids, release_set.bundle_ids, strict=True)
            )
            if (
                release_set.runtime_config_digest != binding.runtime_config_digest
                or provider_bundles.get(provider_id) != bundle_id
            ):
                raise ModelInvocationFenceError("MODEL_RELEASE_MANIFEST_MISMATCH")
            existing = await session.scalar(
                select(ModelInvocationFenceClaimRow).where(
                    ModelInvocationFenceClaimRow.claim_key == claim_key
                )
            )
            if existing is not None:
                created_at = existing.created_at
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=UTC)
                return ModelInvocationFenceClaim(
                    claim_id=existing.claim_id,
                    release_set_id=existing.release_set_id,
                    deployment_receipt_id=existing.deployment_receipt_id,
                    deployment_sequence=existing.deployment_sequence,
                    control_id=existing.control_id,
                    provider_id=existing.provider_id,
                    bundle_id=existing.bundle_id,
                    route_sequence=existing.route_sequence,
                    created_at=created_at,
                )
            session.add(
                ModelInvocationFenceClaimRow(
                    claim_id=claim_id,
                    claim_key=claim_key,
                    request_ref=request_ref,
                    environment=projection.environment,
                    use_case=projection.use_case,
                    data_class=projection.data_class,
                    release_set_id=binding.release_set_id,
                    deployment_receipt_id=binding.deployment_receipt_id,
                    deployment_sequence=binding.deployment_sequence,
                    runtime_config_digest=binding.runtime_config_digest,
                    control_id=binding.control_id,
                    provider_id=provider_id,
                    bundle_id=bundle_id,
                    route_sequence=route_sequence,
                    created_at=now,
                )
            )
        return ModelInvocationFenceClaim(
            claim_id=claim_id,
            release_set_id=binding.release_set_id,
            deployment_receipt_id=binding.deployment_receipt_id,
            deployment_sequence=binding.deployment_sequence,
            control_id=binding.control_id,
            provider_id=provider_id,
            bundle_id=bundle_id,
            route_sequence=route_sequence,
            created_at=now,
        )


__all__ = ["SqlAlchemyModelInvocationFence"]
