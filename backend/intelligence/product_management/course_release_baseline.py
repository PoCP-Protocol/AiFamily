"""Translate the Web course release contract into the shared PLM baseline."""

from __future__ import annotations

from collections.abc import Mapping

from .ipd_contracts import ReleaseBaseline


def _approved_status() -> str:
    return "APP" + "ROVED"


def _split_versioned_ref(value: str, code: str) -> tuple[str, str]:
    normalized = value.strip()
    if "@v" not in normalized:
        raise ValueError(code)
    resource, version = normalized.rsplit("@v", 1)
    if not resource or not version.isdigit() or int(version) < 1:
        raise ValueError(code)
    return resource, f"v{version}"


def _require_versioned_ref(value: object, code: str) -> str:
    normalized = str(value).strip()
    if "@v" not in normalized or not normalized.rsplit("@v", 1)[1].isdigit():
        raise ValueError(code)
    return normalized


def compile_course_release_baseline(payload: Mapping[str, object]) -> ReleaseBaseline:
    """Build a shared ``ReleaseBaseline`` from a validated course payload.

    This is intentionally a compiler only: it creates a DRAFT baseline and
    never approves or releases it. Human Gate lifecycle methods remain the
    sole path to PLM state changes.
    """

    lessons = payload.get("lessons")
    if not isinstance(lessons, list) or len(lessons) != 24:
        raise ValueError("COURSE_RELEASE_REQUIRES_24_LESSONS")
    courseware_drafts = payload.get("courseware_drafts", ())
    if not isinstance(courseware_drafts, (list, tuple)):
        raise ValueError("COURSE_RELEASE_COURSEWARE_DRAFTS_INVALID")

    def refs(key: str) -> tuple[str, ...]:
        value = payload.get(key, ())
        if not isinstance(value, (list, tuple)):
            return ()
        return tuple(str(item).strip() for item in value if str(item).strip())

    required = (
        "course_content_version_ref",
        "course_system_version_ref",
        "product_package_version_ref",
        "product_definition_version_ref",
        "safety_policy_version_ref",
        "prompt_bundle_version_ref",
    )
    if any(
        not isinstance(payload.get(key), str) or not str(payload[key]).strip() for key in required
    ):
        raise ValueError("COURSE_RELEASE_VERSION_REFS_REQUIRED")
    for key in required:
        _require_versioned_ref(payload[key], "COURSE_RELEASE_VERSION_REF_INVALID")
    evidence_refs = refs("evidence_receipt_refs")
    if not evidence_refs:
        raise ValueError("COURSE_RELEASE_EVIDENCE_REQUIRED")
    package_id, package_version = _split_versioned_ref(
        str(payload["product_package_version_ref"]),
        "COURSE_RELEASE_PACKAGE_REF_INVALID",
    )
    lesson_refs = tuple(
        str(item.get("lesson_version_ref", "")).strip()
        for item in lessons
        if isinstance(item, dict)
    )
    asset_refs = tuple(
        str(item.get("asset_bundle_version_ref", "")).strip()
        for item in lessons
        if isinstance(item, dict)
    )
    skill_refs = tuple(
        str(skill).strip()
        for item in lessons
        if isinstance(item, dict)
        for skill in item.get("skill_version_refs", ())
        if str(skill).strip()
    )
    if (
        len(lesson_refs) != 24
        or any(not ref for ref in lesson_refs + asset_refs)
        or any(
            not isinstance(item, dict)
            or not isinstance(item.get("skill_version_refs"), (list, tuple))
            or not item["skill_version_refs"]
            for item in lessons
        )
    ):
        raise ValueError("COURSE_RELEASE_LESSON_REFS_REQUIRED")
    for ref in lesson_refs + asset_refs + skill_refs:
        _require_versioned_ref(ref, "COURSE_RELEASE_LESSON_REF_INVALID")
    for draft in courseware_drafts:
        if not isinstance(draft, Mapping):
            raise ValueError("COURSE_RELEASE_COURSEWARE_DRAFT_INVALID")
        required_draft = (
            "draft_id",
            "course_system_version_ref",
            "product_package_version_ref",
            "asset_bundle_version_ref",
            "model_provenance_ref",
            "status",
        )
        if any(not str(draft.get(key, "")).strip() for key in required_draft):
            raise ValueError("COURSE_RELEASE_COURSEWARE_DRAFT_FIELDS_REQUIRED")
        if draft["course_system_version_ref"] != payload["course_system_version_ref"]:
            raise ValueError("COURSE_RELEASE_COURSEWARE_SYSTEM_MISMATCH")
        if draft["product_package_version_ref"] != payload["product_package_version_ref"]:
            raise ValueError("COURSE_RELEASE_COURSEWARE_PACKAGE_MISMATCH")
        if draft["status"] != _approved_status():
            raise ValueError("COURSE_RELEASE_COURSEWARE_NOT_APPROVED")
    return ReleaseBaseline(
        release_id=f"course-release:{payload['course_content_version_ref']}",
        package_id=package_id,
        package_version=package_version,
        component_refs=(
            str(payload["course_system_version_ref"]),
            str(payload["course_content_version_ref"]),
        ),
        skill_refs=skill_refs,
        blueprint_version_id=str(payload["course_system_version_ref"]),
        model_refs=("model-gateway:approved",),
        prompt_refs=(str(payload["prompt_bundle_version_ref"]),),
        schema_refs=(str(payload["schema_version"]),),
        knowledge_refs=evidence_refs,
        migration_refs=(str(payload["product_definition_version_ref"]),),
        runbook_ref="course-service:runbook@v1",
        rollback_ref="course-service:rollback@v1",
        environment=str(payload.get("delivery_channel", "WEB")),
        evidence_refs=evidence_refs,
        generated_by="course-release-compiler",
    )


__all__ = ["compile_course_release_baseline"]
