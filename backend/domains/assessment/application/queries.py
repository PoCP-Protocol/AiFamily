"""Read-model queries — ported from `AssessmentService.getProjection` and
`GrowthHypothesisService.getProjection`.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.errors import AssessmentForbiddenError
from ..domain.value_objects import Ui02AssessmentAvailability
from .ports import AssessmentInterpretationPort, AssessmentRepositoryPort


@dataclass(frozen=True)
class GetUi02ProjectionQuery:
    family_id: str
    tenant_id: str
    actor_id: str


@dataclass(frozen=True)
class GetUi03ProjectionQuery:
    family_id: str
    tenant_id: str
    actor_id: str


@dataclass(frozen=True)
class GetAssessmentResultProjectionQuery:
    family_id: str
    tenant_id: str
    actor_id: str


@dataclass(frozen=True)
class GetSupportLoopProjectionQuery:
    family_id: str
    tenant_id: str
    actor_id: str


class AssessmentQueryHandler:
    def __init__(
        self, repository: AssessmentRepositoryPort, interpretation: AssessmentInterpretationPort
    ):
        self._repository = repository
        self._interpretation = interpretation

    async def get_ui02_projection(self, query: GetUi02ProjectionQuery) -> dict:
        await self._repository.assert_tenant_family_scope(
            query.tenant_id, query.family_id, query.actor_id
        )
        policy_allows = await self._repository.tenant_allows_page(query.tenant_id, "UI-02")
        subjects = await self._repository.load_assessable_subjects(query.family_id)
        tool = await self._repository.load_active_tool("FAMILY_SUPPORT_NEEDS")
        sessions = await self._repository.load_recent_sessions(
            query.tenant_id, query.family_id, limit=10
        )

        mapped_subjects = [
            {
                "person_id": subject["person_id"],
                "display_name": subject["display_name"],
                "availability": "AVAILABLE" if subject["consent_granted"] else "CONSENT_REQUIRED",
            }
            for subject in subjects
        ]
        availability: Ui02AssessmentAvailability
        if not policy_allows:
            availability = "POLICY_BLOCKED"
        elif any(subject["availability"] == "AVAILABLE" for subject in mapped_subjects):
            availability = "AVAILABLE"
        elif mapped_subjects:
            availability = "CONSENT_REQUIRED"
        else:
            availability = "NO_SUBJECT"

        return {
            "projection_version": "UI02_FAMILY_ASSESSMENT_V1",
            "tenant_id": query.tenant_id,
            "family_id": query.family_id,
            "availability": availability,
            "subjects": mapped_subjects,
            "tool": tool.model_dump(mode="json") if tool else None,
            "sessions": [session.model_dump(mode="json") for session in sessions],
            "named_actions": {
                "start": "START_ASSESSMENT",
                "save_response": "SAVE_ASSESSMENT_RESPONSE",
                "submit": "SUBMIT_ASSESSMENT",
            },
        }

    async def get_ui03_projection(self, query: GetUi03ProjectionQuery) -> dict:
        await self._repository.assert_tenant_family_scope(
            query.tenant_id, query.family_id, query.actor_id
        )
        if not await self._repository.tenant_allows_page(query.tenant_id, "UI-03"):
            return _ui03_projection(query.tenant_id, query.family_id, "POLICY_BLOCKED", None)

        evidence = await self._repository.load_hypothesis_evidence(query.family_id, query.tenant_id)
        if evidence is None:
            return _ui03_projection(
                query.tenant_id, query.family_id, "NO_SUBMITTED_ASSESSMENT", None
            )

        interpretation = await self._interpretation.interpret(
            query.family_id, evidence, "DEEP_AI_INTERPRETATION"
        )
        hypothesis = _map_hypothesis(evidence, interpretation)
        return _ui03_projection(
            query.tenant_id, query.family_id, "READY", hypothesis, ai_state="MODEL_DRAFT_READY"
        )

    async def get_assessment_result_projection(
        self, query: GetAssessmentResultProjectionQuery
    ) -> dict:
        """Return the latest submitted assessment as a family-scoped read model.

        The result is derived from the submitted session and its evidence
        lineage. It does not create a second ``FamilyNeed``/``Consent`` object,
        write a canonical Fact, or calculate a family score. Consent is checked
        again at read time so withdrawal cannot leave a stale result visible.
        """
        await self._repository.assert_tenant_family_scope(
            query.tenant_id, query.family_id, query.actor_id
        )
        if not await self._repository.tenant_allows_page(query.tenant_id, "UI-02"):
            return _assessment_result_projection(
                query.tenant_id, query.family_id, "POLICY_BLOCKED", None
            )

        evidence = await self._repository.load_hypothesis_evidence(query.family_id, query.tenant_id)
        if evidence is None:
            return _assessment_result_projection(
                query.tenant_id, query.family_id, "NO_RESULT", None
            )

        try:
            await self._repository.assert_subject_consent(
                query.family_id, evidence.subject_person_id, "ASSESSMENT"
            )
        except AssessmentForbiddenError:
            # The repository port exposes the domain error rather than a
            # boolean, preserving fail-closed behavior without leaking the
            # submitted result after consent withdrawal.
            return _assessment_result_projection(
                query.tenant_id, query.family_id, "CONSENT_REQUIRED", None
            )

        interpretation = await self._interpretation.interpret(
            query.family_id, evidence, "ASSESSMENT_RESULT_EXPLANATION"
        )
        return _assessment_result_projection(
            query.tenant_id,
            query.family_id,
            "READY",
            _map_assessment_result(evidence, interpretation),
        )

    async def get_support_loop_projection(self, query: GetSupportLoopProjectionQuery) -> dict:
        """Read the family's chosen step and latest reflection without side effects."""
        await self._repository.assert_tenant_family_scope(
            query.tenant_id, query.family_id, query.actor_id
        )
        if not await self._repository.tenant_allows_page(query.tenant_id, "UI-03"):
            return _support_loop_projection(
                query.tenant_id, query.family_id, "POLICY_BLOCKED", None, None
            )

        evidence = await self._repository.load_hypothesis_evidence(query.family_id, query.tenant_id)
        if evidence is None:
            return _support_loop_projection(
                query.tenant_id, query.family_id, "NO_RESULT", None, None
            )
        try:
            await self._repository.assert_subject_consent(
                query.family_id, evidence.subject_person_id, "ASSESSMENT"
            )
        except AssessmentForbiddenError:
            return _support_loop_projection(
                query.tenant_id, query.family_id, "CONSENT_REQUIRED", None, None
            )

        state = await self._repository.load_support_loop_state(
            query.tenant_id, query.family_id, evidence.assessment_session_id
        )
        return _support_loop_projection(
            query.tenant_id,
            query.family_id,
            "READY",
            evidence.assessment_session_id,
            state,
        )


def _ui03_projection(
    tenant_id: str,
    family_id: str,
    availability: str,
    hypothesis: dict | None,
    ai_state: str = "NOT_INVOKED",
) -> dict:
    return {
        "projection_version": "UI03_GROWTH_HYPOTHESIS_V1",
        "tenant_id": tenant_id,
        "family_id": family_id,
        "availability": availability,
        "hypothesis": hypothesis,
        "named_actions": {
            "confirm": "CONFIRM_GROWTH_HYPOTHESIS",
            "dismiss": "DISMISS_GROWTH_HYPOTHESIS",
        },
        "ai_state": ai_state,
    }


def _map_hypothesis(evidence, interpretation: dict) -> dict:
    """Port of `mapHypothesis` (growth-hypothesis.service.ts) — see that file
    for the exact field-by-field mapping this mirrors.
    """
    draft = interpretation["interpretation"]["draft"]
    model_hypothesis = (draft.get("hypotheses") or [{}])[0]
    return {
        "hypothesis_ref": (
            f"ASSESSMENT:{evidence.assessment_session_id}:{evidence.tool_ref}"
            f":v{evidence.tool_version}:H1"
        ),
        "subject_person_id": evidence.subject_person_id,
        "subject_display_name": evidence.subject_display_name,
        "focus_ref": evidence.focus_ref,
        "need_type_ref": evidence.need_type_ref,
        "need_type_version": evidence.need_type_version,
        "title": evidence.title,
        "statement": (
            f"基于家庭本次选择和 Family Education Assessment Model 的结构化解读，"
            f"可以先把“{evidence.title}”作为一个待验证的支持方向。{evidence.description}"
        ),
        "required_capability_keys": evidence.required_capability_keys,
        "source_refs": {
            "assessment_session_id": evidence.assessment_session_id,
            "assessment_response_id": evidence.assessment_response_id,
            "assessment_evidence_id": evidence.assessment_evidence_id,
            "tool_ref": evidence.tool_ref,
            "tool_version": evidence.tool_version,
            "assessment_submitted_at": evidence.submitted_at,
        },
        "limitations": [
            "仅来自本次家庭视角回答，尚未包含孩子的直接表达。",
            "模型产物用于组织下一步支持，不表示家庭或孩子的固定标签。",
            "它不是医学、心理或教育诊断，后续行动效果需要另行观察和确认。",
        ],
        "generator": "FAMILY_EDUCATION_ASSESSMENT_MODEL_V0_1",
        "model_draft_ref": model_hypothesis.get("hypothesis_ref")
        or interpretation["interpretation"]["assessment_ref"],
        "model_generator": interpretation["interpretation"]["generator"],
        "model_component_ref": draft["model_component_ref"],
        "model_boundary_labels": draft["boundary_labels"],
        "need_refs": [need["need_ref"] for need in draft.get("need_summary", [])],
        "construct_refs": [
            signal["construct_ref"] for signal in draft.get("construct_signals", [])
        ],
        "action_candidate_refs": [
            candidate["action_ref"] for candidate in draft.get("action_candidates", [])
        ],
        "fact_boundary": "HYPOTHESIS_NOT_FACT_OR_DIAGNOSIS",
    }


def _assessment_result_projection(
    tenant_id: str, family_id: str, status: str, result: dict | None
) -> dict:
    return {
        "projection_version": "ASSESSMENT_RESULT_V1",
        "tenant_id": tenant_id,
        "family_id": family_id,
        "status": status,
        "result": result,
    }


def _support_loop_projection(
    tenant_id: str,
    family_id: str,
    status: str,
    assessment_session_id: str | None,
    state: dict | None,
) -> dict:
    return {
        "projection_version": "ASSESSMENT_SUPPORT_LOOP_V1",
        "tenant_id": tenant_id,
        "family_id": family_id,
        "status": status,
        "assessment_session_id": assessment_session_id,
        "small_step": state.get("small_step") if state else None,
        "latest_feedback": state.get("latest_feedback") if state else None,
        "latest_checkin": state.get("latest_checkin") if state else None,
    }


def _map_assessment_result(evidence, interpretation: dict) -> dict:
    """Map submitted evidence into a bounded, explainable result projection."""
    draft = interpretation.get("interpretation", {}).get("draft", {})
    source_refs = [
        evidence.assessment_evidence_id,
        evidence.assessment_session_id,
        evidence.assessment_response_id,
    ]
    recommendations = [
        {
            "action_ref": "TRY_TONIGHT",
            "text": evidence.description,
            "source": "DETERMINISTIC_TEST_BASELINE",
            "status": "DRAFT",
        }
    ]
    return {
        "result_id": f"ASSESSMENT_RESULT:{evidence.assessment_session_id}",
        "assessment_session_id": evidence.assessment_session_id,
        "subject": {
            "person_id": evidence.subject_person_id,
            "display_name": evidence.subject_display_name,
        },
        "focus_ref": evidence.focus_ref,
        "family_need_ref": evidence.need_type_ref,
        "title": evidence.title,
        "explanation": {
            "headline": f"家庭可以先从“{evidence.title}”开始",
            "summary": evidence.description,
            "observations": [
                {
                    "item_ref": response["item_ref"],
                    "response_value": response["response_value"],
                    "kind": "ASSESSMENT_RESPONSE",
                }
                for response in evidence.response_set
            ],
            "hypothesis": (
                "这是基于本次家庭回答整理出的待验证支持方向，你可以拒绝它或重新开始一次测评。"
            ),
            "recommendations": recommendations,
        },
        "evidence_lineage": {
            "source_refs": source_refs,
            "tool_ref": evidence.tool_ref,
            "tool_version": evidence.tool_version,
            "submitted_at": evidence.submitted_at,
        },
        "ai": {
            "generator": interpretation.get("interpretation", {}).get(
                "generator", "DETERMINISTIC_TEST_BASELINE"
            ),
            "model": None,
            "model_version": None,
            "prompt_version": None,
            "context_snapshot_ref": None,
            "provenance_refs": source_refs,
            "model_gateway_status": "NOT_INVOKED",
            "may_mutate_business_state": False,
        },
        "boundary": "FAMILY_PERSPECTIVE_NOT_SCORE_OR_DIAGNOSIS",
        "draft_metadata": {
            "boundary_labels": draft.get(
                "boundary_labels", ["hypothesis_not_fact", "recommendation_not_decision"]
            ),
            "review_required": False,
        },
    }
