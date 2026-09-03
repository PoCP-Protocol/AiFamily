"""Deterministic safety pre/post checks around the Model Gateway.

The safety runtime is deliberately policy-oriented rather than a second
model.  It checks structural invariants (DRAFT-only, no business mutation,
no family score/rank) and escalates configured high-impact use cases to the
Human Gate.  Provider-specific moderation remains outside this module.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from backend.intelligence.model_gateway.contracts import ModelDraft

SafetyStatus = Literal["ALLOW", "REVIEW", "BLOCK"]

_PROHIBITED_USE_CASES = frozenset(
    {"family_total_score", "family_ranking", "child_commercial_profiling", "clinical_diagnosis"}
)
_HIGH_IMPACT_USE_CASES = frozenset(
    {
        "growth_plan_draft",
        "daily_action_proposal",
        "service_matching_recommendation",
        "teacher_recommendation",
        "membership_upgrade",
        "external_communication",
    }
)
_FORBIDDEN_KEYS = frozenset(
    {"family_score", "family_rank", "ranking", "total_score", "clinical_diagnosis"}
)


@dataclass(frozen=True, slots=True)
class SafetyContext:
    """Policy inputs resolved by the trusted composition root."""

    use_case: str
    subject_is_minor: bool = False
    data_class: str = "SYNTHETIC"
    purpose: str = ""
    tenant_id: str | None = None
    family_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.use_case, str) or not self.use_case.strip():
            raise ValueError("SAFETY_USE_CASE_REQUIRED")
        if not isinstance(self.subject_is_minor, bool):
            raise ValueError("SAFETY_MINOR_FLAG_INVALID")
        if not isinstance(self.data_class, str) or not self.data_class.strip():
            raise ValueError("SAFETY_DATA_CLASS_REQUIRED")
        if (self.tenant_id is None) != (self.family_id is None):
            raise ValueError("SAFETY_SCOPE_MUST_INCLUDE_TENANT_AND_FAMILY")
        if self.tenant_id is not None and (
            not self.tenant_id.strip() or not self.family_id or not self.family_id.strip()
        ):
            raise ValueError("SAFETY_SCOPE_VALUES_REQUIRED")


@dataclass(frozen=True, slots=True)
class SafetyDecision:
    """Immutable, auditable result of one safety check."""

    status: SafetyStatus
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "PROHIBITED"]
    reasons: tuple[str, ...]
    requires_human_gate: bool

    @property
    def allowed(self) -> bool:
        return self.status != "BLOCK"


class SafetyRuntime:
    """Evaluate policy constraints without invoking a provider."""

    def __init__(self, *, policy_version: str = "family-safety.v1") -> None:
        if not policy_version.strip():
            raise ValueError("SAFETY_POLICY_VERSION_REQUIRED")
        self.policy_version = policy_version

    @property
    def configuration_digest(self) -> str:
        value = {
            "policy_version": self.policy_version,
            "prohibited_use_cases": sorted(_PROHIBITED_USE_CASES),
            "high_impact_use_cases": sorted(_HIGH_IMPACT_USE_CASES),
            "forbidden_keys": sorted(_FORBIDDEN_KEYS),
        }
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def evaluate_input(
        self, context: SafetyContext, payload: Mapping[str, object]
    ) -> SafetyDecision:
        if not isinstance(payload, Mapping):
            raise ValueError("SAFETY_PAYLOAD_REQUIRED")
        reasons = _forbidden_reasons(context.use_case, payload)
        if reasons:
            return SafetyDecision("BLOCK", "PROHIBITED", reasons, False)
        if context.use_case in _PROHIBITED_USE_CASES:
            return SafetyDecision("BLOCK", "PROHIBITED", ("prohibited_use_case",), False)
        if context.use_case in _HIGH_IMPACT_USE_CASES:
            return SafetyDecision("REVIEW", "HIGH", ("high_impact_use_case",), True)
        return SafetyDecision("ALLOW", "LOW", (), False)

    def evaluate_output(self, context: SafetyContext, draft: ModelDraft) -> SafetyDecision:
        if not isinstance(draft, ModelDraft):
            raise ValueError("SAFETY_DRAFT_REQUIRED")
        if draft.status != "DRAFT" or draft.may_mutate_business_state:
            return SafetyDecision("BLOCK", "PROHIBITED", ("draft_mutation_forbidden",), False)
        reasons = _forbidden_reasons(context.use_case, draft.output)
        if reasons:
            return SafetyDecision("BLOCK", "PROHIBITED", reasons, False)
        if context.use_case in _PROHIBITED_USE_CASES:
            return SafetyDecision("BLOCK", "PROHIBITED", ("prohibited_use_case",), False)
        if context.use_case in _HIGH_IMPACT_USE_CASES or context.subject_is_minor:
            reason = (
                "high_impact_use_case"
                if context.use_case in _HIGH_IMPACT_USE_CASES
                else "minor_subject"
            )
            risk_level = "HIGH" if context.use_case in _HIGH_IMPACT_USE_CASES else "MEDIUM"
            return SafetyDecision("REVIEW", risk_level, (reason,), True)
        return SafetyDecision("ALLOW", "LOW", (), False)


def _forbidden_reasons(use_case: str, value: object) -> tuple[str, ...]:
    reasons: list[str] = []

    def walk(node: object, path: str) -> None:
        if isinstance(node, Mapping):
            for key, nested in node.items():
                key_text = str(key).strip().lower()
                if key_text in _FORBIDDEN_KEYS:
                    reasons.append(f"forbidden_field:{path}.{key_text}")
                walk(nested, f"{path}.{key_text}")
        elif isinstance(node, (list, tuple, set, frozenset)):
            for index, nested in enumerate(node):
                walk(nested, f"{path}[{index}]")

    walk(value, "payload")
    if use_case in _PROHIBITED_USE_CASES:
        reasons.append("prohibited_use_case")
    return tuple(dict.fromkeys(reasons))


__all__ = ["SafetyContext", "SafetyDecision", "SafetyRuntime", "SafetyStatus"]
