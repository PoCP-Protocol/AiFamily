"""Resolve the currently effective atomic AI release set and detect drift."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.intelligence.model_gateway.budget import ModelBudgetRuntime
from backend.intelligence.safety.runtime import SafetyRuntime

from .multimodal_routing import MultimodalRouter
from .release_bundle_persistence import SqlAlchemyFamilyExperienceReleaseBundleStore
from .release_set import FamilyExperienceReleaseSet, validate_release_set_runtime
from .release_set_deployment import (
    ReleaseSetDeploymentReceipt,
    SqlAlchemyReleaseSetDeploymentStore,
)
from .release_set_persistence import SqlAlchemyFamilyExperienceReleaseSetStore


class RuntimeReleaseBindingError(ValueError):
    """No durable deployment authorizes the current runtime configuration."""


@dataclass(frozen=True, slots=True)
class ActiveFamilyExperienceRuntimeBinding:
    release_set: FamilyExperienceReleaseSet
    deployment_receipt: ReleaseSetDeploymentReceipt

    def __post_init__(self) -> None:
        receipt = self.deployment_receipt
        expected_release_set_id = (
            receipt.release_set_id
            if receipt.operation == "APPLY"
            else receipt.target_release_set_id
        )
        if expected_release_set_id != self.release_set.release_set_id:
            raise RuntimeReleaseBindingError("ACTIVE_RELEASE_SET_RECEIPT_MISMATCH")
        if (
            receipt.acknowledged_release_set_id != self.release_set.release_set_id
            or receipt.applied_config_digest != self.release_set.runtime_config_digest
        ):
            raise RuntimeReleaseBindingError("ACTIVE_RELEASE_ACK_MISMATCH")


class ActiveFamilyExperienceReleaseResolver(Protocol):
    durability_mode: str

    async def resolve(
        self, *, environment: str, use_case: str, data_class: str
    ) -> ActiveFamilyExperienceRuntimeBinding: ...


@dataclass(frozen=True, slots=True)
class StaticActiveFamilyExperienceReleaseResolver:
    """Process-local adapter for tests; production composition rejects it."""

    binding: ActiveFamilyExperienceRuntimeBinding
    durability_mode: str = "IN_MEMORY"

    async def resolve(
        self, *, environment: str, use_case: str, data_class: str
    ) -> ActiveFamilyExperienceRuntimeBinding:
        return self.binding


class SqlAlchemyActiveFamilyExperienceReleaseResolver:
    """Read monotonic effective state on every call so rollback takes effect."""

    durability_mode = "DURABLE"

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        if not isinstance(session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        self._session_factory = session_factory

    async def resolve(
        self, *, environment: str, use_case: str, data_class: str
    ) -> ActiveFamilyExperienceRuntimeBinding:
        async with self._session_factory() as session:
            deployments = SqlAlchemyReleaseSetDeploymentStore(session)
            projection = await deployments.get_active_binding(
                environment=environment,
                use_case=use_case,
                data_class=data_class,
            )
            if projection is None:
                raise RuntimeReleaseBindingError("ACTIVE_RELEASE_SET_NOT_FOUND")
            receipt = await deployments.get_by_receipt_id(
                projection.deployment_receipt_id
            )
            if receipt is None:
                raise RuntimeReleaseBindingError("ACTIVE_RELEASE_RECEIPT_NOT_FOUND")
            effective_release_set_id = (
                receipt.release_set_id
                if receipt.operation == "APPLY"
                else receipt.target_release_set_id
            )
            if (
                effective_release_set_id != projection.release_set_id
                or receipt.sequence != projection.deployment_sequence
                or receipt.applied_config_digest != projection.runtime_config_digest
                or receipt.control_id != projection.control_id
            ):
                raise RuntimeReleaseBindingError("ACTIVE_RELEASE_PROJECTION_MISMATCH")
            if receipt.operation == "ROLLBACK" and not await deployments.was_active(
                projection.release_set_id
            ):
                raise RuntimeReleaseBindingError("ROLLBACK_TARGET_WAS_NOT_ACTIVE")
            release_set = await SqlAlchemyFamilyExperienceReleaseSetStore(session).get(
                projection.release_set_id
            )
            if release_set is None:
                raise RuntimeReleaseBindingError("ACTIVE_RELEASE_SET_MANIFEST_NOT_FOUND")
            if release_set.runtime_config_digest != projection.runtime_config_digest:
                raise RuntimeReleaseBindingError("ACTIVE_RELEASE_CONFIG_DIGEST_MISMATCH")
            bundle_store = SqlAlchemyFamilyExperienceReleaseBundleStore(session)
            for provider_id, bundle_id in zip(
                release_set.provider_ids,
                release_set.bundle_ids,
                strict=True,
            ):
                bundle = await bundle_store.get(bundle_id)
                if bundle is None:
                    raise RuntimeReleaseBindingError("ACTIVE_RELEASE_BUNDLE_NOT_FOUND")
                if (
                    bundle.provider_id != provider_id
                    or bundle.environment != release_set.environment
                    or bundle.use_case != release_set.use_case
                    or bundle.data_class != release_set.data_class
                    or bundle.agent_id != release_set.agent_id
                    or bundle.prompt_ref != release_set.prompt_ref
                    or bundle.prompt_version != release_set.prompt_version
                    or bundle.schema_ref != release_set.schema_ref
                    or bundle.schema_version != release_set.schema_version
                    or bundle.safety_policy_version != release_set.safety_policy_version
                    or bundle.knowledge_refs != release_set.knowledge_refs
                    or bundle.asset_digest != release_set.asset_digest
                ):
                    raise RuntimeReleaseBindingError("ACTIVE_RELEASE_BUNDLE_SET_MISMATCH")
            return ActiveFamilyExperienceRuntimeBinding(release_set, receipt)


def validate_active_runtime_binding(
    binding: ActiveFamilyExperienceRuntimeBinding,
    *,
    router: MultimodalRouter,
    budget_runtime: ModelBudgetRuntime,
    safety_runtime: SafetyRuntime,
    environment: str,
    use_case: str,
    data_class: str,
) -> None:
    """Verify scope and all configuration content, not merely version labels."""

    if not isinstance(binding, ActiveFamilyExperienceRuntimeBinding):
        raise RuntimeReleaseBindingError("ACTIVE_RUNTIME_BINDING_REQUIRED")
    release_set = binding.release_set
    if (
        release_set.environment,
        release_set.use_case,
        release_set.data_class,
    ) != (environment, use_case, data_class):
        raise RuntimeReleaseBindingError("ACTIVE_RELEASE_SCOPE_MISMATCH")
    try:
        validate_release_set_runtime(
            release_set,
            router=router,
            budget_runtime=budget_runtime,
            safety_runtime=safety_runtime,
        )
    except ValueError as error:
        raise RuntimeReleaseBindingError("ACTIVE_RELEASE_RUNTIME_CONFIG_DRIFT") from error


__all__ = [
    "ActiveFamilyExperienceReleaseResolver",
    "ActiveFamilyExperienceRuntimeBinding",
    "RuntimeReleaseBindingError",
    "SqlAlchemyActiveFamilyExperienceReleaseResolver",
    "StaticActiveFamilyExperienceReleaseResolver",
    "validate_active_runtime_binding",
]
