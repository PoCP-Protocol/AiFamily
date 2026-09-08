"""Model-Gateway boundary for auditable courseware candidates."""

from __future__ import annotations

from collections.abc import Sequence

from backend.domains.product_intelligence.application.courseware_draft_factory import (
    build_courseware_draft_candidate,
)
from backend.domains.product_intelligence.domain.course_content import CourseLesson
from backend.domains.product_intelligence.domain.courseware_draft import CoursewareDraft
from backend.intelligence.model_gateway.contracts import ModelDraft, StructuredRequest
from backend.intelligence.model_gateway.gateway import ModelGateway

COURSEWARE_USE_CASE = "product.courseware.generate"
COURSEWARE_SCHEMA_VERSION = "courseware-candidate.v1"
COURSEWARE_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["title", "outline", "family_action", "evidence_refs"],
    "properties": {
        "title": {"type": "string"},
        "outline": {"type": "array", "items": {"type": "string"}},
        "family_action": {"type": "string"},
        "evidence_refs": {"type": "array", "items": {"type": "string"}},
    },
}


def build_courseware_request(
    *, lesson: CourseLesson, evidence_refs: Sequence[str], context_snapshot_ref: str
) -> StructuredRequest:
    refs = tuple(ref.strip() for ref in evidence_refs if ref.strip())
    if not refs:
        raise ValueError("COURSEWARE_EVIDENCE_REQUIRED")
    if len(set(refs)) != len(refs):
        raise ValueError("COURSEWARE_EVIDENCE_DUPLICATE")
    return StructuredRequest(
        use_case=COURSEWARE_USE_CASE,
        prompt_version="courseware-generator.v1",
        schema_version=COURSEWARE_SCHEMA_VERSION,
        data_class="OPERATIONAL_TEXT",
        payload={
            "lesson": {
                "sequence": lesson.sequence,
                "title": lesson.title,
                "knowledge_point": lesson.knowledge_point,
                "action_task": lesson.action_task,
            },
            "instruction": "生成课件候选，不生成事实，不做疗效承诺。",
        },
        output_schema=COURSEWARE_OUTPUT_SCHEMA,
        context_snapshot_ref=context_snapshot_ref,
        input_refs=refs,
    )


def validate_courseware_draft(draft: ModelDraft, *, evidence_refs: Sequence[str]) -> ModelDraft:
    if draft.status != "DRAFT" or draft.may_mutate_business_state:
        raise ValueError("COURSEWARE_MODEL_DRAFT_ONLY")
    output = draft.output
    if not isinstance(output.get("title"), str) or not output["title"].strip():
        raise ValueError("COURSEWARE_TITLE_REQUIRED")
    if not isinstance(output.get("outline"), list) or not output["outline"]:
        raise ValueError("COURSEWARE_OUTLINE_REQUIRED")
    if not isinstance(output.get("family_action"), str) or not output["family_action"].strip():
        raise ValueError("COURSEWARE_ACTION_REQUIRED")
    refs = output.get("evidence_refs")
    allowed = {ref.strip() for ref in evidence_refs}
    if not isinstance(refs, list) or not refs or not set(refs).issubset(allowed):
        raise ValueError("COURSEWARE_EVIDENCE_REFERENCE_NOT_ALLOWED")
    return draft


async def generate_courseware_draft(
    gateway: ModelGateway,
    *,
    provider_id: str,
    lesson: CourseLesson,
    evidence_refs: Sequence[str],
    context_snapshot_ref: str,
    tenant_scope: str,
    product_package_version_ref: str,
    course_system_version_ref: str,
    asset_bundle_version_ref: str,
    kind: str = "DECK",
) -> tuple[ModelDraft, CoursewareDraft]:
    request = build_courseware_request(
        lesson=lesson, evidence_refs=evidence_refs, context_snapshot_ref=context_snapshot_ref
    )
    model_draft = validate_courseware_draft(
        await gateway.generate_structured(request, provider_id=provider_id),
        evidence_refs=evidence_refs,
    )
    candidate = build_courseware_draft_candidate(
        lesson=lesson,
        tenant_scope=tenant_scope,
        product_package_version_ref=product_package_version_ref,
        course_system_version_ref=course_system_version_ref,
        asset_bundle_version_ref=asset_bundle_version_ref,
        kind=kind,
        prompt_ref="prompt:courseware-generator@v1",
        model_provenance_ref=model_draft.provenance.model,
        output_locator=f"draft://courseware/{lesson.lesson_id}/{kind.lower()}",
    )
    return model_draft, candidate


__all__ = ["build_courseware_request", "generate_courseware_draft", "validate_courseware_draft"]
