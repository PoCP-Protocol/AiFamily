from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.model_gateway.contracts import AiProvenance, ModelDraft
from backend.intelligence.product_management.ai_product_port import (
    ModelDraftProductPackageAdapter,
    ProductPackageDraftError,
)

_GENERATED_AT = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


def _model_draft() -> ModelDraft:
    return ModelDraft(
        output={"product_line": "family-growth", "steps": ["observe", "try"]},
        provenance=AiProvenance(
            provider_id="fake-provider",
            model="multimodal-test",
            model_version="1",
            prompt_version="prompt-v1",
            schema_version="product-package-v1",
            context_snapshot_ref="context:123",
            latency_ms=42,
            data_class="SYNTHETIC",
            use_case="PRODUCT_PACKAGE_DRAFT",
            generated_at=_GENERATED_AT,
        ),
    )


def _adapt(**overrides: object):
    values: dict[str, object] = {
        "package_id": "package-21-day-v1",
        "product_id": "growth-21-day",
        "version": "0.1.0",
        "model_attempt_ref": "attempt:abc",
        "evidence_refs": ("research:need-1",),
        "assumptions": ("家庭愿意尝试每日一个小行动",),
        "next_validation": "用五个匿名家庭验证第一个行动的可执行性",
        "owner": "product:p1",
        "expires_at": _GENERATED_AT + timedelta(days=14),
    }
    values.update(overrides)
    return ModelDraftProductPackageAdapter().adapt(_model_draft(), **values)


def test_adapter_returns_auditable_draft_without_business_mutation() -> None:
    package = _adapt()

    assert package.status == "DRAFT"
    assert package.requires_human_confirmation is True
    assert package.may_mutate_business_state is False
    assert package.model_attempt_ref == "attempt:abc"
    assert package.evidence_refs == ("research:need-1",)
    assert package.provenance.context_snapshot_ref == "context:123"
    assert package.output == {"product_line": "family-growth", "steps": ["observe", "try"]}


@pytest.mark.parametrize(
    ("field", "value", "error"),
    (
        ("evidence_refs", (), "EVIDENCE_REQUIRED"),
        ("assumptions", (), "ASSUMPTIONS_REQUIRED"),
        ("model_attempt_ref", "", "FIELDS_REQUIRED"),
        ("next_validation", "", "FIELDS_REQUIRED"),
    ),
)
def test_adapter_requires_review_metadata(field: str, value: object, error: str) -> None:
    with pytest.raises(ProductPackageDraftError, match=error):
        _adapt(**{field: value})


def test_adapter_rejects_non_draft_model_output() -> None:
    non_draft = replace(_model_draft(), status="APPROVED")

    with pytest.raises(ProductPackageDraftError, match="DRAFT_ONLY"):
        ModelDraftProductPackageAdapter().adapt(
            non_draft,
            package_id="package-1",
            product_id="product-1",
            version="0.1.0",
            model_attempt_ref="attempt:1",
            evidence_refs=("evidence:1",),
            assumptions=("assumption:1",),
            next_validation="validate with an anonymous pilot",
            owner="product:p1",
            expires_at=_GENERATED_AT + timedelta(days=1),
        )


def test_expiry_must_follow_provenance_and_be_timezone_aware() -> None:
    with pytest.raises(ProductPackageDraftError, match="FOLLOW_PROVENANCE"):
        _adapt(expires_at=_GENERATED_AT)
    with pytest.raises(ProductPackageDraftError, match="TIMEZONE_AWARE"):
        _adapt(expires_at=datetime(2026, 9, 1))
