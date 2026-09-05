from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.evaluation.deployment import (
    DeploymentPhase,
    DeploymentResult,
    InMemoryDeploymentReceiptStore,
)
from backend.intelligence.evaluation.release_catalog import InMemoryReleaseCandidateCatalog
from backend.intelligence.evaluation.release_control import InMemoryReleaseControlStore
from backend.intelligence.evaluation.release_gate import ReleaseDecision
from backend.intelligence.experience.release_bundle import FamilyExperienceReleaseBundleError
from backend.intelligence.experience.release_bundle import (
    build_family_experience_release_bundle as _build_release_bundle,
)
from backend.intelligence.experience.release_bundle_deployment import (
    FamilyExperienceReleaseDeploymentService,
)
from backend.intelligence.experience.release_bundle_persistence import (
    FamilyExperienceReleaseBundleBase,
    InMemoryFamilyExperienceReleaseBundleStore,
    SessionPerCallFamilyExperienceReleaseBundleReader,
    SqlAlchemyFamilyExperienceReleaseBundleStore,
)
from backend.intelligence.experience.standard_assets import build_family_experience_assets
from backend.intelligence.model_gateway.provider_registry import (
    ProviderRecord,
    ProviderRegistry,
)

NOW = datetime(2026, 8, 31, 9, 0, tzinfo=UTC)


def build_family_experience_release_bundle(**values):  # type: ignore[no-untyped-def]
    return _build_release_bundle(
        routing_policy_version="multimodal-routing.v1",
        rate_card_version="family-rate-card.v1",
        budget_policy_version="family-budget.v1",
        **values,
    )


class _SignatureVerifier:
    def verify(self, *, payload: bytes, signature: str, actor_id: str) -> bool:
        return bool(payload and actor_id and signature == "valid-signature")


class _BundleDeploymentPort:
    def __init__(self) -> None:
        self.bundles = []

    async def apply(
        self, bundle, candidate, control, *, phase, rollout_percent, idempotency_key
    ):
        self.bundles.append(bundle)
        return DeploymentResult(external_ref=f"bundle-deploy:{bundle.bundle_id}")

    async def rollback(self, bundle, candidate, control, *, idempotency_key):
        self.bundles.append(bundle)
        return DeploymentResult(external_ref=f"bundle-rollback:{bundle.bundle_id}")


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(FamilyExperienceReleaseBundleBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _decision() -> ReleaseDecision:
    return ReleaseDecision(
        status="ADMITTED",
        candidate_id="family-experience:provider-a:2026-08",
        provider_id="provider-a",
        model="multimodal-a",
        model_version="2026-08",
        environment="staging",
        report_ref="benchmark:family-experience:2026-08",
        failures=(),
    )


def _providers() -> ProviderRegistry:
    return ProviderRegistry(
        (
            ProviderRecord(
                provider_id="provider-a",
                vendor="vendor-a",
                model="multimodal-a",
                model_version="2026-08",
                status="INTERNAL_APPROVED",
                approved_environments=("staging",),
                sub_delegates=False,
                minor_data_allowed=True,
                private_text_allowed=True,
                security_assessment_ref="security:provider-a",
                processing_agreement_ref="agreement:provider-a",
                deletion_on_termination_committed=True,
                processing_region="CN",
            ),
        )
    )


async def _release_artifacts():
    decision = _decision()
    controls = InMemoryReleaseControlStore(
        signature_verifier=_SignatureVerifier(), clock=lambda: NOW
    )
    approval = await controls.approve(
        decision,
        actor_id="operator-release-1",
        idempotency_key="approve:family-experience:2026-08",
        reason="reviewed",
        signature="valid-signature",
        signature_algorithm="external-kms-v1",
    )
    bundle = build_family_experience_release_bundle(
        assets=build_family_experience_assets(
            status="PUBLISHED",
            reviewer="prompt-reviewer",
            effective_at=NOW - timedelta(days=1),
        ),
        decision=decision,
        approval=approval,
        provider_registry=_providers(),
        data_class="MINOR_PERSONAL_DATA",
    )
    catalog = InMemoryReleaseCandidateCatalog(clock=lambda: NOW)
    await catalog.register(decision)
    candidate = await catalog.approve(approval, human_actor=approval.actor_id)
    return bundle, candidate, approval


@pytest.mark.asyncio
async def test_sql_bundle_store_round_trips_across_sessions(session_factory) -> None:
    bundle, _, _ = await _release_artifacts()
    async with session_factory() as session:
        stored = await SqlAlchemyFamilyExperienceReleaseBundleStore(session).append(bundle)
        await session.commit()
    reader = SessionPerCallFamilyExperienceReleaseBundleReader(session_factory)
    assert await reader.get(bundle.bundle_id) == stored
    assert await reader.get_for_candidate(bundle.candidate_id, bundle.environment) == stored
    async with session_factory() as session:
        assert await SqlAlchemyFamilyExperienceReleaseBundleStore(session).append(bundle) == stored


@pytest.mark.asyncio
async def test_bundle_store_rejects_same_candidate_with_changed_assets() -> None:
    bundle, _, _ = await _release_artifacts()
    store = InMemoryFamilyExperienceReleaseBundleStore()
    await store.append(bundle)
    changed = replace(bundle, bundle_id="f" * 64, asset_digest="e" * 64)
    with pytest.raises(
        FamilyExperienceReleaseBundleError,
        match="RELEASE_CANDIDATE_BUNDLE_CONFLICT",
    ):
        await store.append(changed)


@pytest.mark.asyncio
async def test_bundle_aware_deployment_forwards_complete_bundle_once() -> None:
    bundle, candidate, approval = await _release_artifacts()
    bundles = InMemoryFamilyExperienceReleaseBundleStore()
    await bundles.append(bundle)
    port = _BundleDeploymentPort()
    service = FamilyExperienceReleaseDeploymentService(
        port=port,
        bundles=bundles,
        receipts=InMemoryDeploymentReceiptStore(),
    )

    first = await service.apply(
        candidate,
        approval,
        human_actor=approval.actor_id,
        phase=DeploymentPhase.CANARY,
        rollout_percent=5,
        idempotency_key="deploy:family-experience:canary",
    )
    replay = await service.apply(
        candidate,
        approval,
        human_actor=approval.actor_id,
        phase=DeploymentPhase.CANARY,
        rollout_percent=5,
        idempotency_key="deploy:family-experience:canary",
    )

    assert first == replay
    assert port.bundles == [bundle]
    assert first.external_ref == f"bundle-deploy:{bundle.bundle_id}"


@pytest.mark.asyncio
async def test_bundle_aware_deployment_fails_closed_before_external_call() -> None:
    bundle, candidate, approval = await _release_artifacts()
    port = _BundleDeploymentPort()
    missing_service = FamilyExperienceReleaseDeploymentService(
        port=port,
        bundles=InMemoryFamilyExperienceReleaseBundleStore(),
        receipts=InMemoryDeploymentReceiptStore(),
    )
    with pytest.raises(FamilyExperienceReleaseBundleError, match="RELEASE_BUNDLE_NOT_FOUND"):
        await missing_service.apply(
            candidate,
            approval,
            human_actor=approval.actor_id,
            phase=DeploymentPhase.CANARY,
            rollout_percent=5,
            idempotency_key="deploy:missing-bundle",
        )

    bundles = InMemoryFamilyExperienceReleaseBundleStore()
    await bundles.append(bundle)
    mismatch_service = FamilyExperienceReleaseDeploymentService(
        port=port,
        bundles=bundles,
        receipts=InMemoryDeploymentReceiptStore(),
    )
    with pytest.raises(
        FamilyExperienceReleaseBundleError,
        match="RELEASE_BUNDLE_CANDIDATE_MISMATCH",
    ):
        await mismatch_service.apply(
            replace(candidate, model_version="changed-after-approval"),
            approval,
            human_actor=approval.actor_id,
            phase=DeploymentPhase.CANARY,
            rollout_percent=5,
            idempotency_key="deploy:mismatched-bundle",
        )

    replaced_approval = replace(approval, control_id="different-approval-control")
    with pytest.raises(
        FamilyExperienceReleaseBundleError,
        match="RELEASE_BUNDLE_APPROVAL_MISMATCH",
    ):
        await mismatch_service.apply(
            candidate,
            replaced_approval,
            human_actor=replaced_approval.actor_id,
            phase=DeploymentPhase.CANARY,
            rollout_percent=5,
            idempotency_key="deploy:replaced-approval",
        )
    assert port.bundles == []
