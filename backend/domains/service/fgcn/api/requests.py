"""HTTP request contracts for the FGCN Human Gate bridge.

The absence of actor, scope, and Named Action fields is intentional.  Those
values are either resolved from trusted identity or constructed by the server
from the persisted FGCN case/task.  ``extra='forbid'`` turns attempts to send
forged fields into an explicit 422 instead of silently ignoring them.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.intelligence.human_gate import DecisionOutcome


class AssignmentProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(min_length=1, max_length=160)
    draft_id: str = Field(min_length=1, max_length=160)
    provenance_ref: str = Field(min_length=1, max_length=256)
    provider_id: str = Field(min_length=1, max_length=160)
    assignee_kind: Literal["STEWARD", "AI", "COACH", "EXPERT", "CONTENT"] = "EXPERT"
    assignment_id: UUID | None = None
    expires_in_seconds: int = Field(default=86_400, ge=60, le=86_400)


class HumanDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: DecisionOutcome
    reason: str | None = Field(default=None, max_length=2_000)


__all__ = ["AssignmentProposalRequest", "HumanDecisionRequest"]
