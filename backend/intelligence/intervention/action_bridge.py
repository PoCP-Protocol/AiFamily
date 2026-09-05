"""Bridge Blueprint recommendations into a pending Human Gate action.

This adapter deliberately stops at ``PendingNamedAction``.  It does not call
the domain, enqueue a payment/service command, or turn a recommendation into a
fact.  A Human Gate decision and the owning domain consumer remain required.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.intelligence.human_gate.contracts import GateScope
from backend.intelligence.tool_runtime.contracts import PendingNamedAction, ToolCallResult

from .blueprint_matching import BlueprintRecommendation


class InterventionActionBridgeError(ValueError):
    """Raised when a recommendation cannot cross the Human Gate boundary."""


def to_pending_named_action(
    recommendation: BlueprintRecommendation,
    *,
    tenant_id: str,
    family_id: str,
    subject_ids: tuple[str, ...],
    purpose: str,
    consent_version: str,
    correlation_id: str,
    provenance_ref: str,
    expires_at: datetime | None = None,
) -> PendingNamedAction:
    """Create a bounded, explicit Named Action candidate for human review."""

    if not isinstance(recommendation, BlueprintRecommendation):
        raise InterventionActionBridgeError("BLUEPRINT_RECOMMENDATION_REQUIRED")
    if recommendation.status != "DRAFT":
        raise InterventionActionBridgeError("INTERVENTION_DRAFT_ONLY")
    values = (tenant_id, family_id, purpose, consent_version, correlation_id, provenance_ref)
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise InterventionActionBridgeError("ACTION_SCOPE_AND_PROVENANCE_REQUIRED")
    if not subject_ids or any(not value for value in subject_ids):
        raise InterventionActionBridgeError("ACTION_SUBJECT_SCOPE_REQUIRED")
    current = datetime.now(UTC)
    expiry = expires_at or (current + timedelta(hours=24))
    if expiry.tzinfo is None or expiry <= current:
        raise InterventionActionBridgeError("ACTION_EXPIRY_INVALID")
    return PendingNamedAction(
        action_name="PROPOSE_SERVICE_BLUEPRINT",
        action_arguments={
            "blueprint_ref": recommendation.blueprint_ref,
            "primary_contradiction_ref": recommendation.primary_contradiction_ref,
            "action_refs": list(recommendation.action_refs),
            "evidence_refs": list(recommendation.evidence_refs),
            "recommendation_status": recommendation.status,
        },
        scope=GateScope(
            tenant_id=tenant_id,
            family_id=family_id,
            subject_ids=subject_ids,
            purpose=purpose,
            consent_version=consent_version,
            correlation_id=correlation_id,
        ),
        provenance_ref=provenance_ref,
        risk_level="HIGH" if recommendation.human_gate_required else "MEDIUM",
        expires_at=expiry,
    )


def to_tool_call_result(
    recommendation: BlueprintRecommendation,
    *,
    call_id: str,
    tool_id: str,
    agent_id: str,
    use_case: str,
    tenant_id: str,
    family_id: str,
    subject_ids: tuple[str, ...],
    consent_version: str,
    correlation_id: str,
    provenance_ref: str,
    expires_at: datetime | None = None,
) -> ToolCallResult:
    """Wrap a recommendation as a Tool Runtime result for outbox delivery."""

    values = (call_id, tool_id, agent_id, use_case)
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise InterventionActionBridgeError("TOOL_RESULT_IDENTITY_REQUIRED")
    pending = to_pending_named_action(
        recommendation,
        tenant_id=tenant_id,
        family_id=family_id,
        subject_ids=subject_ids,
        purpose=use_case,
        consent_version=consent_version,
        correlation_id=correlation_id,
        provenance_ref=provenance_ref,
        expires_at=expires_at,
    )
    return ToolCallResult(
        call_id=call_id,
        tool_id=tool_id,
        agent_id=agent_id,
        tenant_id=tenant_id,
        family_id=family_id,
        pending_action=pending,
    )


__all__ = [
    "InterventionActionBridgeError",
    "to_pending_named_action",
    "to_tool_call_result",
]
