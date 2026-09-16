"""Fail-closed bridge from an accepted Assessment HumanTask to UI-03.

The legacy UI-03 command handler can create a ``GrowthIntent`` from an AI
interpretation.  This composition-layer guard makes that path consume the
durable, human-accepted ``CONFIRM_GROWTH_HYPOTHESIS`` Named Action first.
Canonical viewed-understanding receipts use ``ProductionGrowthConfirmationWiring``
and therefore do not pass through this legacy bridge.
"""

from __future__ import annotations

import hashlib
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.domains.assessment.application.growth_hypothesis_commands import (
    CONFIRM_GROWTH_HYPOTHESIS_ACTION,
    DecideGrowthHypothesisCommand,
    GrowthHypothesisCommandHandler,
)
from backend.domains.assessment.application.ports import AssessmentRepositoryPort
from backend.domains.assessment.domain.entities import GrowthHypothesisEvidence
from backend.domains.assessment.domain.errors import (
    AssessmentConflictError,
    AssessmentForbiddenError,
    AssessmentNotFoundError,
)
from backend.intelligence.agent_runtime.persistence import (
    AgentRunRecord,
    AgentRunScope,
    AgentRunStatus,
    SqlAlchemyAgentRunStore,
)
from backend.intelligence.context_engine.contracts import ContextContractError, ContextScope
from backend.intelligence.human_gate import (
    ActorType,
    DecisionOutcome,
    GateScope,
    GateStatus,
    HumanTask,
    NamedActionRequest,
)
from backend.intelligence.human_gate.errors import HumanGateError
from backend.intelligence.human_gate.persistence import SqlAlchemyHumanGate

ASSESSMENT_REVIEW_SCOPE_KIND = "assessment"
ASSESSMENT_REVIEW_USE_CASE = "assessment_interpretation"
ASSESSMENT_REVIEW_BINDING_VERSION = 1


@dataclass(frozen=True, slots=True)
class AcceptedAssessmentReview:
    """The immutable gate decision plus the AI draft it reviewed."""

    task: HumanTask
    run: AgentRunRecord


class AcceptedAssessmentReviewReader(Protocol):
    async def load(
        self,
        task_id: str,
        *,
        tenant_id: str,
        family_id: str,
    ) -> AcceptedAssessmentReview: ...


CurrentScopeResolver = Callable[
    [str, str],
    ContextScope | Awaitable[ContextScope],
]


@dataclass(frozen=True, slots=True)
class SqlAlchemyAcceptedAssessmentReviewReader:
    """Reload HumanTask and AgentRun after process restart."""

    session_factory: async_sessionmaker[AsyncSession]

    def __post_init__(self) -> None:
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("assessment review reader requires async_sessionmaker")

    async def load(
        self,
        task_id: str,
        *,
        tenant_id: str,
        family_id: str,
    ) -> AcceptedAssessmentReview:
        async with self.session_factory() as session:
            try:
                task = await SqlAlchemyHumanGate(session).get(task_id)
            except HumanGateError as exc:
                if exc.code == "TASK_NOT_FOUND":
                    raise AssessmentConflictError("human_task_reference_invalid") from exc
                raise AssessmentConflictError("human_task_unavailable") from exc

            if (
                task.proposal.scope.tenant_id != tenant_id
                or task.proposal.scope.family_id != family_id
            ):
                raise AssessmentForbiddenError("human_task_family_mismatch")

            arguments = dict(task.proposal.action_arguments)
            run_ref = _required_text(arguments, "agent_run_ref")
            replay = await SqlAlchemyAgentRunStore(session).replay(
                run_ref,
                scope=AgentRunScope(tenant_id, family_id),
            )
        if replay is None:
            raise AssessmentConflictError("reviewed_agent_run_not_found")
        return AcceptedAssessmentReview(task=task, run=replay.run)


@dataclass(frozen=True, slots=True)
class HumanGateConfirmedGrowthHypothesisHandler:
    """Allow an intent-creating legacy command only from one accepted task."""

    delegate: GrowthHypothesisCommandHandler
    repository: AssessmentRepositoryPort
    review_reader: AcceptedAssessmentReviewReader
    current_scope_resolver: CurrentScopeResolver
    expected_prompt_version: str
    expected_schema_version: str
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def __post_init__(self) -> None:
        if not callable(getattr(self.delegate, "decide", None)):
            raise TypeError("assessment decision delegate must expose decide")
        if not callable(getattr(self.repository, "load_hypothesis_evidence", None)):
            raise TypeError("assessment review repository is incomplete")
        if not callable(getattr(self.review_reader, "load", None)):
            raise TypeError("assessment review reader must expose load")
        if not callable(self.current_scope_resolver) or not callable(self.clock):
            raise TypeError("assessment review resolvers must be callable")
        if not self.expected_prompt_version.strip() or not self.expected_schema_version.strip():
            raise ValueError("assessment review execution versions are required")

    async def decide(self, command: DecideGrowthHypothesisCommand) -> dict:
        if command.decision_type not in {"CONFIRM", "EDIT"}:
            return await self.delegate.decide(command)
        if command.decision_type == "EDIT":
            # The staged action reviewed the model draft, not a later edited
            # statement.  A rewritten commitment needs its own reviewed
            # binding (the canonical viewed-understanding path supports it).
            raise AssessmentConflictError("edited_hypothesis_review_required")
        _assert_client_binding_present(command)

        evidence = await self.repository.load_hypothesis_evidence(
            command.family_id,
            command.tenant_id,
            command.assessment_session_id,
        )
        if evidence is None:
            raise AssessmentNotFoundError("growth_hypothesis_not_found")
        _assert_hypothesis_binding(command, evidence)

        try:
            scope_value = self.current_scope_resolver(
                command.family_id,
                evidence.subject_person_id,
            )
            current_scope = await scope_value if inspect.isawaitable(scope_value) else scope_value
        except (ContextContractError, PermissionError) as exc:
            raise AssessmentConflictError("human_task_scope_stale") from exc
        if not isinstance(current_scope, ContextScope):
            raise TypeError("assessment review scope resolver must return ContextScope")
        try:
            current_scope.assert_active()
        except ContextContractError as exc:
            raise AssessmentConflictError("human_task_scope_stale") from exc

        accepted = await self.review_reader.load(
            command.human_gate_receipt_ref,
            tenant_id=command.tenant_id,
            family_id=command.family_id,
        )
        request = _accepted_request(
            accepted,
            command=command,
            evidence=evidence,
            current_scope=current_scope,
            expected_prompt_version=self.expected_prompt_version,
            expected_schema_version=self.expected_schema_version,
            now=self.clock(),
        )
        # The server-owned NamedAction identity, not a second client-selected
        # key, is the durable exactly-once identity of this fact transition.
        return await self.delegate.decide(
            replace(command, idempotency_key=_domain_idempotency_key(request.idempotency_key))
        )


def _assert_client_binding_present(command: DecideGrowthHypothesisCommand) -> None:
    required = (
        command.scope_ref,
        command.reviewed_draft_ref,
        command.provenance_ref,
        command.human_gate_receipt_ref,
    )
    if not all(isinstance(value, str) and value.strip() for value in required):
        raise AssessmentConflictError("human_task_binding_required")
    if command.signal_version < 1 or command.draft_version < 1:
        raise AssessmentConflictError("human_task_version_binding_required")


def _assert_hypothesis_binding(
    command: DecideGrowthHypothesisCommand,
    evidence: GrowthHypothesisEvidence,
) -> None:
    expected = (
        f"ASSESSMENT:{evidence.assessment_session_id}:{evidence.tool_ref}"
        f":v{evidence.tool_version}:H1"
    )
    if command.hypothesis_ref != expected:
        raise AssessmentConflictError("growth_hypothesis_reference_mismatch")
    if command.signal_version != evidence.tool_version:
        raise AssessmentConflictError("growth_hypothesis_signal_version_mismatch")


def _accepted_request(
    accepted: AcceptedAssessmentReview,
    *,
    command: DecideGrowthHypothesisCommand,
    evidence: GrowthHypothesisEvidence,
    current_scope: ContextScope,
    expected_prompt_version: str,
    expected_schema_version: str,
    now: datetime,
) -> NamedActionRequest:
    task = accepted.task
    if not isinstance(task, HumanTask):
        raise TypeError("assessment review reader returned an invalid HumanTask")
    proposal = task.proposal
    if (
        proposal.scope.tenant_id != command.tenant_id
        or proposal.scope.family_id != command.family_id
    ):
        raise AssessmentForbiddenError("human_task_family_mismatch")
    if task.status is not GateStatus.DECIDED:
        if task.status is GateStatus.EXPIRED or now >= proposal.expires_at:
            raise AssessmentConflictError("human_task_expired")
        raise AssessmentConflictError("human_task_acceptance_required")
    if now >= proposal.expires_at:
        raise AssessmentConflictError("human_task_expired")
    if task.decision is None or task.decision.outcome is not DecisionOutcome.ACCEPT:
        raise AssessmentConflictError("human_task_acceptance_required")
    request = task.action_request
    if request is None:
        raise AssessmentConflictError("human_task_acceptance_required")
    if task.decision.actor_id != command.actor_id or request.actor_id != command.actor_id:
        raise AssessmentForbiddenError("human_task_actor_mismatch")
    if request.actor_type is not ActorType.GUARDIAN:
        raise AssessmentForbiddenError("human_task_guardian_required")
    if (
        proposal.action_name != CONFIRM_GROWTH_HYPOTHESIS_ACTION
        or request.action_name != CONFIRM_GROWTH_HYPOTHESIS_ACTION
    ):
        raise AssessmentConflictError("human_task_action_mismatch")
    _assert_scope_binding(request.scope, current_scope, command)
    _assert_draft_binding(
        accepted,
        command=command,
        evidence=evidence,
        expected_prompt_version=expected_prompt_version,
        expected_schema_version=expected_schema_version,
    )
    return request


def _assert_scope_binding(
    reviewed: GateScope,
    current: ContextScope,
    command: DecideGrowthHypothesisCommand,
) -> None:
    current.assert_active()
    if (
        reviewed.tenant_id != current.tenant_id
        or reviewed.family_id != current.family_id
        or reviewed.subject_ids != current.subject_ids
        or reviewed.purpose != current.purpose
        or reviewed.consent_version != current.consent_version
        or reviewed.region_id != current.region_id
        or reviewed.deletion_ref != current.deletion_ref
    ):
        raise AssessmentConflictError("human_task_scope_stale")
    expected_ref = (
        f"family://{current.tenant_id}/{current.family_id}/{ASSESSMENT_REVIEW_SCOPE_KIND}"
    )
    if command.scope_ref != expected_ref:
        raise AssessmentConflictError("human_task_scope_reference_mismatch")


def _assert_draft_binding(
    accepted: AcceptedAssessmentReview,
    *,
    command: DecideGrowthHypothesisCommand,
    evidence: GrowthHypothesisEvidence,
    expected_prompt_version: str,
    expected_schema_version: str,
) -> None:
    task = accepted.task
    proposal = task.proposal
    request = task.action_request
    assert request is not None
    arguments = dict(request.action_arguments)
    if dict(proposal.action_arguments) != arguments:
        raise AssessmentConflictError("human_task_payload_mismatch")
    if _required_text(arguments, "agent_run_ref") != accepted.run.run_id:
        raise AssessmentConflictError("human_task_agent_run_mismatch")
    if _required_text(arguments, "agent_request_ref") != accepted.run.request_id:
        raise AssessmentConflictError("human_task_agent_request_mismatch")
    if _required_text(arguments, "draft_ref") != proposal.draft_id:
        raise AssessmentConflictError("human_task_draft_reference_mismatch")
    if arguments.get("recommendation_status") != "PROPOSED":
        raise AssessmentConflictError("human_task_payload_status_mismatch")
    if command.reviewed_draft_ref != proposal.draft_id:
        raise AssessmentConflictError("reviewed_draft_binding_mismatch")
    if command.draft_version != ASSESSMENT_REVIEW_BINDING_VERSION:
        raise AssessmentConflictError("reviewed_draft_version_mismatch")
    if (
        command.provenance_ref != proposal.provenance_ref
        or request.provenance_ref != proposal.provenance_ref
    ):
        raise AssessmentConflictError("reviewed_draft_provenance_mismatch")

    run = accepted.run
    if (
        run.status is not AgentRunStatus.SUCCEEDED
        or run.use_case != ASSESSMENT_REVIEW_USE_CASE
        or run.tenant_id != command.tenant_id
        or run.family_id != command.family_id
        or run.draft is None
        or run.draft.status != "DRAFT"
    ):
        raise AssessmentConflictError("reviewed_agent_run_invalid")
    if run.draft.output.get("assessment_ref") != evidence.assessment_session_id:
        raise AssessmentConflictError("reviewed_draft_assessment_mismatch")
    if (
        run.draft.provenance.prompt_version != expected_prompt_version
        or run.draft.provenance.schema_version != expected_schema_version
    ):
        raise AssessmentConflictError("reviewed_draft_execution_version_stale")


def _required_text(arguments: dict[str, object], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise AssessmentConflictError(f"human_task_{name}_missing")
    return value


def _domain_idempotency_key(source: str) -> str:
    digest = hashlib.sha256(source.encode()).hexdigest()
    return f"assessment-action:{digest}"


__all__ = [
    "ASSESSMENT_REVIEW_BINDING_VERSION",
    "AcceptedAssessmentReview",
    "AcceptedAssessmentReviewReader",
    "HumanGateConfirmedGrowthHypothesisHandler",
    "SqlAlchemyAcceptedAssessmentReviewReader",
]
