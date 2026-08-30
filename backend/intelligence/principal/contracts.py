"""Contracts for the Principal control plane.

The Principal is an orchestration boundary, not a business domain.  These
objects deliberately contain routing and policy information only: they do not
hold a domain repository and cannot represent a canonical family or service
fact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from backend.intelligence.model_gateway.contracts import DataClass


class PrincipalCapability(StrEnum):
    """Capabilities that the Principal may route to a governed AI profile."""

    ASSESSMENT_INTERPRETATION = "assessment_interpretation"
    GROWTH_HYPOTHESIS_PRIORITIZATION = "growth_hypothesis_prioritization"
    GROWTH_PLAN_DRAFT = "growth_plan_draft"
    DAILY_ACTION_PROPOSAL = "daily_action_proposal"
    REFLECTION_PROCESS_PERSPECTIVE = "reflection_process_perspective"
    FAMILY_ASSISTANT_CONVERSATION = "family_assistant_conversation"
    SERVICE_MATCHING_RECOMMENDATION = "service_matching_recommendation"
    OPERATIONS_INSIGHT = "operations_insight"
    SERVICE_PRODUCT_DISCOVERY = "service_product_discovery"
    SERVICE_PRODUCT_COMPOSITION = "service_product_composition"
    SERVICE_PRODUCT_COMPILE = "service_product_compile"
    SERVICE_PRODUCT_SIMULATION = "service_product_simulation"
    KNOWLEDGE_STEWARDSHIP = "knowledge_stewardship"
    PRINCIPAL_KNOWLEDGE_ANSWER = "principal_knowledge_answer"
    EXPERIENCE_CURATION = "experience_curation"
    MEMORY_CANDIDATE_DRAFT = "memory_candidate_draft"


class PrincipalEntryPoint(StrEnum):
    """Product entry points shared by the mobile and operations surfaces."""

    ASK_PRINCIPAL = "ask_principal"
    SAY_IT_TONIGHT = "say_it_tonight"
    TODAY_ACTION = "today_action"
    TWENTY_ONE_DAY_COMPANION = "21_day_companion"
    PRINCIPAL_MICRO_LESSON = "principal_micro_lesson"
    PRODUCT_DESIGN_WORKBENCH = "product_design_workbench"
    KNOWLEDGE_WORKBENCH = "knowledge_workbench"
    OPERATIONS_WORKBENCH = "operations_workbench"


class PrincipalRiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    PROHIBITED = "PROHIBITED"


class PrincipalHumanGate(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    EXPLICIT_CONFIRMATION = "EXPLICIT_CONFIRMATION"
    PROHIBITED = "PROHIBITED"


class PrincipalOutputType(StrEnum):
    PERSPECTIVE = "Perspective"
    HYPOTHESIS = "Hypothesis"
    DRAFT = "Draft"
    RECOMMENDATION = "Recommendation"
    EXPLANATION = "Explanation"
    ACTION_PROPOSAL = "ActionProposal"
    OPS_INSIGHT = "OpsInsight"
    HUMAN_TASK = "HumanTask"


@dataclass(frozen=True, slots=True)
class PrincipalSoulRef:
    """Immutable reference to the reviewed Principal Soul bundle."""

    soul_id: str
    version: str
    persona_ref: str
    values_ref: str
    thinking_policy_ref: str
    language_style_ref: str
    action_policy_ref: str
    safety_policy_ref: str
    method_inheritance: bool = True
    identity_cloning: bool = False

    def __post_init__(self) -> None:
        required = (
            self.soul_id,
            self.version,
            self.persona_ref,
            self.values_ref,
            self.thinking_policy_ref,
            self.language_style_ref,
            self.action_policy_ref,
            self.safety_policy_ref,
        )
        if not all(required):
            raise ValueError("PrincipalSoulRef requires all policy references")
        if not self.method_inheritance:
            raise ValueError("Principal Soul must declare method inheritance")
        if self.identity_cloning:
            raise ValueError("identity cloning is prohibited")


@dataclass(frozen=True, slots=True)
class PrincipalRouteRequest:
    """Input to deterministic capability routing.

    The router does not inspect domain ORM objects.  Callers provide a
    previously authorized context snapshot reference and an explicit purpose.
    """

    request_id: str
    tenant_id: str
    actor_type: str
    entry_point: PrincipalEntryPoint
    capability: PrincipalCapability
    purpose: str
    data_class: DataClass
    context_snapshot_ref: str
    consent_granted: bool
    global_id: str
    consent_version: str
    correlation_id: str
    causation_id: str
    family_id: str | None = None
    subject_id: str | None = None
    locale: str = "zh-CN"
    content_locale: str | None = None
    model_locale: str | None = None
    policy_locale: str | None = None
    region: str = "CN"
    tenant_policy_version: str = "tenant-policy.v1"

    def __post_init__(self) -> None:
        required = (
            self.request_id,
            self.tenant_id,
            self.actor_type,
            self.purpose,
            self.context_snapshot_ref,
            self.global_id,
            self.consent_version,
            self.correlation_id,
            self.causation_id,
        )
        if not all(required):
            raise ValueError("PrincipalRouteRequest identity and purpose are required")
        if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", self.locale):
            raise ValueError("LOCALE_UNSUPPORTED")
        if self.content_locale and not re.fullmatch(
            r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", self.content_locale
        ):
            raise ValueError("LOCALE_UNSUPPORTED")
        for locale in (self.model_locale, self.policy_locale):
            if locale and not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", locale):
                raise ValueError("LOCALE_UNSUPPORTED")
        if not re.fullmatch(r"[A-Z]{2,3}", self.region):
            raise ValueError("REGION_UNSUPPORTED")
        if not self.tenant_policy_version:
            raise ValueError("TENANT_POLICY_UNAVAILABLE")
        if (
            self.data_class in {"FAMILY_PRIVATE_TEXT", "MINOR_PERSONAL_DATA"}
            and not self.consent_granted
        ):
            raise ValueError("CONSENT_REQUIRED")
        family_entry = self.entry_point in {
            PrincipalEntryPoint.ASK_PRINCIPAL,
            PrincipalEntryPoint.SAY_IT_TONIGHT,
            PrincipalEntryPoint.TODAY_ACTION,
            PrincipalEntryPoint.TWENTY_ONE_DAY_COMPANION,
            PrincipalEntryPoint.PRINCIPAL_MICRO_LESSON,
        }
        if family_entry and not self.family_id:
            raise ValueError("SCOPE_DENIED")


@dataclass(frozen=True, slots=True)
class PrincipalRouteDecision:
    """The only output of routing; it grants no business write permission."""

    request_id: str
    capability: PrincipalCapability
    profile_id: str
    agent_id: str
    allowed_tools: tuple[str, ...]
    knowledge_scope: str
    output_type: PrincipalOutputType
    risk_level: PrincipalRiskLevel
    human_gate: PrincipalHumanGate
    soul_ref: PrincipalSoulRef
    reason: str
    global_id: str
    consent_version: str
    correlation_id: str
    causation_id: str
    locale: str
    content_locale: str
    model_locale: str
    policy_locale: str
    region: str
    tenant_policy_version: str
    tenant_id: str
    family_id: str | None
    subject_id: str | None
    purpose: str
    data_class: DataClass
    consent_granted: bool

    @property
    def may_mutate_business_state(self) -> bool:
        """A Principal route can never grant a domain mutation capability."""

        return False
