"""Build human-gated courseware candidates from a course lesson."""

from __future__ import annotations

from ..domain.course_content import CourseLesson
from ..domain.courseware_draft import CoursewareDraft


def build_courseware_draft_candidate(
    *,
    lesson: CourseLesson,
    tenant_scope: str,
    product_package_version_ref: str,
    course_system_version_ref: str,
    asset_bundle_version_ref: str,
    kind: str,
    prompt_ref: str,
    model_provenance_ref: str,
    output_locator: str,
) -> CoursewareDraft:
    """Create a DRAFT candidate; generation and approval remain separate gates."""

    return CoursewareDraft(
        draft_id=f"courseware-draft:{lesson.lesson_id}:{kind.lower()}",
        tenant_scope=tenant_scope,
        product_package_version_ref=product_package_version_ref,
        course_system_version_ref=course_system_version_ref,
        lesson_sequence=lesson.sequence,
        asset_bundle_version_ref=asset_bundle_version_ref,
        kind=kind,
        prompt_ref=prompt_ref,
        model_provenance_ref=model_provenance_ref,
        output_locator=output_locator,
    )


__all__ = ["build_courseware_draft_candidate"]
