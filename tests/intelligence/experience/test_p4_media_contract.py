"""P4 contract evidence for media, sharing and growth achievements.

These tests intentionally have two layers.  The schema layer proves that the
target contract is explicit and rejects unsafe shapes.  The runtime layer is
an acceptance gate: it stays red until the production-shaped Experience
runtime exposes the same separated objects and lifecycle boundaries.  It must
not be changed to a skip or a synthetic pass merely because the implementation
is not wired yet.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_ROOT = REPO_ROOT / "contracts" / "schemas"

MEDIA_SCHEMAS = {
    "MediaAsset": SCHEMA_ROOT / "media-asset.schema.json",
    "MediaTranscript": SCHEMA_ROOT / "media-transcript.schema.json",
    "MediaEvidence": SCHEMA_ROOT / "media-evidence.schema.json",
}

COMMON_ROOT_FIELDS = {
    "tenant_id",
    "family_id",
    "subject_ids",
    "purpose",
    "retention",
    "deletion",
    "correlation_id",
    "causation_id",
}


def _matches(instance: Any, schema: dict[str, Any], root: dict[str, Any]) -> bool:
    if "$ref" in schema:
        schema = root["$defs"][schema["$ref"].rsplit("/", 1)[-1]]
    if "const" in schema and instance != schema["const"]:
        return False
    if "enum" in schema and instance not in schema["enum"]:
        return False
    if "properties" in schema and isinstance(instance, dict):
        return all(
            key not in instance or _matches(value, subschema, root)
            for key, subschema in schema["properties"].items()
            for value in [instance.get(key)]
        )
    return True


def _validate(instance: Any, schema: dict[str, Any], root: dict[str, Any]) -> None:
    if "$ref" in schema:
        schema = root["$defs"][schema["$ref"].rsplit("/", 1)[-1]]
    if "const" in schema:
        assert instance == schema["const"]
    if "enum" in schema:
        assert instance in schema["enum"]
    expected = schema.get("type")
    if expected:
        expected_types = (expected,) if isinstance(expected, str) else tuple(expected)
        assert any(
            {
                "object": isinstance(instance, dict),
                "array": isinstance(instance, list),
                "string": isinstance(instance, str),
                "boolean": isinstance(instance, bool),
                "null": instance is None,
            }.get(kind, False)
            for kind in expected_types
        )
    if isinstance(instance, dict):
        required = set(schema.get("required", ()))
        assert required <= instance.keys()
        if schema.get("additionalProperties") is False:
            assert set(instance) <= set(schema.get("properties", {}))
        for key, subschema in schema.get("properties", {}).items():
            if key in instance:
                _validate(instance[key], subschema, root)
    if isinstance(instance, list):
        assert len(instance) >= schema.get("minItems", 0)
        if schema.get("uniqueItems"):
            assert len({json.dumps(item, sort_keys=True) for item in instance}) == len(instance)
        for item in instance:
            _validate(item, schema.get("items", {}), root)
    if isinstance(instance, str):
        assert len(instance) >= schema.get("minLength", 0)
    for rule in schema.get("allOf", ()):
        if _matches(instance, rule.get("if", {}), root):
            _validate(instance, rule.get("then", {}), root)


def _p4_examples() -> dict[str, dict[str, Any]]:
    consent = {
        "consent_version": "consent.v1",
        "status": "GRANTED",
        "effective_from": "2026-08-30T00:00:00Z",
        "effective_to": None,
        "purpose": "growth_support",
    }
    retention = {"expires_at": "2027-08-30T00:00:00Z", "on_expiry": "DELETE"}
    return {
        "MediaAsset": {
            "asset_id": "asset-1",
            "tenant_id": "tenant-1",
            "family_id": "family-1",
            "subject_ids": ["child-1"],
            "subject_scope": "CHILD",
            "media_type": "IMAGE",
            "storage_ref": "media:asset-1",
            "original": True,
            "purpose": "growth_support",
            "consent": consent,
            "retention": retention,
            "deletion": {"deletion_id": "delete-1", "cascade_ids": ["asset-1"]},
            "derived_asset_ids": ["transcript-1"],
            "creator_role": "CHILD",
            "commercial_use": False,
            "age_band": "CHILD",
            "moderation_status": "PENDING",
            "visibility": "FAMILY_PRIVATE",
            "correlation_id": "corr-1",
            "causation_id": "cause-1",
        },
        "MediaTranscript": {
            "transcript_id": "transcript-1",
            "source_asset_id": "asset-1",
            "tenant_id": "tenant-1",
            "family_id": "family-1",
            "subject_ids": ["child-1"],
            "purpose": "growth_support",
            "consent": consent,
            "retention": retention,
            "deletion": {
                "deletion_id": "delete-2",
                "source_deletion_id": "delete-1",
                "cascade_ids": ["transcript-1"],
            },
            "locale": "zh-CN",
            "text": "一起读完一页。",
            "transcript_status": "DRAFT",
            "provenance": {
                "kind": "AI_DRAFT",
                "source_ref": "asset-1",
                "model_attempt_ref": "attempt-1",
                "schema_version": "transcript.v1",
            },
            "correlation_id": "corr-1",
            "causation_id": "cause-1",
        },
        "MediaEvidence": {
            "evidence_id": "evidence-1",
            "tenant_id": "tenant-1",
            "family_id": "family-1",
            "subject_ids": ["child-1"],
            "source_refs": ["asset-1", "transcript-1"],
            "evidence_kind": "REFLECTION",
            "observation": "家庭记录了一次共同阅读。",
            "status": "FAMILY_CONFIRMED",
            "human_verification_ref": None,
            "purpose": "growth_support",
            "consent": consent,
            "retention": retention,
            "deletion": {"deletion_id": "delete-3", "source_refs": ["asset-1", "transcript-1"]},
            "provenance": "family-confirmation-1",
            "may_mutate_business_state": False,
            "correlation_id": "corr-1",
            "causation_id": "cause-1",
        },
        "FamilyContentShare": {
            "share_id": "share-1",
            "tenant_id": "tenant-1",
            "family_id": "family-1",
            "recipient_family_id": "family-1",
            "source_ref": "asset-1",
            "source_type": "MEDIA_ASSET",
            "subject_ids": ["child-1"],
            "requested_by_role": "GUARDIAN",
            "purpose": "family_sharing",
            "consent": {**consent, "purpose": "family_sharing"},
            "audience": "FAMILY_MEMBERS",
            "recipient_ids": [],
            "moderation_status": "APPROVED",
            "moderation_ref": "review-1",
            "child_safe_review": True,
            "commercial_context": "NONE",
            "visibility": "FAMILY_PRIVATE",
            "retention": retention,
            "deletion": {
                "deletion_id": "delete-share-1",
                "source_deletion_id": "delete-1",
                "cascade_ids": ["share-1"],
            },
            "idempotency_key": "tenant-1:share-1",
            "correlation_id": "corr-1",
            "causation_id": "cause-1",
        },
        "GrowthAchievement": {
            "achievement_id": "achievement-1",
            "tenant_id": "tenant-1",
            "family_id": "family-1",
            "subject_ids": ["child-1"],
            "subject_scope": "CHILD",
            "key": "FIRST_STEP",
            "basis": "ACTION_COMPLETED",
            "evidence_refs": ["evidence-1"],
            "title": "第一步",
            "message": "完成了一步自己选择的小行动。",
            "visibility": "FAMILY_PRIVATE",
            "comparison_scope": "NONE",
            "commercial_reward": "NONE",
            "purpose": "growth_support",
            "consent": consent,
            "retention": retention,
            "deletion": {"deletion_id": "delete-achievement-1", "source_refs": ["evidence-1"]},
            "idempotency_key": "tenant-1:achievement-1",
            "earned_at": "2026-08-30T01:00:00Z",
            "correlation_id": "corr-1",
            "causation_id": "cause-1",
        },
    }


def _schema(name: str) -> dict[str, Any]:
    return json.loads(MEDIA_SCHEMAS[name].read_text(encoding="utf-8"))


def _required(schema: dict[str, Any]) -> set[str]:
    return set(schema["required"])


def _properties(schema: dict[str, Any]) -> dict[str, Any]:
    return schema["properties"]


def test_three_media_objects_are_separate_contract_documents() -> None:
    schemas = {name: _schema(name) for name in MEDIA_SCHEMAS}

    assert len({schema["$id"] for schema in schemas.values()}) == 3
    assert {schema["title"] for schema in schemas.values()} == {
        "AiFamily MediaAsset",
        "AiFamily MediaTranscript",
        "AiFamily MediaEvidence",
    }
    assert _required(schemas["MediaAsset"]) >= {"asset_id", "storage_ref", "original"}
    assert _required(schemas["MediaTranscript"]) >= {"transcript_id", "source_asset_id", "text"}
    assert _required(schemas["MediaEvidence"]) >= {
        "evidence_id",
        "source_refs",
        "observation",
        "may_mutate_business_state",
    }


@pytest.mark.parametrize("name", [*MEDIA_SCHEMAS, "FamilyContentShare", "GrowthAchievement"])
def test_every_p4_record_carries_isolation_retention_and_deletion_envelope(name: str) -> None:
    filename = {
        "MediaAsset": "media-asset.schema.json",
        "MediaTranscript": "media-transcript.schema.json",
        "MediaEvidence": "media-evidence.schema.json",
        "FamilyContentShare": "family-content-share.schema.json",
        "GrowthAchievement": "growth-achievement.schema.json",
    }[name]
    schema = json.loads((SCHEMA_ROOT / filename).read_text(encoding="utf-8"))

    assert schema["additionalProperties"] is False
    assert _required(schema) >= COMMON_ROOT_FIELDS
    assert "consent" in _required(schema) or "consent_version" in _required(schema)
    assert "expires_at" in _required(schema["$defs"]["retention"])
    assert schema["$defs"]["retention"]["properties"]["on_expiry"]["const"] == "DELETE"


def test_media_transcript_and_evidence_keep_independent_deletion_lineage() -> None:
    asset = _schema("MediaAsset")
    transcript = _schema("MediaTranscript")
    evidence = _schema("MediaEvidence")

    assert "derived_asset_ids" in _required(asset)
    assert "source_deletion_id" in _required(transcript["$defs"]["deletion"])
    assert "source_refs" in _required(evidence["$defs"]["deletion"])
    assert "source_asset_id" in _required(transcript)
    assert "source_refs" in _required(evidence)


def test_minor_media_is_not_a_commercial_input() -> None:
    schema = _schema("MediaAsset")
    child_rule = next(
        rule
        for rule in schema["allOf"]
        if rule["if"]["properties"]["creator_role"]["const"] == "CHILD"
    )
    assert child_rule["then"]["properties"]["commercial_use"]["const"] is False


def test_family_share_is_private_reviewed_and_never_public() -> None:
    schema = json.loads(
        (SCHEMA_ROOT / "family-content-share.schema.json").read_text(encoding="utf-8")
    )
    properties = _properties(schema)

    assert properties["visibility"]["const"] == "FAMILY_PRIVATE"
    assert properties["commercial_context"]["const"] == "NONE"
    assert "PUBLIC" not in properties["audience"].get("enum", [])
    assert "moderation_ref" in _required(schema)
    assert schema["$defs"]["consent"]["properties"]["purpose"]["const"] == "family_sharing"


def test_achievement_is_evidence_bound_and_not_an_engagement_score() -> None:
    schema = json.loads(
        (SCHEMA_ROOT / "growth-achievement.schema.json").read_text(encoding="utf-8")
    )
    properties = _properties(schema)
    forbidden = {
        "watch_time",
        "screen_time",
        "likes",
        "followers",
        "streak",
        "rank",
        "score",
        "family_total",
        "commercial_value",
    }

    assert not forbidden.intersection(properties)
    assert properties["comparison_scope"]["const"] == "NONE"
    assert properties["commercial_reward"]["const"] == "NONE"
    assert _required(schema) >= {"basis", "evidence_refs", "visibility", "deletion"}
    assert set(properties["basis"]["enum"]) <= {
        "ACTION_COMPLETED",
        "REFLECTION_SUBMITTED",
        "RELATIONSHIP_FEEDBACK",
        "CONTRIBUTION_VERIFIED",
    }


def test_p4_positive_examples_validate_against_each_contract() -> None:
    examples = _p4_examples()
    schemas = {
        **{name: _schema(name) for name in MEDIA_SCHEMAS},
        "FamilyContentShare": json.loads(
            (SCHEMA_ROOT / "family-content-share.schema.json").read_text(encoding="utf-8")
        ),
        "GrowthAchievement": json.loads(
            (SCHEMA_ROOT / "growth-achievement.schema.json").read_text(encoding="utf-8")
        ),
    }

    for name, payload in examples.items():
        _validate(payload, schemas[name], schemas[name])


@pytest.mark.parametrize(
    ("name", "mutator"),
    [
        ("MediaAsset", lambda item: item.update(commercial_use=True)),
        ("MediaTranscript", lambda item: item["deletion"].pop("source_deletion_id")),
        ("FamilyContentShare", lambda item: item.update(moderation_status="PENDING")),
        ("FamilyContentShare", lambda item: item.update(audience="PUBLIC")),
        ("GrowthAchievement", lambda item: item.update(watch_time=900)),
        ("GrowthAchievement", lambda item: item.update(commercial_reward="POINTS")),
    ],
)
def test_p4_reverse_examples_are_rejected(name: str, mutator: Any) -> None:
    schemas = {
        **{key: _schema(key) for key in MEDIA_SCHEMAS},
        "FamilyContentShare": json.loads(
            (SCHEMA_ROOT / "family-content-share.schema.json").read_text(encoding="utf-8")
        ),
        "GrowthAchievement": json.loads(
            (SCHEMA_ROOT / "growth-achievement.schema.json").read_text(encoding="utf-8")
        ),
    }
    payload = _p4_examples()[name]
    mutator(payload)

    with pytest.raises(AssertionError):
        _validate(payload, schemas[name], schemas[name])


def test_runtime_exposes_separate_media_contracts() -> None:
    """Acceptance gate: one merged media ref is not production equivalence."""

    from backend.intelligence.experience import contracts as runtime_contracts

    missing = [name for name in MEDIA_SCHEMAS if not hasattr(runtime_contracts, name)]
    assert not missing, (
        "P4 runtime gap: separate media contracts are missing "
        f"({', '.join(missing)}); ExperienceMediaRef cannot satisfy the "
        "MediaAsset/MediaTranscript/MediaEvidence deletion and provenance boundary."
    )


def test_runtime_exposes_reviewed_family_share_lifecycle() -> None:
    """Acceptance gate: no share endpoint/object may bypass review or scope."""

    from backend.intelligence.experience import contracts as runtime_contracts

    assert hasattr(runtime_contracts, "FamilyContentShare"), (
        "P4 runtime gap: FamilyContentShare is not implemented; a frontend "
        "adapter or a raw media reference cannot prove same-family authorization, "
        "review admission, idempotency, or deletion revocation."
    )


def test_runtime_achievement_contract_carries_non_engagement_basis() -> None:
    """Acceptance gate: existing evidence refs alone do not define anti-gaming rules."""

    from backend.intelligence.experience.achievement import Achievement

    fields = set(getattr(Achievement, "__dataclass_fields__", {}))
    assert {"basis", "visibility", "comparison_scope", "commercial_reward"} <= fields, (
        "P4 runtime gap: Achievement lacks explicit action/relationship basis "
        "and non-comparative/non-commercial fields; do not infer them from "
        "message text or playback telemetry."
    )
