"""Fail-closed routing from Principal capabilities to governed profiles."""

from __future__ import annotations

from dataclasses import dataclass

from backend.intelligence.principal.contracts import (
    PrincipalCapability,
    PrincipalEntryPoint,
    PrincipalHumanGate,
    PrincipalOutputType,
    PrincipalRiskLevel,
    PrincipalRouteDecision,
    PrincipalRouteRequest,
    PrincipalSoulRef,
)

DEFAULT_SOUL_REF = PrincipalSoulRef(
    soul_id="FAMILI_PRINCIPAL_SISTERLY_MENTOR",
    version="1.0.0",
    persona_ref="principal.persona_dna.v1",
    values_ref="principal.values.v1",
    thinking_policy_ref="principal.thinking_policy.v1",
    language_style_ref="principal.language_style.v1",
    action_policy_ref="principal.action_policy.v1",
    safety_policy_ref="principal.safety_policy.v1",
)


@dataclass(frozen=True, slots=True)
class _RouteRule:
    profile_id: str
    agent_id: str
    allowed_tools: tuple[str, ...]
    knowledge_scope: str
    output_type: PrincipalOutputType
    risk_level: PrincipalRiskLevel
    human_gate: PrincipalHumanGate


_RULES: dict[PrincipalCapability, _RouteRule] = {
    PrincipalCapability.ASSESSMENT_INTERPRETATION: _RouteRule(
        "family_understanding",
        "parent_advisor",
        ("read_context", "draft_explanation", "create_human_task"),
        "family_growth_reviewed",
        PrincipalOutputType.PERSPECTIVE,
        PrincipalRiskLevel.MEDIUM,
        PrincipalHumanGate.REVIEW_REQUIRED,
    ),
    PrincipalCapability.GROWTH_HYPOTHESIS_PRIORITIZATION: _RouteRule(
        "family_understanding",
        "growth_planner",
        ("read_context", "read_growth_projection", "draft_explanation"),
        "family_growth_reviewed",
        PrincipalOutputType.HYPOTHESIS,
        PrincipalRiskLevel.MEDIUM,
        PrincipalHumanGate.REVIEW_REQUIRED,
    ),
    PrincipalCapability.GROWTH_PLAN_DRAFT: _RouteRule(
        "growth_planning",
        "growth_planner",
        ("read_context", "read_growth_projection", "draft_growth_plan", "create_human_task"),
        "family_growth_reviewed",
        PrincipalOutputType.DRAFT,
        PrincipalRiskLevel.MEDIUM,
        PrincipalHumanGate.EXPLICIT_CONFIRMATION,
    ),
    PrincipalCapability.DAILY_ACTION_PROPOSAL: _RouteRule(
        "action_coaching",
        "child_coach",
        ("read_context", "read_growth_projection", "draft_daily_action", "create_human_task"),
        "family_growth_reviewed",
        PrincipalOutputType.ACTION_PROPOSAL,
        PrincipalRiskLevel.MEDIUM,
        PrincipalHumanGate.EXPLICIT_CONFIRMATION,
    ),
    PrincipalCapability.REFLECTION_PROCESS_PERSPECTIVE: _RouteRule(
        "delivery_reflection",
        "child_coach",
        ("read_context", "read_growth_projection", "create_human_task"),
        "family_growth_reviewed",
        PrincipalOutputType.PERSPECTIVE,
        PrincipalRiskLevel.MEDIUM,
        PrincipalHumanGate.REVIEW_REQUIRED,
    ),
    PrincipalCapability.FAMILY_ASSISTANT_CONVERSATION: _RouteRule(
        "family_understanding",
        "parent_advisor",
        ("read_context", "draft_explanation", "create_human_task"),
        "family_growth_reviewed",
        PrincipalOutputType.EXPLANATION,
        PrincipalRiskLevel.HIGH,
        PrincipalHumanGate.REVIEW_REQUIRED,
    ),
    PrincipalCapability.SERVICE_MATCHING_RECOMMENDATION: _RouteRule(
        "service_matching",
        "teaching_assistant",
        (
            "read_context",
            "read_growth_projection",
            "read_service_catalog",
            "draft_service_recommendation",
        ),
        "service_catalog_reviewed",
        PrincipalOutputType.RECOMMENDATION,
        PrincipalRiskLevel.HIGH,
        PrincipalHumanGate.REVIEW_REQUIRED,
    ),
    PrincipalCapability.OPERATIONS_INSIGHT: _RouteRule(
        "operations_insight",
        "operations_assistant",
        (
            "read_ops_projection",
            "read_ai_quality_projection",
            "draft_ops_insight",
            "create_human_task",
        ),
        "governance_reviewed",
        PrincipalOutputType.OPS_INSIGHT,
        PrincipalRiskLevel.MEDIUM,
        PrincipalHumanGate.REVIEW_REQUIRED,
    ),
    PrincipalCapability.SERVICE_PRODUCT_DISCOVERY: _RouteRule(
        "service_product_architect",
        "operations_assistant",
        ("read_context", "read_service_catalog", "draft_product_concept", "create_human_task"),
        "product_design_reviewed",
        PrincipalOutputType.DRAFT,
        PrincipalRiskLevel.MEDIUM,
        PrincipalHumanGate.REVIEW_REQUIRED,
    ),
    PrincipalCapability.SERVICE_PRODUCT_COMPOSITION: _RouteRule(
        "service_product_architect",
        "operations_assistant",
        ("read_product_components", "draft_product_definition", "create_human_task"),
        "product_design_reviewed",
        PrincipalOutputType.DRAFT,
        PrincipalRiskLevel.MEDIUM,
        PrincipalHumanGate.REVIEW_REQUIRED,
    ),
    PrincipalCapability.SERVICE_PRODUCT_COMPILE: _RouteRule(
        "service_product_architect",
        "operations_assistant",
        ("read_product_definition", "compile_service_blueprint", "create_human_task"),
        "product_design_reviewed",
        PrincipalOutputType.DRAFT,
        PrincipalRiskLevel.HIGH,
        PrincipalHumanGate.REVIEW_REQUIRED,
    ),
    PrincipalCapability.SERVICE_PRODUCT_SIMULATION: _RouteRule(
        "service_product_architect",
        "operations_assistant",
        ("read_service_blueprint_draft", "run_simulation", "create_human_task"),
        "product_design_reviewed",
        PrincipalOutputType.RECOMMENDATION,
        PrincipalRiskLevel.HIGH,
        PrincipalHumanGate.REVIEW_REQUIRED,
    ),
    PrincipalCapability.KNOWLEDGE_STEWARDSHIP: _RouteRule(
        "knowledge_steward",
        "operations_assistant",
        ("read_knowledge_source", "draft_knowledge_claim", "create_human_task"),
        "knowledge_governance",
        PrincipalOutputType.DRAFT,
        PrincipalRiskLevel.HIGH,
        PrincipalHumanGate.REVIEW_REQUIRED,
    ),
    PrincipalCapability.PRINCIPAL_KNOWLEDGE_ANSWER: _RouteRule(
        "family_understanding",
        "parent_advisor",
        ("read_context", "retrieve_reviewed_knowledge", "draft_explanation", "create_human_task"),
        "family_growth_reviewed",
        PrincipalOutputType.EXPLANATION,
        PrincipalRiskLevel.MEDIUM,
        PrincipalHumanGate.REVIEW_REQUIRED,
    ),
    PrincipalCapability.EXPERIENCE_CURATION: _RouteRule(
        "experience_curator",
        "parent_advisor",
        (
            "read_context",
            "retrieve_reviewed_knowledge",
            "draft_experience_recommendation",
            "create_human_task",
        ),
        "family_growth_reviewed",
        PrincipalOutputType.RECOMMENDATION,
        PrincipalRiskLevel.MEDIUM,
        PrincipalHumanGate.EXPLICIT_CONFIRMATION,
    ),
    PrincipalCapability.MEMORY_CANDIDATE_DRAFT: _RouteRule(
        "experience_curator",
        "parent_advisor",
        ("read_context", "draft_memory_candidate", "create_human_task"),
        "family_memory_scoped",
        PrincipalOutputType.DRAFT,
        PrincipalRiskLevel.HIGH,
        PrincipalHumanGate.EXPLICIT_CONFIRMATION,
    ),
}


class PrincipalCapabilityRouter:
    """Resolve only registered capabilities and fail closed for everything else."""

    def __init__(self, *, soul_ref: PrincipalSoulRef = DEFAULT_SOUL_REF) -> None:
        self._soul_ref = soul_ref

    @property
    def soul_ref(self) -> PrincipalSoulRef:
        return self._soul_ref

    def resolve(self, request: PrincipalRouteRequest) -> PrincipalRouteDecision:
        rule = _RULES.get(request.capability)
        if rule is None:
            raise ValueError("ROUTE_NOT_REGISTERED")
        if (
            request.entry_point is PrincipalEntryPoint.PRODUCT_DESIGN_WORKBENCH
            and request.family_id
        ):
            raise ValueError("SCOPE_DENIED")
        if (
            request.capability
            in {
                PrincipalCapability.SERVICE_PRODUCT_DISCOVERY,
                PrincipalCapability.SERVICE_PRODUCT_COMPOSITION,
                PrincipalCapability.SERVICE_PRODUCT_COMPILE,
                PrincipalCapability.SERVICE_PRODUCT_SIMULATION,
                PrincipalCapability.KNOWLEDGE_STEWARDSHIP,
                PrincipalCapability.OPERATIONS_INSIGHT,
            }
            and request.data_class == "MINOR_PERSONAL_DATA"
        ):
            raise ValueError("SCOPE_DENIED")
        return PrincipalRouteDecision(
            request_id=request.request_id,
            capability=request.capability,
            profile_id=rule.profile_id,
            agent_id=rule.agent_id,
            allowed_tools=rule.allowed_tools,
            knowledge_scope=rule.knowledge_scope,
            output_type=rule.output_type,
            risk_level=rule.risk_level,
            human_gate=rule.human_gate,
            soul_ref=self._soul_ref,
            reason="capability registered and policy scope satisfied",
            global_id=request.global_id,
            consent_version=request.consent_version,
            correlation_id=request.correlation_id,
            causation_id=request.causation_id,
            locale=request.locale,
            content_locale=request.content_locale or request.locale,
            model_locale=request.model_locale or request.locale,
            policy_locale=request.policy_locale or request.locale,
            region=request.region,
            tenant_policy_version=request.tenant_policy_version,
            tenant_id=request.tenant_id,
            family_id=request.family_id,
            subject_id=request.subject_id,
            purpose=request.purpose,
            data_class=request.data_class,
            consent_granted=request.consent_granted,
        )


def registered_capabilities() -> frozenset[PrincipalCapability]:
    """Expose the immutable route set for registry/contract tests."""

    return frozenset(_RULES)
