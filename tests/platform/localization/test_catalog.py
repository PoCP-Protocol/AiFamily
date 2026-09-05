import json
from pathlib import Path

import pytest

from backend.platform.localization import (
    LocaleArtifactKind,
    LocaleCatalog,
    LocaleCatalogError,
    LocaleContext,
    LocaleDimension,
    LocaleReviewStatus,
    LocalizedArtifact,
)


def context(**overrides) -> LocaleContext:
    values = {
        "user_locale": "fr-FR",
        "content_locale": "fr-FR",
        "model_locale": "fr-FR",
        "policy_locale": "fr-FR",
        "fallback_locales": ("en-US",),
    }
    values.update(overrides)
    return LocaleContext(**values)


def artifact(**overrides) -> LocalizedArtifact:
    values = {
        "concept_id": "policy.pause_action",
        "artifact_kind": LocaleArtifactKind.HUMAN_GATE,
        "locale": "en-US",
        "version": "1.0.0",
        "text": "Pause and ask for human review.",
        "review_status": LocaleReviewStatus.REVIEWED,
    }
    values.update(overrides)
    return LocalizedArtifact(**values)


def test_catalog_resolves_by_concept_and_explicit_fallback() -> None:
    catalog = LocaleCatalog([artifact()])

    resolved = catalog.resolve(
        context(),
        LocaleDimension.POLICY,
        concept_id="policy.pause_action",
        artifact_kind=LocaleArtifactKind.HUMAN_GATE,
        version="1.0.0",
    )

    assert resolved.locale == "en-US"
    assert resolved.concept_id == "policy.pause_action"
    assert len(catalog) == 1


def test_catalog_normalizes_string_enums_from_transport_payloads() -> None:
    catalog = LocaleCatalog(
        [
            artifact(
                artifact_kind="HUMAN_GATE",
                review_status="REVIEWED",
            )
        ]
    )

    resolved = catalog.resolve(
        context(),
        LocaleDimension.POLICY,
        concept_id="policy.pause_action",
        artifact_kind="HUMAN_GATE",
        version="1.0.0",
    )

    assert resolved.review_status is LocaleReviewStatus.REVIEWED
    assert resolved.artifact_kind is LocaleArtifactKind.HUMAN_GATE


def test_localized_artifact_transport_contract_round_trips() -> None:
    original = artifact()

    restored = LocalizedArtifact.from_dict(original.as_dict())

    assert restored == original


def test_localized_artifact_transport_contract_rejects_unknown_fields() -> None:
    payload = artifact().as_dict()

    with pytest.raises(LocaleCatalogError, match="FIELDS_UNSUPPORTED"):
        LocalizedArtifact.from_dict({**payload, "unexpected": "value"})


@pytest.mark.parametrize("field", ("concept_id", "version", "text"))
def test_localized_artifact_rejects_non_string_contract_fields(field: str) -> None:
    payload = artifact().as_dict()
    payload[field] = 1

    with pytest.raises(LocaleCatalogError, match="FIELDS_UNSUPPORTED"):
        LocalizedArtifact.from_dict(payload)


def test_unreviewed_artifact_is_not_returned_even_when_technically_available() -> None:
    catalog = LocaleCatalog([artifact(review_status=LocaleReviewStatus.DRAFT)])

    with pytest.raises(LocaleCatalogError, match="UNAVAILABLE"):
        catalog.resolve(
            context(),
            LocaleDimension.POLICY,
            concept_id="policy.pause_action",
            artifact_kind=LocaleArtifactKind.HUMAN_GATE,
            version="1.0.0",
        )


def test_catalog_does_not_silently_select_another_version() -> None:
    catalog = LocaleCatalog([artifact(version="2.0.0")])

    with pytest.raises(LocaleCatalogError, match="UNAVAILABLE"):
        catalog.resolve(
            context(),
            LocaleDimension.POLICY,
            concept_id="policy.pause_action",
            artifact_kind=LocaleArtifactKind.HUMAN_GATE,
            version="1.0.0",
        )


def test_coverage_gate_requires_reviewed_entries_for_every_concept_and_locale() -> None:
    catalog = LocaleCatalog(
        [
            artifact(locale="en-US"),
            artifact(locale="zh-CN", text="请暂停并转人工复核。"),
            artifact(
                concept_id="policy.stop_action",
                locale="en-US",
                review_status=LocaleReviewStatus.DRAFT,
            ),
        ]
    )

    report = catalog.evaluate_coverage(
        concept_ids=("policy.pause_action", "policy.stop_action"),
        locales=("en-US", "zh-CN"),
        artifact_kind=LocaleArtifactKind.HUMAN_GATE,
        version="1.0.0",
    )

    assert report.complete is False
    assert report.missing == (
        ("policy.stop_action", "en-US"),
        ("policy.stop_action", "zh-CN"),
    )


def test_coverage_gate_deduplicates_inputs_and_passes_complete_reviewed_set() -> None:
    catalog = LocaleCatalog(
        [
            artifact(locale="en-US"),
            artifact(locale="zh-CN", text="请暂停并转人工复核。"),
        ]
    )

    report = catalog.evaluate_coverage(
        concept_ids=("policy.pause_action", "policy.pause_action"),
        locales=("en-US", "en-us", "zh-CN"),
        artifact_kind=LocaleArtifactKind.HUMAN_GATE,
        version="1.0.0",
    )

    assert report.complete is True
    assert report.required_concepts == ("policy.pause_action",)
    assert report.required_locales == ("en-US", "zh-CN")


def test_duplicate_concept_locale_kind_and_version_is_rejected() -> None:
    with pytest.raises(LocaleCatalogError, match="DUPLICATE"):
        LocaleCatalog([artifact(), artifact()])


def test_localized_artifact_schema_is_explicitly_versioned_and_reviewed() -> None:
    schema = json.loads(
        (
            Path(__file__).resolve().parents[3] / "contracts/schemas/localized-artifact.schema.json"
        ).read_text(encoding="utf-8")
    )

    assert schema["required"] == [
        "concept_id",
        "artifact_kind",
        "locale",
        "version",
        "text",
        "review_status",
    ]
    assert "REVIEWED" in schema["properties"]["review_status"]["enum"]
