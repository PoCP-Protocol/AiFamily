"""Bind one completed ExperienceRun draft to the Human Gate boundary.

This adapter closes the otherwise implicit link between a run checkpoint and a
reviewable action proposal.  It does not execute a Named Action or write a
domain fact.  The first implementation deliberately targets the synchronous
in-memory gate used by the development/test vertical slice; the same static
validation helpers can be reused by a durable gate adapter later.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Protocol

from backend.intelligence.human_gate.contracts import (
    ActionProposal,
    ActorType,
    DecisionOutcome,
    GateScope,
    HumanTask,
    NamedActionRequest,
)
from backend.intelligence.human_gate.errors import HumanGateError
from backend.intelligence.human_gate.gate import InMemoryHumanGate
from backend.intelligence.human_gate.persistence import SqlAlchemyHumanGate
from backend.intelligence.model_gateway.contracts import ModelDraft
from backend.platform.audit import AuditRecorder

from .runs import DurableExperienceRun, RunState

RUN_ID_ARGUMENT = "run_id"
EXPERIENCE_RUN_REF_ARGUMENT = "experience_run_ref"


class HumanGateSubmitter(Protocol):
    """Small synchronous port implemented by :class:`InMemoryHumanGate`."""

    def submit_model_draft(self, draft: ModelDraft, **kwargs: object) -> HumanTask: ...

    def get(self, task_id: str) -> HumanTask: ...

    def decide(
        self, task_id: str, **kwargs: object
    ) -> tuple[HumanTask, NamedActionRequest | None]: ...


def experience_run_ref(run: DurableExperienceRun) -> str:
    """Return the deterministic, scope-qualified reference for ``run``."""

    return f"experience-run:{run.tenant_id}:{run.family_id}:{run.run_id}"


def _assert_run_succeeded(run: DurableExperienceRun) -> None:
    if not isinstance(run, DurableExperienceRun):
        raise HumanGateError("EXPERIENCE_RUN_REQUIRED", "a DurableExperienceRun is required")
    if run.state is not RunState.SUCCEEDED:
        raise HumanGateError(
            "EXPERIENCE_RUN_NOT_SUCCEEDED",
            "only a successfully generated ExperienceRun may enter Human Gate",
        )


def _assert_run_draft_binding(
    run: DurableExperienceRun,
    draft: ModelDraft,
    scope: GateScope,
) -> None:
    _assert_run_succeeded(run)
    if not isinstance(scope, GateScope):
        raise HumanGateError("EXPERIENCE_SCOPE_REQUIRED", "a GateScope is required")
    checkpoint = run.latest_checkpoint
    if checkpoint is None or checkpoint.draft_payload is None:
        raise HumanGateError(
            "EXPERIENCE_DRAFT_CHECKPOINT_REQUIRED",
            "the run has no replayable DRAFT checkpoint",
        )
    if not isinstance(draft, ModelDraft):
        raise HumanGateError("DRAFT_REQUIRED", "a ModelDraft is required")
    if draft.status != "DRAFT" or draft.may_mutate_business_state:
        raise HumanGateError("DRAFT_REQUIRED", "only a non-mutating DRAFT may enter Human Gate")
    if dict(checkpoint.draft_payload) != dict(draft.output):
        raise HumanGateError(
            "EXPERIENCE_DRAFT_MISMATCH",
            "the ModelDraft does not match the run's latest DRAFT checkpoint",
        )
    if (
        scope.tenant_id != run.tenant_id
        or scope.family_id != run.family_id
        or scope.subject_ids != run.subject_ids
    ):
        raise HumanGateError("EXPERIENCE_SCOPE_MISMATCH", "run and Human Gate scope differ")
    if scope.correlation_id != run.snapshot.request_ref:
        raise HumanGateError(
            "EXPERIENCE_CORRELATION_MISMATCH",
            "GateScope.correlation_id must equal ExperienceRun.request_ref",
        )


def bound_action_arguments(
    run: DurableExperienceRun,
    action_arguments: Mapping[str, object],
) -> dict[str, object]:
    """Return immutable-bound arguments, rejecting caller-supplied drift."""

    if not isinstance(action_arguments, Mapping):
        raise HumanGateError("INVALID_CONTRACT", "action_arguments must be a mapping")
    expected_ref = experience_run_ref(run)
    supplied_run_id = action_arguments.get(RUN_ID_ARGUMENT)
    if supplied_run_id is not None and supplied_run_id != run.run_id:
        raise HumanGateError("EXPERIENCE_RUN_REF_MISMATCH", "run_id does not match the run")
    supplied_ref = action_arguments.get(EXPERIENCE_RUN_REF_ARGUMENT)
    if supplied_ref is not None and supplied_ref != expected_ref:
        raise HumanGateError(
            "EXPERIENCE_RUN_REF_MISMATCH",
            "experience_run_ref does not match the run",
        )
    result = dict(action_arguments)
    result[RUN_ID_ARGUMENT] = run.run_id
    result[EXPERIENCE_RUN_REF_ARGUMENT] = expected_ref
    return result


def assert_named_action_binding(
    run: DurableExperienceRun,
    request: NamedActionRequest,
) -> None:
    """Fail closed if an accepted request has lost its run binding."""

    if not isinstance(request, NamedActionRequest):
        raise HumanGateError("NAMED_ACTION_REQUIRED", "a NamedActionRequest is required")
    _assert_scope_binding(run, request.scope)
    args = request.action_arguments
    if (
        args.get(RUN_ID_ARGUMENT) != run.run_id
        or args.get(EXPERIENCE_RUN_REF_ARGUMENT) != experience_run_ref(run)
    ):
        raise HumanGateError("EXPERIENCE_RUN_REF_MISMATCH", "accepted request lost its run binding")


def _assert_scope_binding(run: DurableExperienceRun, scope: GateScope) -> None:
    if (
        scope.tenant_id != run.tenant_id
        or scope.family_id != run.family_id
        or scope.subject_ids != run.subject_ids
        or scope.correlation_id != run.snapshot.request_ref
    ):
        raise HumanGateError("EXPERIENCE_SCOPE_MISMATCH", "run and Human Gate scope differ")


class ExperienceRunHumanGateBridge:
    """Submit/decide a run-bound proposal without touching a business domain."""

    def __init__(self, gate: HumanGateSubmitter | None = None) -> None:
        self._gate = gate or InMemoryHumanGate()

    @property
    def gate(self) -> HumanGateSubmitter:
        return self._gate

    def submit_model_draft(
        self,
        run: DurableExperienceRun,
        draft: ModelDraft,
        *,
        draft_id: str,
        proposal_id: str,
        action_name: str,
        action_arguments: Mapping[str, object],
        scope: GateScope,
        allowed_actor_types: tuple[ActorType, ...],
        risk_level: str,
        provenance_ref: str,
        now: datetime | None = None,
        ttl: timedelta = timedelta(hours=24),
    ) -> HumanTask:
        _assert_run_draft_binding(run, draft, scope)
        return self._gate.submit_model_draft(
            draft,
            draft_id=draft_id,
            proposal_id=proposal_id,
            action_name=action_name,
            action_arguments=bound_action_arguments(run, action_arguments),
            scope=scope,
            allowed_actor_types=allowed_actor_types,
            risk_level=risk_level,
            provenance_ref=provenance_ref,
            now=now,
            ttl=ttl,
        )

    def decide(
        self,
        run: DurableExperienceRun,
        task_id: str,
        *,
        actor_id: str,
        actor_type: ActorType | str,
        outcome: DecisionOutcome | str,
        reason: str | None = None,
        decision_id: str | None = None,
        now: datetime | None = None,
    ) -> tuple[HumanTask, NamedActionRequest | None]:
        _assert_run_succeeded(run)
        task = self._gate.get(task_id)
        _assert_scope_binding(run, task.proposal.scope)
        decided, request = self._gate.decide(
            task_id,
            actor_id=actor_id,
            actor_type=actor_type,
            outcome=outcome,
            reason=reason,
            decision_id=decision_id,
            now=now,
        )
        if request is not None:
            assert_named_action_binding(run, request)
        return decided, request


class AsyncExperienceRunHumanGateBridge:
    """Async adapter for the durable :class:`SqlAlchemyHumanGate`.

    The adapter stages Human Gate rows and audit events in the caller-owned
    session.  ``flush_audit``/``commit``/``rollback`` are explicit delegates;
    no method commits implicitly, so a caller can keep proposal/decision and
    its audit trail in one transaction.
    """

    def __init__(self, gate: SqlAlchemyHumanGate) -> None:
        self._gate = gate

    async def submit_model_draft(
        self,
        run: DurableExperienceRun,
        draft: ModelDraft,
        *,
        draft_id: str,
        proposal_id: str,
        action_name: str,
        action_arguments: Mapping[str, object],
        scope: GateScope,
        allowed_actor_types: tuple[ActorType, ...],
        risk_level: str,
        provenance_ref: str,
        recorder: AuditRecorder,
        task_id: str | None = None,
        now: datetime | None = None,
        ttl: timedelta = timedelta(hours=24),
    ) -> HumanTask:
        _assert_run_draft_binding(run, draft, scope)
        created_at = now or datetime.now(UTC)
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise HumanGateError("INVALID_CONTRACT", "now must be timezone-aware")

        # Preserve the first server-created window on a replay, matching the
        # in-memory adapter and preventing clock metadata from becoming part
        # of the proposal idempotency content.
        resolved_task_id = task_id or f"human-task:{scope.tenant_id}:{proposal_id}"
        try:
            existing = await self._gate.get(resolved_task_id)
        except HumanGateError as exc:
            if exc.code != "TASK_NOT_FOUND":
                raise
        else:
            if existing.proposal.expires_at - existing.proposal.created_at == ttl:
                created_at = existing.proposal.created_at

        proposal = ActionProposal(
            proposal_id=proposal_id,
            draft_id=draft_id,
            draft_status=draft.status,
            action_name=action_name,
            action_arguments=bound_action_arguments(run, action_arguments),
            scope=scope,
            allowed_actor_types=allowed_actor_types,
            risk_level=risk_level,
            provenance_ref=provenance_ref,
            created_at=created_at,
            expires_at=created_at + ttl,
        )
        return await self._gate.submit(proposal, recorder=recorder, task_id=task_id)

    async def decide(
        self,
        run: DurableExperienceRun,
        task_id: str,
        *,
        actor_id: str,
        actor_type: ActorType | str,
        outcome: DecisionOutcome | str,
        recorder: AuditRecorder,
        reason: str | None = None,
        decision_id: str | None = None,
        now: datetime | None = None,
    ) -> tuple[HumanTask, NamedActionRequest | None]:
        _assert_run_succeeded(run)
        task = await self._gate.get(task_id)
        _assert_scope_binding(run, task.proposal.scope)
        decided, request = await self._gate.decide(
            task_id,
            actor_id=actor_id,
            actor_type=actor_type,
            outcome=outcome,
            recorder=recorder,
            reason=reason,
            decision_id=decision_id,
            now=now,
        )
        if request is not None:
            assert_named_action_binding(run, request)
        return decided, request

    async def flush_audit(self, recorder: AuditRecorder) -> int:
        return await self._gate.flush_audit(recorder)

    async def commit(self) -> None:
        await self._gate.commit()

    async def rollback(self) -> None:
        await self._gate.rollback()


__all__ = [
    "EXPERIENCE_RUN_REF_ARGUMENT",
    "RUN_ID_ARGUMENT",
    "ExperienceRunHumanGateBridge",
    "AsyncExperienceRunHumanGateBridge",
    "assert_named_action_binding",
    "bound_action_arguments",
    "experience_run_ref",
]
