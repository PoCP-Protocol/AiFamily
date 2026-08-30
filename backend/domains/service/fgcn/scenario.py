"""Canonical, locale-aware S-01 scenario facts for the FGCN service slice.

The scenario is deliberately represented as a versioned business concept,
not inferred from English prose. Localized prose is rendered from the
registry and is checked against structured outcome markers before it can be
used as delivery or quality evidence.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from backend.domains.service.domain.errors import ServiceValidationError

S01_SCENARIO_KEY = "S-01"
S01_SCENARIO_VERSION = 1
S01_OUTCOME_KEY = "CALM_START_CONFLICT_REDUCTION"
S01_POLICY_REF = "shadow-policy.v1"
S01_POLICY_VERSION = 1
S01_DEFAULT_LOCALE = "en"

# This is an FGCN-owned registry for the frozen S-01 concept. It is not a
# general translation service: adding a locale requires adding its canonical
# scenario copy and its marker vocabulary in the same reviewed change.
S01_LOCALE_REGISTRY: dict[str, dict[str, object]] = {
    "en": {
        "family_problem": (
            "The family has repeatedly tried self-help, but cannot start a calm shared "
            "action without conflict escalating."
        ),
        "provider_deliverable": (
            "A qualified human provider delivers one adult-led calm-start intervention "
            "from the frozen blueprint and submits auditable delivery evidence."
        ),
        "service_outcome": (
            "The family completes one calm start and conflict does not escalate; child "
            "performance, family scores, and rankings are out of scope."
        ),
        "task_acceptance_criterion": (
            "The adult-led calm start was completed and conflict did not escalate; child "
            "performance, family scores, and rankings are not an acceptance measure."
        ),
        "quality_verification_marker": (
            "S-01 outcome verified: calm start completed and conflict did not escalate."
        ),
        "quality_rework_marker": (
            "S-01 rework required: delivery evidence does not yet demonstrate a calm start "
            "without conflict escalation."
        ),
        "outcome_observation": "S-01 calm start completed; conflict did not escalate.",
        "markers": {
            "calm_start_completed": ("calm start completed",),
            "conflict_contained": ("conflict did not escalate",),
        },
    },
    "zh": {
        "family_problem": "家庭已反复尝试自助，但无法在冲突不升级的情况下平稳开始共同行动。",
        "provider_deliverable": (
            "合资格人工服务提供者依据冻结蓝图交付一次成人主导的平稳启动干预，"
            "并提交可审计的交付证据。"
        ),
        "service_outcome": (
            "家庭完成一次平稳启动且冲突未升级；儿童表现、家庭分数和排名不属于结果范围。"
        ),
        "task_acceptance_criterion": (
            "成人主导的平稳启动已完成且冲突未升级；儿童表现、家庭分数和排名不是验收指标。"
        ),
        "quality_verification_marker": "S-01 结果已验收：平稳启动已完成且冲突未升级。",
        "quality_rework_marker": "S-01 需要返工：交付证据尚未证明平稳启动且冲突未升级。",
        "outcome_observation": "S-01 平稳启动已完成；冲突未升级。",
        "markers": {
            "calm_start_completed": ("平稳启动已完成",),
            "conflict_contained": ("冲突未升级",),
        },
    },
    "fr": {
        "family_problem": (
            "La famille a essayé plusieurs fois de s'aider seule, mais ne parvient pas à "
            "commencer calmement sans escalade du conflit."
        ),
        "provider_deliverable": (
            "Un intervenant humain qualifié réalise une intervention de démarrage calme, "
            "dirigée par un adulte, selon le blueprint gelé et fournit une preuve de "
            "livraison auditable."
        ),
        "service_outcome": (
            "La famille réalise un démarrage calme et le conflit ne s'aggrave pas ; la "
            "performance de l'enfant, les scores familiaux et les classements sont hors "
            "périmètre."
        ),
        "task_acceptance_criterion": (
            "Le démarrage calme dirigé par un adulte est réalisé et le conflit ne "
            "s'aggrave pas ; la performance de l'enfant, les scores familiaux et les "
            "classements ne sont pas des critères d'acceptation."
        ),
        "quality_verification_marker": (
            "Résultat S-01 vérifié : démarrage calme terminé et le conflit ne s'est pas aggravé."
        ),
        "quality_rework_marker": (
            "Retouche S-01 requise : la preuve de livraison ne démontre pas encore un "
            "démarrage calme sans aggravation du conflit."
        ),
        "outcome_observation": ("S-01 démarrage calme terminé ; le conflit ne s'est pas aggravé."),
        "markers": {
            "calm_start_completed": ("démarrage calme terminé",),
            "conflict_contained": ("conflit ne s'est pas aggravé",),
        },
    },
}

S01_FAMILY_PROBLEM = S01_LOCALE_REGISTRY["en"]["family_problem"]
S01_PROVIDER_DELIVERABLE = S01_LOCALE_REGISTRY["en"]["provider_deliverable"]
S01_SERVICE_OUTCOME = S01_LOCALE_REGISTRY["en"]["service_outcome"]
S01_TASK_ACCEPTANCE_CRITERION = S01_LOCALE_REGISTRY["en"]["task_acceptance_criterion"]
S01_QUALITY_VERIFICATION_MARKER = S01_LOCALE_REGISTRY["en"]["quality_verification_marker"]
S01_REWORK_QUALITY_MARKER = S01_LOCALE_REGISTRY["en"]["quality_rework_marker"]
S01_OUTCOME_OBSERVATION = S01_LOCALE_REGISTRY["en"]["outcome_observation"]

_FORBIDDEN_COMPARISON_TERMS = (
    "score",
    "scores",
    "ranking",
    "rank",
    "grade",
    "grades",
    "成绩",
    "分数",
    "总分",
    "排名",
    "排行",
    "名次",
    "classement",
    "rang",
    "note",
)


def _locale(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ServiceValidationError("fgcn_s01_locale_required")
    normalized = value.strip().casefold()
    if normalized not in S01_LOCALE_REGISTRY:
        raise ServiceValidationError("fgcn_s01_locale_unsupported")
    return normalized


def _entry(locale: str) -> dict[str, object]:
    return S01_LOCALE_REGISTRY[_locale(locale)]


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ServiceValidationError(f"fgcn_s01_{field_name}_required")
    return value.strip()


@dataclass(frozen=True, slots=True)
class S01OutcomeMarkers:
    """Structured outcome facts; prose is only a localized rendering."""

    calm_start_completed: bool
    conflict_escalated: bool
    scenario_key: str = S01_SCENARIO_KEY
    scenario_version: int = S01_SCENARIO_VERSION
    outcome_key: str = S01_OUTCOME_KEY
    child_performance_observed: bool = False

    def __post_init__(self) -> None:
        if self.scenario_key != S01_SCENARIO_KEY or self.scenario_version != S01_SCENARIO_VERSION:
            raise ServiceValidationError("fgcn_s01_outcome_concept_invalid")
        if self.outcome_key != S01_OUTCOME_KEY:
            raise ServiceValidationError("fgcn_s01_outcome_concept_invalid")
        for value, field_name in (
            (self.calm_start_completed, "calm_start_completed"),
            (self.conflict_escalated, "conflict_escalated"),
            (self.child_performance_observed, "child_performance_observed"),
        ):
            if type(value) is not bool:
                raise ServiceValidationError(f"fgcn_s01_{field_name}_invalid")
        if self.child_performance_observed:
            raise ServiceValidationError("fgcn_s01_scoring_semantics_forbidden")


@dataclass(frozen=True, slots=True)
class ServiceScenario:
    """Immutable, versioned scenario content frozen into a BlueprintSnapshot."""

    scenario_key: str
    family_problem: str
    provider_deliverable: str
    service_outcome: str
    scenario_version: int = S01_SCENARIO_VERSION
    outcome_key: str = S01_OUTCOME_KEY
    policy_ref: str = S01_POLICY_REF
    policy_version: int = S01_POLICY_VERSION
    locale: str = S01_DEFAULT_LOCALE

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.scenario_key, "scenario_key"),
            (self.family_problem, "family_problem"),
            (self.provider_deliverable, "provider_deliverable"),
            (self.service_outcome, "service_outcome"),
            (self.outcome_key, "outcome_key"),
            (self.policy_ref, "policy_ref"),
        ):
            _text(value, field_name)
        if self.scenario_version < 1 or self.policy_version < 1:
            raise ServiceValidationError("fgcn_s01_scenario_version_invalid")
        if not isinstance(self.locale, str) or not self.locale.strip():
            raise ServiceValidationError("fgcn_s01_locale_required")
        object.__setattr__(self, "locale", self.locale.strip().casefold())


def render_s01_scenario(locale: str = S01_DEFAULT_LOCALE) -> ServiceScenario:
    """Render the canonical S-01 concept into a registered locale."""

    language = _locale(locale)
    copy = _entry(language)
    return ServiceScenario(
        scenario_key=S01_SCENARIO_KEY,
        family_problem=copy["family_problem"],
        provider_deliverable=copy["provider_deliverable"],
        service_outcome=copy["service_outcome"],
        scenario_version=S01_SCENARIO_VERSION,
        outcome_key=S01_OUTCOME_KEY,
        policy_ref=S01_POLICY_REF,
        policy_version=S01_POLICY_VERSION,
        locale=language,
    )


S01_SCENARIO = render_s01_scenario()


def validate_s01_scenario(
    scenario: ServiceScenario,
    *,
    policy_ref: str | None = None,
    policy_version: int | None = None,
) -> ServiceScenario:
    """Allow only a registered, versioned S-01 scenario into a blueprint."""

    if not isinstance(scenario, ServiceScenario):
        raise ServiceValidationError("fgcn_s01_scenario_required")
    if scenario.scenario_key != S01_SCENARIO_KEY:
        raise ServiceValidationError("fgcn_only_s01_scenario_is_supported")
    if (
        scenario.scenario_version != S01_SCENARIO_VERSION
        or scenario.outcome_key != S01_OUTCOME_KEY
        or scenario.policy_ref != S01_POLICY_REF
        or scenario.policy_version != S01_POLICY_VERSION
        or scenario.locale not in S01_LOCALE_REGISTRY
    ):
        raise ServiceValidationError("fgcn_s01_scenario_metadata_invalid")
    if policy_ref is not None and policy_ref != scenario.policy_ref:
        raise ServiceValidationError("fgcn_s01_blueprint_policy_invalid")
    if policy_version is not None and (type(policy_version) is not int or policy_version < 1):
        raise ServiceValidationError("fgcn_s01_blueprint_policy_invalid")
    if scenario != render_s01_scenario(scenario.locale):
        raise ServiceValidationError("fgcn_only_s01_scenario_is_supported")
    return scenario


def validate_s01_task_acceptance(
    criteria: Iterable[str], *, locale: str = S01_DEFAULT_LOCALE
) -> tuple[str, ...]:
    """Require the localized task criterion for the S-01 outcome."""

    copy = _entry(locale)
    normalized = tuple(criteria)
    expected = copy["task_acceptance_criterion"]
    if expected not in normalized:
        raise ServiceValidationError("fgcn_s01_task_outcome_criterion_required")
    return normalized


def parse_s01_outcome_markers(
    observation: str, *, locale: str = S01_DEFAULT_LOCALE
) -> S01OutcomeMarkers:
    """Parse only the registered locale's marker vocabulary into facts."""

    language = _locale(locale)
    normalized = _text(observation, "delivery_outcome").casefold()
    if any(term in normalized for term in _FORBIDDEN_COMPARISON_TERMS):
        raise ServiceValidationError("fgcn_s01_scoring_semantics_forbidden")
    markers = _entry(language)["markers"]
    calm_tokens = markers["calm_start_completed"]
    conflict_tokens = markers["conflict_contained"]
    if not all(token.casefold() in normalized for token in (*calm_tokens, *conflict_tokens)):
        raise ServiceValidationError("fgcn_s01_delivery_outcome_required")
    return S01OutcomeMarkers(calm_start_completed=True, conflict_escalated=False)


def validate_s01_outcome_observation(
    observation: str,
    *,
    locale: str = S01_DEFAULT_LOCALE,
    markers: S01OutcomeMarkers | None = None,
) -> str:
    """Validate structured outcome facts and their registered prose rendering."""

    normalized = _text(observation, "delivery_outcome")
    parsed = parse_s01_outcome_markers(normalized, locale=locale)
    if markers is not None and markers != parsed:
        raise ServiceValidationError("fgcn_s01_outcome_markers_mismatch")
    return normalized


def validate_s01_quality_note(note: str, *, locale: str = S01_DEFAULT_LOCALE) -> str:
    """Require the registered localized human-verification marker."""

    normalized = _text(note, "quality_note")
    marker = _entry(locale)["quality_verification_marker"]
    if marker not in normalized:
        raise ServiceValidationError("fgcn_s01_quality_outcome_attestation_required")
    if any(term in normalized.casefold() for term in _FORBIDDEN_COMPARISON_TERMS):
        raise ServiceValidationError("fgcn_s01_scoring_semantics_forbidden")
    return normalized


def validate_s01_rework_note(note: str, *, locale: str = S01_DEFAULT_LOCALE) -> str:
    """Require a localized human reason when delivery needs rework."""

    normalized = _text(note, "quality_rework_note")
    marker = _entry(locale)["quality_rework_marker"]
    if marker not in normalized:
        raise ServiceValidationError("fgcn_s01_rework_reason_required")
    if any(term in normalized.casefold() for term in _FORBIDDEN_COMPARISON_TERMS):
        raise ServiceValidationError("fgcn_s01_scoring_semantics_forbidden")
    return normalized


__all__ = [
    "S01_DEFAULT_LOCALE",
    "S01_FAMILY_PROBLEM",
    "S01_LOCALE_REGISTRY",
    "S01_OUTCOME_KEY",
    "S01_OUTCOME_OBSERVATION",
    "S01_POLICY_REF",
    "S01_POLICY_VERSION",
    "S01_PROVIDER_DELIVERABLE",
    "S01_REWORK_QUALITY_MARKER",
    "S01_QUALITY_VERIFICATION_MARKER",
    "S01_SCENARIO",
    "S01_SCENARIO_KEY",
    "S01_SCENARIO_VERSION",
    "S01_SERVICE_OUTCOME",
    "S01_TASK_ACCEPTANCE_CRITERION",
    "S01OutcomeMarkers",
    "ServiceScenario",
    "parse_s01_outcome_markers",
    "render_s01_scenario",
    "validate_s01_outcome_observation",
    "validate_s01_quality_note",
    "validate_s01_rework_note",
    "validate_s01_scenario",
    "validate_s01_task_acceptance",
]
