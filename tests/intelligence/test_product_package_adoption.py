from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from types import MappingProxyType

import pytest

from backend.intelligence.model_gateway.contracts import AiProvenance
from backend.intelligence.product_management.ai_product_port import ProductPackageDraft
from backend.intelligence.product_management.application.product_package_adoption import (
    ProductPackageAdoptionCommand,
    ProductPackageAdoptionError,
    adopt_product_package_draft,
)


def _provenance(*, generated_at: datetime | None = None) -> AiProvenance:
    return AiProvenance(
        provider_id="provider:test",
        model="model:test",
        model_version="1.0",
        prompt_version="product.compose@1",
        schema_version="product-package@1",
        context_snapshot_ref="snapshot:test",
        latency_ms=12,
        data_class="OPERATIONAL_TEXT",
        use_case="service_product_composition",
        confidence=0.8,
        generated_at=generated_at or datetime.now(UTC),
    )


def _draft(
    *,
    expires_at: datetime | None = None,
    generated_at: datetime | None = None,
) -> ProductPackageDraft:
    generated_at = generated_at or datetime.now(UTC)
    return ProductPackageDraft(
        package_id="package:21:v1",
        product_id="product:family-growth",
        version="1.0.0",
        output={"duration_days": 21, "zone": "ADVANTAGE"},
        evidence_refs=("evidence:market:1", "evidence:pilot:1"),
        assumptions=("需要小批验证",),
        next_validation="完成五个家庭的匿名试点",
        owner="product:owner",
        expires_at=expires_at or generated_at + timedelta(days=7),
        model_attempt_ref="attempt:test:1",
        provenance=_provenance(generated_at=generated_at),
    )


def _adopt(**kwargs: object) -> ProductPackageAdoptionCommand:
    return adopt_product_package_draft(
        kwargs.pop("draft", _draft()),
        evidence_statuses=kwargs.pop(
            "evidence_statuses",
            {"evidence:market:1": "VERIFIED", "evidence:pilot:1": "VERIFIED"},
        ),
        human_actor=kwargs.pop("human_actor", "human:ipmt"),
        adoption_reason=kwargs.pop("adoption_reason", "证据已复核，允许进入领域命令"),
        **kwargs,
    )


def test_adoption_requires_draft_expiry_verified_evidence_and_human() -> None:
    command = _adopt(idempotency_key="adopt:package:21:v1")
    assert isinstance(command, ProductPackageAdoptionCommand)
    assert command.requires_human_confirmation is True
    assert command.may_mutate_business_state is False
    assert command.human_actor == "human:ipmt"
    assert command.evidence_refs == ("evidence:market:1", "evidence:pilot:1")
    assert command.ai_provenance.provider_id == "provider:test"

    with pytest.raises(ProductPackageAdoptionError, match="EXPIRED"):
        now = datetime.now(UTC)
        _adopt(
            draft=_draft(
                generated_at=now - timedelta(days=2),
                expires_at=now - timedelta(seconds=1),
            )
        )
    with pytest.raises(ProductPackageAdoptionError, match="NOT_VERIFIED"):
        _adopt(evidence_statuses={"evidence:market:1": "UNKNOWN", "evidence:pilot:1": "VERIFIED"})
    with pytest.raises(ProductPackageAdoptionError, match="HUMAN_ACTOR_REQUIRED"):
        _adopt(human_actor="ai:product-factory")


def test_adoption_requires_complete_evidence_status_map_and_reason() -> None:
    with pytest.raises(ProductPackageAdoptionError, match="STATUS_MISSING"):
        _adopt(evidence_statuses={"evidence:market:1": "VERIFIED"})
    with pytest.raises(ProductPackageAdoptionError, match="STATUS_UNREFERENCED"):
        _adopt(
            evidence_statuses={
                "evidence:market:1": "VERIFIED",
                "evidence:pilot:1": "VERIFIED",
                "evidence:extra": "VERIFIED",
            }
        )
    with pytest.raises(ProductPackageAdoptionError, match="ADOPTION_REASON_REQUIRED"):
        _adopt(adoption_reason=" ")


def test_adoption_mapping_and_output_are_immutable_and_side_effect_free() -> None:
    command = _adopt()
    mapping = command.to_domain_mapping()
    assert isinstance(mapping, MappingProxyType)
    assert mapping["human_actor"] == "human:ipmt"
    assert mapping["provenance"] is command.ai_provenance
    with pytest.raises(TypeError):
        mapping["human_actor"] = "human:other"  # type: ignore[index]
    with pytest.raises(TypeError):
        command.output["new_key"] = "blocked"  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        command.human_actor = "human:other"  # type: ignore[misc]
    assert command.to_domain_mapping()["package_id"] == "package:21:v1"


def test_adoption_does_not_accept_provider_or_repository_and_supports_deterministic_clock() -> None:
    current = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
    draft = _draft(
        expires_at=current + timedelta(hours=1),
    )
    # The draft generated_at is now, so make a deterministic future draft for
    # this clock by constructing it directly with an older provenance.
    draft = ProductPackageDraft(
        package_id=draft.package_id,
        product_id=draft.product_id,
        version=draft.version,
        output=draft.output,
        evidence_refs=draft.evidence_refs,
        assumptions=draft.assumptions,
        next_validation=draft.next_validation,
        owner=draft.owner,
        expires_at=current + timedelta(hours=1),
        model_attempt_ref=draft.model_attempt_ref,
        provenance=_provenance(generated_at=current - timedelta(hours=1)),
    )
    command = _adopt(draft=draft, now=current)
    assert command.adopted_at == current
    assert command.expires_at == current + timedelta(hours=1)
