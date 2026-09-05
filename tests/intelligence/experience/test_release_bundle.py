from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.evaluation.release_control import InMemoryReleaseControlStore
from backend.intelligence.evaluation.release_gate import ReleaseDecision
from backend.intelligence.experience.release_bundle import FamilyExperienceReleaseBundleError
from backend.intelligence.experience.release_bundle import (
    build_family_experience_release_bundle as _build_release_bundle,
)
from backend.intelligence.experience.standard_assets import (
    FamilyExperienceAssetBundle,
    build_family_experience_assets,
)
from backend.intelligence.model_gateway.provider_registry import (
    ProviderRecord,
    ProviderRegistry,
)

NOW = datetime(2026, 8, 31, 8, 0, tzinfo=UTC)


def build_family_experience_release_bundle(**values):  # type: ignore[no-untyped-def]
    return _build_release_bundle(
        routing_policy_version="multimodal-routing.v1",
        rate_card_version="family-rate-card.v1",
        budget_policy_version="family-budget.v1",
        **values,
    )


class _SignatureVerifier:
    def verify(self, *, payload: bytes, signature: str, actor_id: str) -> bool:
        return bool(payload and actor_id) and signature == "valid-signature"


def _provider_registry() -> ProviderRegistry:
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


def _decision(*, status: str = "ADMITTED", model: str = "multimodal-a") -> ReleaseDecision:
    return ReleaseDecision(
        status=status,  # type: ignore[arg-type]
        candidate_id="family-experience:provider-a:2026-08",
        provider_id="provider-a",
        model=model,
        model_version="2026-08",
        environment="staging",
        report_ref="benchmark:family-experience:2026-08",
        failures=() if status == "ADMITTED" else ("quality_below_min",),
    )


def _assets(*, status: str = "PUBLISHED") -> FamilyExperienceAssetBundle:
    if status == "DRAFT":
        return build_family_experience_assets()
    return build_family_experience_assets(
        status="PUBLISHED",
        reviewer="prompt-reviewer",
        effective_at=NOW - timedelta(days=1),
    )


async def _approval(decision: ReleaseDecision):
    store = InMemoryReleaseControlStore(
        signature_verifier=_SignatureVerifier(),
        clock=lambda: NOW,
    )
    return await store.approve(
        decision,
        actor_id="operator-release-1",
        idempotency_key=f"approve:{decision.candidate_id}:{decision.model}",
        reason="评测、合规和人工闸门已经复核",
        signature="valid-signature",
        signature_algorithm="external-kms-v1",
    )


@pytest.mark.asyncio
async def test_release_bundle_binds_model_assets_evaluation_and_human_approval() -> None:
    decision = _decision()
    approval = await _approval(decision)
    assets = _assets()

    first = build_family_experience_release_bundle(
        assets=assets,
        decision=decision,
        approval=approval,
        provider_registry=_provider_registry(),
        data_class="MINOR_PERSONAL_DATA",
    )
    replay = build_family_experience_release_bundle(
        assets=assets,
        decision=decision,
        approval=approval,
        provider_registry=_provider_registry(),
        data_class="MINOR_PERSONAL_DATA",
    )

    assert first == replay
    assert first.bundle_id == replay.bundle_id
    assert first.prompt_version == "family-companion.v1"
    assert first.schema_version == "family-experience-draft.v1"
    assert first.report_ref == decision.report_ref
    assert first.approval_signature_ref == approval.signature_ref
    assert first.human_gate_rule == "REVIEW_REQUIRED"
    assert first.draft_only is True
    assert first.may_mutate_business_state is False


@pytest.mark.asyncio
async def test_release_bundle_rejects_unpublished_assets_or_blocked_decision() -> None:
    admitted = _decision()
    approval = await _approval(admitted)
    with pytest.raises(FamilyExperienceReleaseBundleError, match="PUBLISHED_ASSETS_REQUIRED"):
        build_family_experience_release_bundle(
            assets=_assets(status="DRAFT"),
            decision=admitted,
            approval=approval,
            provider_registry=_provider_registry(),
            data_class="MINOR_PERSONAL_DATA",
        )

    blocked = _decision(status="BLOCKED")
    with pytest.raises(
        FamilyExperienceReleaseBundleError,
        match="ADMITTED_RELEASE_DECISION_REQUIRED",
    ):
        build_family_experience_release_bundle(
            assets=_assets(),
            decision=blocked,
            approval=approval,
            provider_registry=_provider_registry(),
            data_class="MINOR_PERSONAL_DATA",
        )


@pytest.mark.asyncio
async def test_release_bundle_rejects_model_or_human_gate_mismatch() -> None:
    mismatched = _decision(model="different-model")
    approval = await _approval(mismatched)
    with pytest.raises(FamilyExperienceReleaseBundleError, match="PROVIDER_MODEL_MISMATCH"):
        build_family_experience_release_bundle(
            assets=_assets(),
            decision=mismatched,
            approval=approval,
            provider_registry=_provider_registry(),
            data_class="MINOR_PERSONAL_DATA",
        )

    decision = _decision()
    approval = await _approval(decision)
    assets = _assets()
    unsafe_assets = FamilyExperienceAssetBundle(
        prompt=assets.prompt,
        schema=replace(assets.schema, human_gate_rule="NOT_REQUIRED"),
        system_policy=assets.system_policy,
        knowledge=assets.knowledge,
    )
    with pytest.raises(FamilyExperienceReleaseBundleError, match="HUMAN_GATE_REQUIRED"):
        build_family_experience_release_bundle(
            assets=unsafe_assets,
            decision=decision,
            approval=approval,
            provider_registry=_provider_registry(),
            data_class="MINOR_PERSONAL_DATA",
        )

    with pytest.raises(FamilyExperienceReleaseBundleError, match="DATA_CLASS_INVALID"):
        build_family_experience_release_bundle(
            assets=assets,
            decision=decision,
            approval=approval,
            provider_registry=_provider_registry(),
            data_class="UNKNOWN",  # type: ignore[arg-type]
        )
