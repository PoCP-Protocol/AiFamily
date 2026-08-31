from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from ..application.context import ActorContext
from ..application.evidence_verification import evidence_record_hash
from ..application.product_package_evidence_admission import (
    ReceiptBackedProductPackageSourceResolver,
    admit_product_package_evidence,
    revalidate_product_package_evidence,
)
from ..application.product_package_source_resolution import (
    ProductPackageDesignIntent,
    ProductPackageSourceResolutionError,
    ResolvedProductPackageSource,
)
from ..application.product_package_submission import ProductPackageSubmissionInput
from ..domain.entities import Evidence
from ..domain.evidence_verification import (
    EvidenceVerificationReceipt,
    EvidenceVerificationReceiptContent,
    evidence_verification_receipt_hash,
)
from ..domain.product_package_draft import ProductPackageEvidenceRequirement

NOW = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)


def _evidence(**changes: object) -> Evidence:
    values: dict[str, object] = {
        "id": "evidence:one",
        "version": 3,
        "created_at": NOW - timedelta(days=2),
        "updated_at": NOW - timedelta(days=1),
        "created_by": "human:researcher",
        "tenant_scope": "tenant-a",
        "status": "ACTIVE",
        "description": "redacted family research record",
        "evidence_ref": "source:research:one",
    }
    values.update(changes)
    return Evidence.model_validate(values)


def _receipt(evidence: Evidence | None = None, **changes: object) -> EvidenceVerificationReceipt:
    source = evidence or _evidence()
    values: dict[str, object] = {
        "receipt_id": "verification-receipt:one",
        "tenant_scope": source.tenant_scope,
        "evidence_id": source.id,
        "evidence_version": source.version,
        "evidence_record_hash": evidence_record_hash(source),
        "evidence_ref": source.evidence_ref,
        "claim_scope": ("claim:family-need",),
        "verification_methods": ("SOURCE_OPENED", "EVIDENCE_RECORD_HASH_MATCHED"),
        "applicability_scope": (
            "role:PARENT_GUARDIAN",
            "age:AGE_9_12",
            "scenario:HOME_ROUTINE",
            "region:CN",
            "language:zh-CN",
        ),
        "criteria_refs": ("evidence-policy:source-integrity:v1",),
        "verification_purpose": "product_package_admission",
        "verification_policy_version": "product-evidence-verification:v1",
        "task_id": "task:one",
        "proposal_id": "proposal:one",
        "decision_id": "decision:one",
        "request_id": "request:one",
        "verifier_actor_id": "operator:evidence-reviewer",
        "decision_reason": "source and scope reviewed",
        "verified_at": NOW - timedelta(hours=1),
        "valid_until": NOW + timedelta(days=30),
        "recorded_at": NOW - timedelta(minutes=50),
        "request_hash": "a" * 64,
    }
    values.update(changes)
    content = EvidenceVerificationReceiptContent.model_validate(values)
    return EvidenceVerificationReceipt(
        **content.model_dump(mode="python"),
        receipt_hash=evidence_verification_receipt_hash(content),
    )


def _requirement(**changes: object) -> ProductPackageEvidenceRequirement:
    values: dict[str, object] = {
        "receipt_locator": "verification-receipt:one",
        "claim_type": "FAMILY_NEED",
        "required_claim_refs": ("claim:family-need",),
        "required_applicability_refs": (
            "role:PARENT_GUARDIAN",
            "age:AGE_9_12",
        ),
    }
    values.update(changes)
    return ProductPackageEvidenceRequirement.model_validate(values)


class _Reader:
    def __init__(
        self,
        receipts: tuple[EvidenceVerificationReceipt, ...],
        evidence: tuple[Evidence, ...],
    ) -> None:
        self.receipts = {item.receipt_id: item for item in receipts}
        self.evidence = {item.id: item for item in evidence}

    async def load_receipt(
        self,
        receipt_id: str,
        tenant_scope: str,
    ) -> EvidenceVerificationReceipt:
        receipt = self.receipts[receipt_id]
        assert receipt.tenant_scope == tenant_scope
        return receipt

    async def load_evidence(self, entity_id: str, tenant_scope: str) -> Evidence:
        evidence = self.evidence[entity_id]
        assert evidence.tenant_scope == tenant_scope
        return evidence


@pytest.mark.asyncio
async def test_receipt_and_current_source_create_explainable_admission_snapshot() -> None:
    evidence = _evidence()
    receipt = _receipt(evidence)
    admissions = await admit_product_package_evidence(
        _Reader((receipt,), (evidence,)),
        tenant_scope="tenant-a",
        requirements=(_requirement(),),
        now=NOW,
    )

    assert len(admissions) == 1
    admission = admissions[0]
    assert admission.admission_status == "ADMITTED"
    assert admission.reason_codes == ()
    assert admission.receipt_hash == receipt.receipt_hash
    assert admission.evidence_record_hash == evidence_record_hash(evidence)
    assert admission.required_claim_refs == ("claim:family-need",)
    assert admission.admission_policy_version == "family-education-evidence-admission:v1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("receipt_changes", "code"),
    [
        ({"valid_until": NOW}, "RECEIPT_EXPIRED"),
        ({"recorded_at": NOW + timedelta(minutes=1)}, "RECEIPT_NOT_YET_EFFECTIVE"),
        (
            {"verification_policy_version": "unsupported-policy:v9"},
            "RECEIPT_POLICY_UNSUPPORTED",
        ),
        (
            {"supersedes_receipt_id": "verification-receipt:old"},
            "RECEIPT_SUPERSESSION_UNSUPPORTED",
        ),
        ({"verification_methods": ("SOURCE_OPENED",)}, "RECEIPT_METHODS_INSUFFICIENT"),
    ],
)
async def test_receipt_policy_and_time_fail_closed(
    receipt_changes: dict[str, object],
    code: str,
) -> None:
    evidence = _evidence()
    with pytest.raises(ProductPackageSourceResolutionError, match=code):
        await admit_product_package_evidence(
            _Reader((_receipt(evidence, **receipt_changes),), (evidence,)),
            tenant_scope="tenant-a",
            requirements=(_requirement(),),
            now=NOW,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("evidence", "code"),
    [
        (_evidence(status="RETIRED"), "SOURCE_NOT_ACTIVE"),
        (_evidence(version=4), "VERSION_DRIFT"),
        (_evidence(evidence_ref="source:changed"), "REF_DRIFT"),
        (_evidence(description="record changed"), "RECORD_HASH_DRIFT"),
    ],
)
async def test_current_evidence_drift_fails_closed(evidence: Evidence, code: str) -> None:
    original = _evidence()
    with pytest.raises(ProductPackageSourceResolutionError, match=code):
        await admit_product_package_evidence(
            _Reader((_receipt(original),), (evidence,)),
            tenant_scope="tenant-a",
            requirements=(_requirement(),),
            now=NOW,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("requirement", "code"),
    [
        (
            _requirement(required_claim_refs=("claim:not-reviewed",)),
            "CLAIM_SCOPE_NOT_COVERED",
        ),
        (
            _requirement(required_applicability_refs=("age:AGE_13_15",)),
            "APPLICABILITY_SCOPE_NOT_COVERED",
        ),
    ],
)
async def test_claim_and_applicability_require_exact_coverage(
    requirement: ProductPackageEvidenceRequirement,
    code: str,
) -> None:
    evidence = _evidence()
    with pytest.raises(ProductPackageSourceResolutionError, match=code):
        await admit_product_package_evidence(
            _Reader((_receipt(evidence),), (evidence,)),
            tenant_scope="tenant-a",
            requirements=(requirement,),
            now=NOW,
        )


@pytest.mark.asyncio
async def test_duplicate_locator_and_underlying_evidence_are_rejected() -> None:
    evidence = _evidence()
    receipt = _receipt(evidence)
    with pytest.raises(ProductPackageSourceResolutionError, match="LOCATORS_REQUIRED_AND_UNIQUE"):
        await admit_product_package_evidence(
            _Reader((receipt,), (evidence,)),
            tenant_scope="tenant-a",
            requirements=(_requirement(), _requirement()),
            now=NOW,
        )

    second = _receipt(
        evidence,
        receipt_id="verification-receipt:two",
        task_id="task:two",
        proposal_id="proposal:two",
        decision_id="decision:two",
        request_id="request:two",
        request_hash="b" * 64,
    )
    with pytest.raises(ProductPackageSourceResolutionError, match="DUPLICATE_UNDERLYING"):
        await admit_product_package_evidence(
            _Reader((receipt, second), (evidence,)),
            tenant_scope="tenant-a",
            requirements=(
                _requirement(),
                _requirement(receipt_locator="verification-receipt:two"),
            ),
            now=NOW,
        )


@pytest.mark.asyncio
async def test_revalidation_detects_snapshot_or_package_window_change() -> None:
    evidence = _evidence()
    receipt = _receipt(evidence)
    reader = _Reader((receipt,), (evidence,))
    admissions = await admit_product_package_evidence(
        reader,
        tenant_scope="tenant-a",
        requirements=(_requirement(),),
        now=NOW,
    )
    await revalidate_product_package_evidence(
        reader,
        tenant_scope="tenant-a",
        admissions=admissions,
        package_expires_at=NOW + timedelta(days=7),
        now=NOW,
    )
    with pytest.raises(ProductPackageSourceResolutionError, match="EXPIRES_BEFORE_PACKAGE"):
        await revalidate_product_package_evidence(
            reader,
            tenant_scope="tenant-a",
            admissions=admissions,
            package_expires_at=NOW + timedelta(days=31),
            now=NOW,
        )
    changed_reader = _Reader(
        (receipt,),
        (_evidence(description="record changed"),),
    )
    with pytest.raises(ProductPackageSourceResolutionError, match="RECORD_HASH_DRIFT"):
        await revalidate_product_package_evidence(
            changed_reader,
            tenant_scope="tenant-a",
            admissions=admissions,
            package_expires_at=NOW + timedelta(days=7),
            now=NOW,
        )


def _intent() -> ProductPackageDesignIntent:
    return ProductPackageDesignIntent(
        source_draft_locator="source-draft:one",
        concept_id="concept:one",
        zone_assessment_id="assessment:one",
        product_kind="MICRO_CAMP",
        duration_days=21,
        primary_contradiction="understanding-action gap",
        demand_ref="demand:one",
        market_insight_refs=("insight:one",),
        competitor_evidence_refs=("competitor:one",),
        component_ids=("component:one",),
        skill_ids=("skill:one",),
        success_metric_ids=("metric:one",),
        guardrail_ids=("guardrail:one",),
        stop_conditions=("stop:safety",),
        pause_policy="parent can pause",
        human_gate_policy="human review required",
        evidence_locators=("verification-receipt:one",),
        assumptions=("small cohort needed",),
        unknowns=("age rhythm differs",),
        next_validation="run a redacted pilot",
        requested_ttl_hours=168,
    )


class _InnerResolver:
    async def resolve(self, *, context, intent, now) -> ResolvedProductPackageSource:
        return ResolvedProductPackageSource(
            source_draft_locator=intent.source_draft_locator,
            submission=ProductPackageSubmissionInput(
                concept_id=intent.concept_id,
                zone_assessment_id=intent.zone_assessment_id,
                upstream_decision_draft_ref="model-draft:one",
                product_kind=intent.product_kind,
                duration_days=intent.duration_days,
                primary_contradiction=intent.primary_contradiction,
                demand_ref=intent.demand_ref,
                market_insight_refs=intent.market_insight_refs,
                competitor_evidence_refs=intent.competitor_evidence_refs,
                component_ids=intent.component_ids,
                skill_ids=intent.skill_ids,
                success_metric_ids=intent.success_metric_ids,
                guardrail_ids=intent.guardrail_ids,
                stop_conditions=intent.stop_conditions,
                pause_policy=intent.pause_policy,
                human_gate_policy=intent.human_gate_policy,
                evidence_refs=intent.evidence_locators,
                evidence_requirements=(_requirement(),),
                evidence_admissions=(),
                assumptions=intent.assumptions,
                unknowns=intent.unknowns,
                next_validation=intent.next_validation,
                expires_at=now + timedelta(days=60),
                source_provenance_ref="model-draft:one",
                model_ref="model:test@1",
                prompt_use_case_version="service-product-composition@1",
                confidence=0.8,
            ),
        )


@pytest.mark.asyncio
async def test_receipt_backed_resolver_overwrites_only_with_trusted_admission() -> None:
    evidence = _evidence()
    receipt = _receipt(evidence)
    resolver = ReceiptBackedProductPackageSourceResolver(
        inner=_InnerResolver(),
        reader=_Reader((receipt,), (evidence,)),
    )
    resolved = await resolver.resolve(
        context=ActorContext(
            actor_id="human:owner",
            actor_type="HUMAN",
            tenant_scope="tenant-a",
        ),
        intent=_intent(),
        now=NOW,
    )

    assert resolved.submission.evidence_admissions[0].receipt_id == receipt.receipt_id
    assert resolved.submission.expires_at == receipt.valid_until
    assert resolved.submission.evidence_refs == (receipt.receipt_id,)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "trusted_requirements",
    [
        (),
        (_requirement(receipt_locator="verification-receipt:wrong"),),
        (_requirement(), _requirement(receipt_locator="verification-receipt:extra")),
        (_requirement(), _requirement()),
    ],
)
async def test_receipt_backed_resolver_requires_trusted_requirements_for_all_locators(
    trusted_requirements: tuple[ProductPackageEvidenceRequirement, ...],
) -> None:
    class _MismatchedInner:
        async def resolve(self, *, context, intent, now):
            resolved = await _InnerResolver().resolve(
                context=context,
                intent=intent,
                now=now,
            )
            return replace(
                resolved,
                submission=replace(
                    resolved.submission,
                    evidence_requirements=trusted_requirements,
                ),
            )

    class _UnreadableReader:
        async def load_receipt(self, receipt_id, tenant_scope):
            raise AssertionError("admission must not read before requirements match")

        async def load_evidence(self, entity_id, tenant_scope):
            raise AssertionError("admission must not read before requirements match")

    resolver = ReceiptBackedProductPackageSourceResolver(
        inner=_MismatchedInner(),
        reader=_UnreadableReader(),
    )
    with pytest.raises(
        ProductPackageSourceResolutionError,
        match="TRUSTED_EVIDENCE_REQUIREMENTS_MISMATCH",
    ):
        await resolver.resolve(
            context=ActorContext(
                actor_id="human:owner",
                actor_type="HUMAN",
                tenant_scope="tenant-a",
            ),
            intent=_intent(),
            now=NOW,
        )
