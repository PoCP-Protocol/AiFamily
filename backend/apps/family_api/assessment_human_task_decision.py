"""Governed HTTP application service for Assessment HumanTask decisions.

The mobile client owns only the human outcome and optional reason. Identity,
scope, draft, provenance and version bindings are reloaded from durable server
state and returned only after ``ProductionAgentRuntime.decide_review`` accepts
the decision. The service never executes the accepted Named Action.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.apps.family_api.assessment_review_confirmation import (
    ASSESSMENT_REVIEW_BINDING_VERSION,
    ASSESSMENT_REVIEW_USE_CASE,
    SqlAlchemyAcceptedAssessmentReviewReader,
)
from backend.apps.family_api.production_agent_wiring import (
    ASSESSMENT_REVIEW_ACTION,
    ProductionAgentRuntime,
    ProductionAgentRuntimeResolver,
)
from backend.domains.assessment.api.dependencies import FamilyContext
from backend.domains.assessment.application.ports import AssessmentRepositoryPort
from backend.domains.assessment.domain.entities import GrowthHypothesisEvidence
from backend.domains.assessment.domain.errors import (
    AssessmentConflictError,
    AssessmentNotFoundError,
    AssessmentValidationError,
)
from backend.intelligence.agent_runtime.persistence import AgentRunStatus
from backend.intelligence.context_engine.contracts import (
    ContextContractError,
    ContextScope,
    DataClass,
)
from backend.intelligence.human_gate.contracts import (
    ActorType,
    DecisionOutcome,
    GateStatus,
    HumanTask,
    NamedActionRequest,
)
from backend.intelligence.human_gate.errors import HumanGateError
from backend.intelligence.human_gate.persistence import SqlAlchemyHumanGate

DecisionValue = Literal["ACCEPT", "REJECT"]


@dataclass(frozen=True, slots=True)
class AssessmentHumanTaskDecisionApplication:
    """Decide one visible Assessment review against a freshly resolved scope."""

    identity: FamilyContext
    session_factory: async_sessionmaker[AsyncSession]
    runtime_resolver: ProductionAgentRuntimeResolver
    repository: AssessmentRepositoryPort
    expected_prompt_version: str
    expected_schema_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.identity, FamilyContext):
            raise TypeError("assessment human-task identity is required")
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("assessment human-task session_factory is required")
        if not isinstance(self.runtime_resolver, ProductionAgentRuntimeResolver):
            raise TypeError("assessment human-task runtime_resolver is required")
        if not callable(getattr(self.repository, "load_hypothesis_evidence", None)):
            raise TypeError("assessment human-task repository is incomplete")
        if not self.expected_prompt_version.strip() or not self.expected_schema_version.strip():
            raise ValueError("assessment human-task execution versions are required")

    async def decide(
        self,
        task_id: str,
        *,
        outcome: DecisionValue,
        reason: str | None,
        idempotency_key: str,
    ) -> dict[str, object]:
        key = _idempotency_key(idempotency_key)
        task = await self._visible_task(task_id)
        subject_id = _review_subject(task)
        runtime = await self._current_runtime(subject_id)
        binding = None
        if outcome == DecisionOutcome.ACCEPT.value:
            binding = await self._confirmation_binding(task, runtime.scope)

        decision_id = assessment_review_decision_id(
            tenant_id=self.identity.tenant_id,
            family_id=self.identity.family_id,
            task_id=task.task_id,
            idempotency_key=key,
        )
        try:
            decided, request = await runtime.decide_review(
                task.task_id,
                actor_id=self.identity.person_id,
                actor_type=ActorType.GUARDIAN,
                outcome=outcome,
                decision_id=decision_id,
                reason=reason,
            )
        except IntegrityError as exc:
            raise AssessmentConflictError("assessment_human_task_decision_id_conflict") from exc
        except HumanGateError as exc:
            raise _human_gate_error(exc) from exc
        except ContextContractError as exc:
            raise AssessmentConflictError("assessment_human_task_scope_stale") from exc

        if outcome == DecisionOutcome.ACCEPT.value:
            _assert_accepted_request(decided, request, binding)
        elif request is not None:
            raise AssessmentConflictError("assessment_human_task_rejection_invalid")
        return _decision_receipt(decided, binding=binding)

    async def _visible_task(self, task_id: str) -> HumanTask:
        if not isinstance(task_id, str) or not task_id.strip():
            raise AssessmentNotFoundError("assessment_human_task_not_found")
        async with self.session_factory() as session:
            try:
                task = await SqlAlchemyHumanGate(session).get(task_id)
            except HumanGateError as exc:
                if exc.code == "TASK_NOT_FOUND":
                    raise AssessmentNotFoundError("assessment_human_task_not_found") from exc
                raise AssessmentConflictError("assessment_human_task_unavailable") from exc
        scope = task.proposal.scope
        if (
            scope.tenant_id != self.identity.tenant_id
            or scope.family_id != self.identity.family_id
            or task.proposal.action_name != ASSESSMENT_REVIEW_ACTION
        ):
            raise AssessmentNotFoundError("assessment_human_task_not_found")
        return task

    async def _current_runtime(self, subject_id: str) -> ProductionAgentRuntime:
        try:
            runtime = await self.runtime_resolver.resolve_for_subject(
                self.identity.family_id,
                subject_id,
            )
        except (ContextContractError, PermissionError, ValueError) as exc:
            raise AssessmentConflictError("assessment_human_task_scope_stale") from exc
        if not isinstance(runtime, ProductionAgentRuntime):
            raise TypeError("assessment human-task resolver returned an invalid runtime")
        scope = runtime.scope
        if (
            scope.tenant_id != self.identity.tenant_id
            or scope.family_id != self.identity.family_id
            or scope.subject_ids != (subject_id,)
            or scope.purpose.lower() != "assessment"
            or scope.data_class is not DataClass.MINOR_PERSONAL_DATA
        ):
            raise AssessmentConflictError("assessment_human_task_scope_stale")
        try:
            scope.assert_active()
        except ContextContractError as exc:
            raise AssessmentConflictError("assessment_human_task_scope_stale") from exc
        return runtime

    async def _confirmation_binding(
        self,
        task: HumanTask,
        current_scope: ContextScope,
    ) -> dict[str, object]:
        accepted = await SqlAlchemyAcceptedAssessmentReviewReader(self.session_factory).load(
            task.task_id,
            tenant_id=self.identity.tenant_id,
            family_id=self.identity.family_id,
        )
        run = accepted.run
        arguments = dict(task.proposal.action_arguments)
        assessment_ref = _required_argument(arguments, "agent_run_ref")
        if assessment_ref != run.run_id:
            raise AssessmentConflictError("assessment_human_task_agent_run_mismatch")
        if _required_argument(arguments, "draft_ref") != task.proposal.draft_id:
            raise AssessmentConflictError("assessment_human_task_draft_mismatch")
        if (
            run.status is not AgentRunStatus.SUCCEEDED
            or run.use_case != ASSESSMENT_REVIEW_USE_CASE
            or run.tenant_id != self.identity.tenant_id
            or run.family_id != self.identity.family_id
            or run.draft is None
            or run.draft.status != "DRAFT"
        ):
            raise AssessmentConflictError("assessment_human_task_agent_run_invalid")
        if (
            run.draft.provenance.prompt_version != self.expected_prompt_version
            or run.draft.provenance.schema_version != self.expected_schema_version
        ):
            raise AssessmentConflictError("assessment_human_task_execution_version_stale")
        session_id = run.draft.output.get("assessment_ref")
        if not isinstance(session_id, str) or not session_id.strip():
            raise AssessmentConflictError("assessment_human_task_assessment_ref_missing")
        evidence = await self.repository.load_hypothesis_evidence(
            self.identity.family_id,
            self.identity.tenant_id,
            session_id,
        )
        if evidence is None:
            raise AssessmentConflictError("assessment_human_task_evidence_unavailable")
        _assert_evidence_scope(evidence, current_scope)
        return {
            "subject_person_id": evidence.subject_person_id,
            "assessment_session_id": evidence.assessment_session_id,
            "hypothesis_ref": _hypothesis_ref(evidence),
            "scope_ref": (
                f"family://{self.identity.tenant_id}/{self.identity.family_id}/assessment"
            ),
            "signal_version": evidence.tool_version,
            "reviewed_draft_ref": task.proposal.draft_id,
            "draft_version": ASSESSMENT_REVIEW_BINDING_VERSION,
            "provenance_ref": task.proposal.provenance_ref,
            "human_gate_receipt_ref": task.task_id,
        }


def assessment_review_decision_id(
    *,
    tenant_id: str,
    family_id: str,
    task_id: str,
    idempotency_key: str,
) -> str:
    """Return the fixed-length, restart-stable decision identity."""

    material = "\x1f".join((tenant_id, family_id, task_id, idempotency_key))
    return f"assessment-decision:{hashlib.sha256(material.encode()).hexdigest()}"


def _idempotency_key(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AssessmentValidationError("idempotency_key_required")
    normalised = value.strip()
    if len(normalised) > 256:
        raise AssessmentValidationError("idempotency_key_too_long")
    return normalised


def _review_subject(task: HumanTask) -> str:
    subjects = task.proposal.scope.subject_ids
    if len(subjects) != 1:
        raise AssessmentNotFoundError("assessment_human_task_not_found")
    return subjects[0]


def _required_argument(arguments: dict[str, object], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise AssessmentConflictError(f"assessment_human_task_{name}_missing")
    return value


def _assert_evidence_scope(
    evidence: GrowthHypothesisEvidence,
    current_scope: ContextScope,
) -> None:
    if evidence.subject_person_id != current_scope.subject_id:
        raise AssessmentConflictError("assessment_human_task_evidence_scope_mismatch")


def _hypothesis_ref(evidence: GrowthHypothesisEvidence) -> str:
    return (
        f"ASSESSMENT:{evidence.assessment_session_id}:{evidence.tool_ref}"
        f":v{evidence.tool_version}:H1"
    )


def _assert_accepted_request(
    task: HumanTask,
    request: NamedActionRequest | None,
    binding: dict[str, object] | None,
) -> None:
    if (
        task.status is not GateStatus.DECIDED
        or task.decision is None
        or task.decision.outcome is not DecisionOutcome.ACCEPT
        or request is None
        or binding is None
        or request.task_id != task.task_id
        or request.action_name != ASSESSMENT_REVIEW_ACTION
        or request.actor_id != task.decision.actor_id
        or request.provenance_ref != binding["provenance_ref"]
        or dict(request.action_arguments) != dict(task.proposal.action_arguments)
    ):
        raise AssessmentConflictError("assessment_human_task_acceptance_invalid")


def _human_gate_error(error: HumanGateError) -> Exception:
    if error.code == "TASK_NOT_FOUND":
        return AssessmentNotFoundError("assessment_human_task_not_found")
    if error.code == "TASK_EXPIRED":
        return AssessmentConflictError("assessment_human_task_expired")
    if error.code in {"TASK_ALREADY_DECIDED", "PROPOSAL_REPLAY_MISMATCH"}:
        return AssessmentConflictError("assessment_human_task_decision_conflict")
    if error.code in {"DECISION_REASON_REQUIRED", "INVALID_DECISION"}:
        return AssessmentValidationError("assessment_human_task_decision_invalid")
    if error.code in {"REVIEWER_NOT_ALLOWED", "HUMAN_REVIEWER_REQUIRED"}:
        return AssessmentNotFoundError("assessment_human_task_not_found")
    return AssessmentConflictError("assessment_human_task_unavailable")


def _decision_receipt(
    task: HumanTask,
    *,
    binding: dict[str, object] | None,
) -> dict[str, object]:
    decision = task.decision
    if task.status is not GateStatus.DECIDED or decision is None:
        raise AssessmentConflictError("assessment_human_task_decision_unavailable")
    return {
        "task_id": task.task_id,
        "decision_id": decision.decision_id,
        "status": task.status.value,
        "outcome": decision.outcome.value,
        "reason": decision.reason,
        "decided_at": decision.decided_at.isoformat(),
        "binding": binding if decision.outcome is DecisionOutcome.ACCEPT else None,
    }


__all__ = [
    "AssessmentHumanTaskDecisionApplication",
    "assessment_review_decision_id",
]
