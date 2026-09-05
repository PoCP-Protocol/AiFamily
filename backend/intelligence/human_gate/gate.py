"""In-memory Human Gate runtime.

This adapter is intentionally shaped like a future durable workflow port.  It
is useful for contract tests and development, but it is not a production queue:
the package does not claim persistence, retries, notifications, or worker
delivery.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from backend.intelligence.human_gate.contracts import (
    ActionProposal,
    ActorType,
    DecisionOutcome,
    GateScope,
    GateStatus,
    HumanDecision,
    HumanTask,
    NamedActionRequest,
)
from backend.intelligence.human_gate.errors import HumanGateError

if TYPE_CHECKING:
    from backend.intelligence.model_gateway.contracts import ModelDraft


class InMemoryHumanGate:
    """Open and decide human tasks without touching a business repository."""

    def __init__(self) -> None:
        self._tasks: dict[str, HumanTask] = {}
        self._task_ids_by_proposal: dict[tuple[str, str], str] = {}

    def submit(self, proposal: ActionProposal, *, task_id: str | None = None) -> HumanTask:
        """Create an OPEN task, idempotently by tenant and proposal id."""

        key = (proposal.scope.tenant_id, proposal.proposal_id)
        existing_id = self._task_ids_by_proposal.get(key)
        if existing_id is not None:
            existing = self._tasks[existing_id]
            if existing.proposal != proposal:
                raise HumanGateError(
                    "PROPOSAL_REPLAY_MISMATCH", "proposal id was reused with new content"
                )
            return existing

        resolved_task_id = task_id or f"human-task:{proposal.proposal_id}"
        if resolved_task_id in self._tasks:
            raise HumanGateError("TASK_ID_COLLISION", "task_id is already registered")
        task = HumanTask(
            task_id=resolved_task_id,
            proposal=proposal,
            created_at=proposal.created_at,
        )
        self._tasks[resolved_task_id] = task
        self._task_ids_by_proposal[key] = resolved_task_id
        return task

    def submit_model_draft(
        self,
        draft: ModelDraft,
        *,
        draft_id: str,
        proposal_id: str,
        action_name: str,
        action_arguments: dict[str, object],
        scope: GateScope,
        allowed_actor_types: tuple[ActorType, ...],
        risk_level: str,
        provenance_ref: str,
        now: datetime | None = None,
        ttl: timedelta = timedelta(hours=24),
    ) -> HumanTask:
        """Convert a Model Gateway draft into a review task.

        The explicit draft checks are repeated at this boundary so a future
        caller cannot hand in a different object that merely looks like a
        recommendation.  The model output itself remains outside the task; the
        caller maps only the proposed action arguments into this contract.
        """

        if getattr(draft, "status", None) != "DRAFT":
            raise HumanGateError(
                "DRAFT_REQUIRED", "Human Gate accepts only ModelDraft status DRAFT"
            )
        if getattr(draft, "may_mutate_business_state", True) is not False:
            raise HumanGateError(
                "AI_MUTATION_FORBIDDEN", "an AI draft cannot mutate business state"
            )
        created_at = now or datetime.now(UTC)
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise HumanGateError("INVALID_CONTRACT", "now must be timezone-aware")
        existing_id = self._task_ids_by_proposal.get((scope.tenant_id, proposal_id))
        if existing_id is not None:
            existing = self._tasks[existing_id]
            existing_ttl = existing.proposal.expires_at - existing.proposal.created_at
            if ttl == existing_ttl:
                # The clock is server metadata, not proposal content. Preserve
                # the original window so a retry without a caller-supplied
                # timestamp remains an idempotent replay.
                created_at = existing.proposal.created_at
        proposal = ActionProposal(
            proposal_id=proposal_id,
            draft_id=draft_id,
            draft_status=draft.status,
            action_name=action_name,
            action_arguments=action_arguments,
            scope=scope,
            allowed_actor_types=allowed_actor_types,
            risk_level=risk_level,
            provenance_ref=provenance_ref,
            created_at=created_at,
            expires_at=created_at + ttl,
        )
        return self.submit(proposal)

    def get(self, task_id: str) -> HumanTask:
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise HumanGateError("TASK_NOT_FOUND", f"unknown human task {task_id!r}") from exc

    def decide(
        self,
        task_id: str,
        *,
        actor_id: str,
        actor_type: ActorType | str,
        outcome: DecisionOutcome | str,
        reason: str | None = None,
        decision_id: str | None = None,
        now: datetime | None = None,
    ) -> tuple[HumanTask, NamedActionRequest | None]:
        """Record one human decision and optionally return a domain request."""

        task = self.get(task_id)
        if task.status is GateStatus.EXPIRED:
            raise HumanGateError("TASK_EXPIRED", "the human task is past its review deadline")
        if task.status is GateStatus.DECIDED:
            requested_decision_id = decision_id or f"decision:{task_id}"
            previous = task.decision
            same_decision = (
                previous is not None
                and previous.decision_id == requested_decision_id
                and previous.actor_id == actor_id
                and previous.actor_type == actor_type
                and previous.outcome == outcome
                and (previous.reason or "").strip() == (reason or "").strip()
            )
            if same_decision:
                return task, task.action_request
            raise HumanGateError("TASK_ALREADY_DECIDED", "a human task can be decided only once")

        try:
            actor_type = ActorType(actor_type)
            outcome = DecisionOutcome(outcome)
        except ValueError as exc:
            raise HumanGateError(
                "INVALID_DECISION", "unknown actor type or decision outcome"
            ) from exc

        current = now or datetime.now(UTC)
        if current.tzinfo is None or current.utcoffset() is None:
            raise HumanGateError("INVALID_CONTRACT", "now must be timezone-aware")
        if current >= task.proposal.expires_at:
            expired = replace(task, status=GateStatus.EXPIRED, decision=None)
            self._tasks[task_id] = expired
            raise HumanGateError("TASK_EXPIRED", "the human task is past its review deadline")

        if actor_type not in {ActorType.GUARDIAN, ActorType.PROFESSIONAL, ActorType.OPERATOR}:
            raise HumanGateError("HUMAN_REVIEWER_REQUIRED", "AI and system actors cannot decide")
        if actor_type not in task.proposal.allowed_actor_types:
            raise HumanGateError("REVIEWER_NOT_ALLOWED", "actor is not allowed for this proposal")

        decision = HumanDecision(
            decision_id=decision_id or f"decision:{task_id}",
            task_id=task_id,
            actor_id=actor_id,
            actor_type=actor_type,
            outcome=outcome,
            reason=reason,
            decided_at=current,
        )
        action_request = None
        if outcome is DecisionOutcome.ACCEPT:
            action_request = NamedActionRequest(
                request_id=f"named-action-request:{task_id}",
                action_name=task.proposal.action_name,
                action_arguments=task.proposal.action_arguments,
                task_id=task_id,
                proposal_id=task.proposal.proposal_id,
                decision_id=decision.decision_id,
                actor_id=actor_id,
                actor_type=actor_type,
                scope=task.proposal.scope,
                provenance_ref=task.proposal.provenance_ref,
                idempotency_key=(
                    f"{task.proposal.scope.tenant_id}:"
                    f"{task.proposal.action_name}:{task.proposal.proposal_id}"
                ),
            )
        decided = replace(
            task,
            status=GateStatus.DECIDED,
            decision=decision,
            action_request=action_request,
        )
        self._tasks[task_id] = decided
        return decided, action_request


__all__ = ["InMemoryHumanGate"]
