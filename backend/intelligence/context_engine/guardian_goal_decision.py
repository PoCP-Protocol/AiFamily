"""Guardian Goal Decision (AIFAMILY-WM-005) — a real human guardian's
decision on a `GoalProposal`.

This module is deliberately NOT generative: there is no model call anywhere
in it, no `AgentRuntime`, no `StructuredRequest`. A `GoalProposal` (see
`goal_proposal.py`) is AI-authored and explicitly not-yet-decided; a
`GuardianGoalDecision` is what turns "the AI proposed this" into either
"a real guardian accepted/edited it" or "a real guardian rejected it" —
the AI never gets to accept its own proposal. `guardian_actor_ref` is
checked structurally against looking like an AI actor identity for exactly
this reason (`AI_CANNOT_ACCEPT_GOAL`).

Follow-up integration note (explicitly out of scope for this module): once
recorded, an ACCEPT or EDIT decision is expected to later flow into
`backend/domains/growth/application/growth_intent_confirmation.py`'s real
`GrowthIntent` confirmation path via a follow-up task that carefully reviews
that binding's identity/idempotency rules. This module does not perform that
write itself — it only constructs and validates the decision record.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .contracts import ContextContractError


class GuardianGoalDecisionType(StrEnum):
    ACCEPT = "ACCEPT"
    EDIT = "EDIT"
    REJECT = "REJECT"


def _require_text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContextContractError(name)


@dataclass(frozen=True, slots=True)
class GuardianGoalDecision:
    """A deterministic, pure record of a real human guardian's decision on a
    `GoalProposal`. Construction alone enforces this module's governance
    rules — there is no separate validation step, because there is no model
    output to validate against here."""

    decision_id: str
    goal_proposal_ref: str
    decision: GuardianGoalDecisionType
    final_goal_text: str | None
    reason: str
    guardian_actor_ref: str
    decided_at: datetime

    def __post_init__(self) -> None:
        _require_text("decision_id", self.decision_id)
        _require_text("goal_proposal_ref", self.goal_proposal_ref)
        _require_text("reason", self.reason)
        _require_text("guardian_actor_ref", self.guardian_actor_ref)
        if (
            self.guardian_actor_ref.lower().startswith("ai:")
            or self.guardian_actor_ref.upper() == "AI"
        ):
            raise ContextContractError("AI_CANNOT_ACCEPT_GOAL")
        if self.decision in (
            GuardianGoalDecisionType.ACCEPT,
            GuardianGoalDecisionType.EDIT,
        ):
            if not isinstance(self.final_goal_text, str) or not self.final_goal_text.strip():
                raise ContextContractError("GUARDIAN_DECISION_REQUIRES_FINAL_GOAL_TEXT")
        elif self.decision is GuardianGoalDecisionType.REJECT and self.final_goal_text is not None:
            raise ContextContractError("REJECTED_GOAL_MUST_NOT_CARRY_FINAL_TEXT")
        if self.decided_at.tzinfo is None:
            raise ContextContractError("decided_at_requires_timezone")


def record_guardian_decision(
    *,
    decision_id: str,
    goal_proposal_ref: str,
    decision: GuardianGoalDecisionType,
    final_goal_text: str | None,
    reason: str,
    guardian_actor_ref: str,
    decided_at: datetime,
) -> GuardianGoalDecision:
    """Construct and return a `GuardianGoalDecision` — a clean, documented
    call site for the real validation the dataclass's own `__post_init__`
    performs, mirroring how `promote_proposal_to_atom` reads in
    `world_state.py`."""

    return GuardianGoalDecision(
        decision_id=decision_id,
        goal_proposal_ref=goal_proposal_ref,
        decision=decision,
        final_goal_text=final_goal_text,
        reason=reason,
        guardian_actor_ref=guardian_actor_ref,
        decided_at=decided_at,
    )


__all__ = [
    "GuardianGoalDecision",
    "GuardianGoalDecisionType",
    "record_guardian_decision",
]
