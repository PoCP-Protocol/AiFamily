"""Linearization point that rejects stale release bindings before model I/O."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from .contracts import ModelReleaseBinding, StructuredRequest


class ModelInvocationFenceError(RuntimeError):
    """The request's release binding is no longer the active deployment."""


@dataclass(frozen=True, slots=True)
class ModelInvocationFenceClaim:
    claim_id: str
    release_set_id: str
    deployment_receipt_id: str
    deployment_sequence: int
    control_id: str
    provider_id: str
    bundle_id: str
    route_sequence: int
    created_at: datetime


class ModelInvocationFence(Protocol):
    durability_mode: str

    async def claim(
        self,
        request: StructuredRequest,
        *,
        provider_id: str,
        route_sequence: int,
    ) -> ModelInvocationFenceClaim: ...


class InMemoryModelInvocationFence:
    """Test/dev equivalent of the durable release projection lock."""

    durability_mode = "IN_MEMORY"

    def __init__(self, active_binding: ModelReleaseBinding) -> None:
        self._active_binding = active_binding
        self._lock = asyncio.Lock()
        self.claims: list[ModelInvocationFenceClaim] = []
        self._claims_by_key: dict[
            tuple[str, str, int, int], ModelInvocationFenceClaim
        ] = {}

    async def replace_active(self, binding: ModelReleaseBinding) -> None:
        async with self._lock:
            self._active_binding = binding

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
        async with self._lock:
            if binding != self._active_binding:
                raise ModelInvocationFenceError("MODEL_RELEASE_BINDING_STALE")
            try:
                bundle_id = binding.bundle_id_for(provider_id)
            except ValueError as error:
                raise ModelInvocationFenceError(
                    "MODEL_RELEASE_PROVIDER_NOT_AUTHORIZED"
                ) from error
            key = (
                request.request_id or request.context_snapshot_ref,
                provider_id,
                route_sequence,
                binding.deployment_sequence,
            )
            existing = self._claims_by_key.get(key)
            if existing is not None:
                return existing
            claim = ModelInvocationFenceClaim(
                claim_id=uuid4().hex,
                release_set_id=binding.release_set_id,
                deployment_receipt_id=binding.deployment_receipt_id,
                deployment_sequence=binding.deployment_sequence,
                control_id=binding.control_id,
                provider_id=provider_id,
                bundle_id=bundle_id,
                route_sequence=route_sequence,
                created_at=datetime.now(UTC),
            )
            self.claims.append(claim)
            self._claims_by_key[key] = claim
            return claim


__all__ = [
    "InMemoryModelInvocationFence",
    "ModelInvocationFence",
    "ModelInvocationFenceClaim",
    "ModelInvocationFenceError",
]
