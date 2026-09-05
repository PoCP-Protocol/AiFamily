from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..application.context import ActorContext
from ..application.evidence_receipt_health import (
    EvidenceReceiptHealthConflictError,
    EvidenceReceiptHealthUnavailableError,
    get_evidence_receipt_health,
)
from ..application.evidence_verification import (
    EVIDENCE_VERIFICATION_POLICY_VERSION,
    evidence_record_hash,
)
from ..application.product_package_evidence_admission import (
    admit_product_package_evidence,
)
from ..application.product_package_source_resolution import (
    ProductPackageSourceResolutionError,
)
from ..application.product_package_submission import (
    PRODUCT_PACKAGE_READ_PERMISSION,
    ProductPackageSubmissionError,
    ProductPackageSubmissionForbiddenError,
)
from ..domain.entities import Evidence
from ..domain.errors import (
    ProductIntelligenceConflictError,
    ProductIntelligenceNotFoundError,
)
from ..domain.evidence_verification import (
    EvidenceVerificationReceipt,
    EvidenceVerificationReceiptContent,
    evidence_verification_receipt_hash,
)
from ..domain.product_package_draft import ProductPackageEvidenceRequirement
from ..infrastructure.evidence_verification_repository import (
    EvidenceVerificationReceiptRow,
    SqlAlchemyEvidenceVerificationReceiptRepository,
)
from ..infrastructure.product_package_evidence_reader import (
    SqlAlchemyProductPackageEvidenceReader,
)
from ..infrastructure.sqlalchemy_models import Base as ProductBase
from ..infrastructure.sqlalchemy_repository import SqlAlchemyProductIntelligenceRepository

NOW = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)


def context(*, allowed: bool = True, tenant_scope: str = "tenant-a") -> ActorContext:
    return ActorContext(
        actor_id="operator:product-reviewer",
        actor_type="HUMAN",
        tenant_scope=tenant_scope,
        permissions=(
            frozenset({PRODUCT_PACKAGE_READ_PERMISSION})
            if allowed
            else frozenset()
        ),
    )


def evidence(**changes: object) -> Evidence:
    values: dict[str, object] = {
        "id": "evidence:one",
        "version": 3,
        "created_at": NOW - timedelta(days=2),
        "updated_at": NOW - timedelta(days=1),
        "created_by": "human:researcher",
        "tenant_scope": "tenant-a",
        "status": "ACTIVE",
        "description": "Redacted interview record",
        "evidence_ref": "source:interview:redacted:one",
    }
    values.update(changes)
    return Evidence.model_validate(values)


def receipt(source: Evidence | None = None, **changes: object) -> EvidenceVerificationReceipt:
    source = source or evidence()
    values: dict[str, object] = {
        "receipt_id": "receipt:one",
        "tenant_scope": "tenant-a",
        "evidence_id": source.id,
        "evidence_version": source.version,
        "evidence_record_hash": evidence_record_hash(source),
        "evidence_ref": source.evidence_ref,
        "claim_scope": ("claim:parent-action-friction",),
        "verification_methods": (
            "SOURCE_OPENED",
            "EVIDENCE_RECORD_HASH_MATCHED",
        ),
        "applicability_scope": ("family-education-product-research",),
        "criteria_refs": ("evidence-policy:source-integrity:v1",),
        "verification_purpose": "product_package_admission",
        "verification_policy_version": EVIDENCE_VERIFICATION_POLICY_VERSION,
        "task_id": "task:one",
        "proposal_id": "proposal:one",
        "decision_id": "decision:one",
        "request_id": "request:one",
        "verifier_actor_id": "operator:evidence-reviewer",
        "decision_reason": "Source and record hash reviewed",
        "verified_at": NOW - timedelta(hours=2),
        "valid_until": NOW + timedelta(days=30),
        "recorded_at": NOW - timedelta(hours=1),
        "request_hash": "request-hash:one",
    }
    values.update(changes)
    content = EvidenceVerificationReceiptContent.model_validate(values)
    return EvidenceVerificationReceipt(
        **content.model_dump(mode="python"),
        receipt_hash=evidence_verification_receipt_hash(content),
    )


class FakeReader:
    def __init__(
        self,
        *,
        receipt_value: EvidenceVerificationReceipt | Exception | None = None,
        evidence_value: Evidence | Exception | None = None,
    ) -> None:
        self.receipt_value = receipt_value or receipt()
        self.evidence_value = evidence_value or evidence()
        self.receipt_calls = 0
        self.evidence_calls = 0

    async def load_receipt(
        self,
        receipt_id: str,
        tenant_scope: str,
    ) -> EvidenceVerificationReceipt:
        self.receipt_calls += 1
        if isinstance(self.receipt_value, Exception):
            raise self.receipt_value
        if receipt_id != self.receipt_value.receipt_id or (
            tenant_scope != self.receipt_value.tenant_scope
        ):
            raise ProductIntelligenceNotFoundError(
                "evidence_verification_receipt_not_found"
            )
        return self.receipt_value

    async def load_evidence(self, entity_id: str, tenant_scope: str) -> Evidence:
        self.evidence_calls += 1
        if isinstance(self.evidence_value, Exception):
            raise self.evidence_value
        if entity_id != self.evidence_value.id or tenant_scope != self.evidence_value.tenant_scope:
            raise ProductIntelligenceNotFoundError("evidence_not_found")
        return self.evidence_value


@pytest.mark.asyncio
async def test_current_policy_pass_remains_unknown_without_supersession_index() -> None:
    reader = FakeReader()
    result = await get_evidence_receipt_health(
        reader,
        context(),
        receipt_id=" receipt:one ",
        now=NOW,
    )

    assert result.current_policy_precheck == "PASS"
    assert result.receipt_traceability_health == "UNKNOWN"
    assert result.supersession_state == "UNKNOWN_NOT_IN_CONTRACT"
    assert result.reason_codes == (
        "SUPERSESSION_STATE_UNKNOWN_NOT_IN_CONTRACT",
        "CLAIM_APPLICABILITY_NOT_EVALUATED",
        "AUTHORITATIVE_ADMISSION_NOT_PERFORMED",
    )
    assert result.claim_applicability_evaluated is False
    assert result.authoritative_admission is False
    assert result.final_revalidation_required is True
    assert result.precheck_policy_version == "family-education-evidence-admission:v1"
    assert result.diagnostic_scope == "RECEIPT_SOURCE_INTEGRITY"
    assert reader.receipt_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("receipt_changes", "source_changes", "expected"),
    [
        ({"valid_until": NOW}, {}, "PRODUCT_PACKAGE_RECEIPT_EXPIRED"),
        (
            {
                "verified_at": NOW + timedelta(hours=1),
                "recorded_at": NOW + timedelta(hours=1),
            },
            {},
            "PRODUCT_PACKAGE_RECEIPT_NOT_YET_EFFECTIVE",
        ),
        (
            {"verification_policy_version": "unsupported:v9"},
            {},
            "PRODUCT_PACKAGE_RECEIPT_POLICY_UNSUPPORTED",
        ),
        (
            {"verification_methods": ("SOURCE_OPENED",)},
            {},
            "PRODUCT_PACKAGE_RECEIPT_METHODS_INSUFFICIENT",
        ),
        (
            {"supersedes_receipt_id": "receipt:older"},
            {},
            "PRODUCT_PACKAGE_RECEIPT_SUPERSESSION_UNSUPPORTED",
        ),
        ({}, {"status": "RETIRED"}, "PRODUCT_PACKAGE_EVIDENCE_SOURCE_NOT_ACTIVE"),
        ({}, {"version": 4}, "PRODUCT_PACKAGE_EVIDENCE_VERSION_DRIFT"),
        ({}, {"evidence_ref": "source:changed"}, "PRODUCT_PACKAGE_EVIDENCE_REF_DRIFT"),
        (
            {},
            {"description": "Content drifted after verification"},
            "PRODUCT_PACKAGE_EVIDENCE_RECORD_HASH_DRIFT",
        ),
    ],
)
async def test_policy_failures_are_discrete_unhealthy_observations(
    receipt_changes: dict[str, object],
    source_changes: dict[str, object],
    expected: str,
) -> None:
    original = evidence()
    receipt_value = receipt(original, **receipt_changes)
    source_value = evidence(**source_changes)
    reader = FakeReader(receipt_value=receipt_value, evidence_value=source_value)
    result = await get_evidence_receipt_health(
        reader,
        context(),
        receipt_id="receipt:one",
        now=NOW,
    )

    assert result.current_policy_precheck == "FAIL"
    assert result.receipt_traceability_health == "UNHEALTHY"
    assert result.reason_codes == (expected,)
    assert result.authoritative_admission is False

    requirement = ProductPackageEvidenceRequirement(
        receipt_locator="receipt:one",
        claim_type="FAMILY_NEED",
        required_claim_refs=("claim:parent-action-friction",),
        required_applicability_refs=("family-education-product-research",),
    )
    with pytest.raises(ProductPackageSourceResolutionError) as caught:
        await admit_product_package_evidence(
            FakeReader(receipt_value=receipt_value, evidence_value=source_value),
            tenant_scope="tenant-a",
            requirements=(requirement,),
            now=NOW,
        )
    assert caught.value.code == expected


@pytest.mark.asyncio
async def test_missing_live_source_is_an_unhealthy_broken_lineage_observation() -> None:
    reader = FakeReader(
        evidence_value=ProductIntelligenceNotFoundError("evidence_not_found")
    )
    result = await get_evidence_receipt_health(
        reader,
        context(),
        receipt_id="receipt:one",
        now=NOW,
    )
    assert result.current_policy_precheck == "FAIL"
    assert result.receipt_traceability_health == "UNHEALTHY"
    assert result.reason_codes == ("PRODUCT_PACKAGE_EVIDENCE_SOURCE_NOT_FOUND",)


@pytest.mark.asyncio
async def test_authorization_and_input_fail_before_health_source_reads() -> None:
    reader = FakeReader()
    with pytest.raises(ProductPackageSubmissionForbiddenError):
        await get_evidence_receipt_health(
            reader,
            context(allowed=False),
            receipt_id="receipt:one",
            now=NOW,
        )
    assert reader.receipt_calls == 0
    assert reader.evidence_calls == 0

    with pytest.raises(ProductPackageSubmissionError, match="ID_REQUIRED"):
        await get_evidence_receipt_health(reader, context(), receipt_id=" ", now=NOW)
    assert reader.receipt_calls == 0


@pytest.mark.asyncio
async def test_tenant_scoped_missing_receipt_stays_not_found() -> None:
    reader = FakeReader()
    with pytest.raises(ProductIntelligenceNotFoundError):
        await get_evidence_receipt_health(
            reader,
            context(tenant_scope="tenant-b"),
            receipt_id="receipt:one",
            now=NOW,
        )


@pytest.mark.asyncio
async def test_corrupt_persisted_receipt_is_conflict_not_unknown() -> None:
    reader = FakeReader(
        receipt_value=ProductIntelligenceConflictError(
            "evidence_verification_persisted_payload_invalid"
        )
    )
    with pytest.raises(EvidenceReceiptHealthConflictError):
        await get_evidence_receipt_health(
            reader,
            context(),
            receipt_id="receipt:one",
            now=NOW,
        )


@pytest.mark.asyncio
async def test_naive_server_clock_is_rejected_before_repository_io() -> None:
    reader = FakeReader()
    with pytest.raises(EvidenceReceiptHealthUnavailableError, match="CLOCK_INVALID"):
        await get_evidence_receipt_health(
            reader,
            context(),
            receipt_id="receipt:one",
            now=NOW.replace(tzinfo=None),
        )
    assert reader.receipt_calls == 0


@pytest.mark.asyncio
async def test_sql_reader_preserves_tenant_boundary_and_detects_scalar_tamper() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(ProductBase.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        source = evidence()
        await SqlAlchemyProductIntelligenceRepository(session).save_evidence(source)
        await SqlAlchemyEvidenceVerificationReceiptRepository(
            session
        ).create_receipt_if_absent(receipt(source))
        await session.commit()

    async with factory() as session:
        result = await get_evidence_receipt_health(
            SqlAlchemyProductPackageEvidenceReader(session),
            context(),
            receipt_id="receipt:one",
            now=NOW,
        )
        assert result.current_policy_precheck == "PASS"
        with pytest.raises(ProductIntelligenceNotFoundError):
            await get_evidence_receipt_health(
                SqlAlchemyProductPackageEvidenceReader(session),
                context(tenant_scope="tenant-b"),
                receipt_id="receipt:one",
                now=NOW,
            )

    async with factory() as session:
        row = await session.scalar(select(EvidenceVerificationReceiptRow))
        assert row is not None
        row.receipt_hash = "0" * 64
        await session.commit()
    async with factory() as session:
        with pytest.raises(EvidenceReceiptHealthConflictError):
            await get_evidence_receipt_health(
                SqlAlchemyProductPackageEvidenceReader(session),
                context(),
                receipt_id="receipt:one",
                now=NOW,
            )

    await engine.dispose()
