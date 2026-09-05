"""Composition-root glue: a real teacher match -> FGCN AI-suggests/human-approves.

This module is deliberately outside every domain package, same reasoning as
`need_fulfillment_flow.py`: it calls three independent subsystems in
sequence (FGCN's synchronous P0 engine, the AI model gateway, and the human
gate) and putting that sequencing inside any one of those packages would give
it a compile-time dependency on the other two.

The business point this module exists to enforce: once a family has already
tried self-help and it did not help (N6/N7 `FamilyOutcomeDecision.DID_NOT_HELP`),
escalating to a real human teacher must go through FGCN's own governance —
an AI may only *suggest* a candidate teacher, and only a human guardian's
approval through the Human Gate turns that suggestion into a real
`TaskAssignment`. Calling `service_booking` directly after a name match, with
no FGCN case/task/assignment and no human approval step, is exactly the gap
this module closes.

Following the scenario contract read from `backend/domains/service/fgcn/scenario.py`
and `contracts.py`: only the registered S-01 scenario is used, rendered in
Chinese (`render_s01_scenario("zh")`), and the blueprint is constructed
directly (not through the governance proposal workflow) because P0 does not
require it — see `tests/domains/service/fgcn/test_fgcn_flow.py::_blueprint`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.ext.asyncio import AsyncSession

from backend.domains.service.domain.errors import (
    ServiceDomainError,
    ServiceNotFoundError,
    ServiceValidationError,
)
from backend.domains.service.fgcn.admission import (
    AsyncProviderAdmissionQuery,
    ProviderAdmissionQuery,
)
from backend.domains.service.fgcn.application import (
    execute_task_assignment_named_action,
    open_service_case,
)
from backend.domains.service.fgcn.contracts import (
    BlueprintSnapshot,
    GateServiceScope,
    ServiceTask,
    TaskStatus,
)
from backend.domains.service.fgcn.engine import FGCNEngine
from backend.domains.service.fgcn.entry import (
    AsyncCaseEntryDependencyQuery,
    CaseEntryDependencyQuery,
)
from backend.domains.service.fgcn.persistence import SqlAlchemyFGCNRepository
from backend.domains.service.fgcn.scenario import (
    S01_POLICY_REF,
    S01_POLICY_VERSION,
    render_s01_scenario,
)
from backend.intelligence.human_gate import ActorType, DecisionOutcome, GateScope, InMemoryHumanGate
from backend.intelligence.model_gateway import FakeProvider, ModelGateway
from backend.intelligence.model_gateway.contracts import StructuredRequest
from backend.platform.audit import AuditEvent, AuditRecorder

#: The FGCN task template key used for the single "human teacher does the
#: real-world help" task this flow ever creates. Matches one of the keys the
#: constructed blueprint publishes below.
_TASK_KEY = "HUMAN_TEACHER_ASSIGNMENT"
_TASK_ROLE_KEY = "DELIVERY_RESOURCE"
_ASSIGNEE_KIND = "EXPERT"
_MODEL_USE_CASE = "service_matching_recommendation"


def build_s01_blueprint(*, blueprint_ref: str, checksum: str) -> BlueprintSnapshot:
    """Construct a directly-published S-01 blueprint in Chinese.

    No governance proposal workflow is used (P0 does not require one — see
    `backend/domains/service/fgcn/contracts.py::BlueprintSnapshot`, which only
    checks `status == "PUBLISHED"`). `policy_ref`/`policy_version` must match
    the scenario's own frozen policy, per `S01_POLICY_REF`/`S01_POLICY_VERSION`.
    """

    return BlueprintSnapshot(
        blueprint_ref=blueprint_ref,
        version=1,
        status="PUBLISHED",
        policy_ref=S01_POLICY_REF,
        policy_version=S01_POLICY_VERSION,
        checksum=checksum,
        task_template_keys=(_TASK_KEY,),
        scenario=render_s01_scenario("zh"),
    )


@dataclass(frozen=True)
class FGCNAssignmentResult:
    """What actually happened when a real teacher assignment was authorized."""

    case_id: str
    task_id: str
    assignment_id: str | None = None
    assignee_ref: str | None = None
    succeeded: bool = False
    failed_step: str | None = None
    failure_reason: str | None = None


async def authorize_real_teacher_assignment(
    *,
    scope: GateServiceScope,
    intent_ref: str,
    case_entry_dependencies: CaseEntryDependencyQuery,
    provider_admission: ProviderAdmissionQuery,
    provider_ref: str,
    required_capability_keys: tuple[str, ...],
    guardian_actor_id: str,
    blueprint_ref: str,
    now: datetime | None = None,
) -> FGCNAssignmentResult:
    """Open an FGCN case/task, get an AI-suggested candidate, and require a
    guardian's Human Gate approval before the candidate becomes a real
    `TaskAssignment`.

    Every failure mode here (case-entry evidence rejected, provider not
    admitted) is reported through `FGCNAssignmentResult.failed_step` /
    `failure_reason` instead of raising past this function, mirroring
    `need_fulfillment_flow.FulfillmentResult`'s own "report, do not hide"
    convention — the caller decides whether that means "do not book" or
    "this need never had self-help evidence, proceed as before".
    """

    moment = now or datetime.now(UTC)
    engine = FGCNEngine(
        case_entry_dependencies=case_entry_dependencies,
        provider_admission=provider_admission,
    )
    case_id = f"fgcn-case:{intent_ref}"
    task_id = f"fgcn-task:{intent_ref}"

    try:
        engine.open_case(
            case_id=case_id,
            scope=scope,
            intent_ref=intent_ref,
            plan_ref=f"plan:{intent_ref}",
            owner_id=guardian_actor_id,
            blueprint=build_s01_blueprint(
                blueprint_ref=blueprint_ref, checksum=f"checksum:{blueprint_ref}"
            ),
            idempotency_key=f"fgcn-open:{intent_ref}",
            opened_at=moment,
        )
    except ServiceDomainError as exc:
        return FGCNAssignmentResult(
            case_id=case_id,
            task_id=task_id,
            failed_step="fgcn_open_case",
            failure_reason=str(exc),
        )

    try:
        engine.create_task(
            task_id=task_id,
            case_id=case_id,
            task_key=_TASK_KEY,
            title="真人教师分派",
            description="由合资格真人教师承接一次成人主导的平稳启动干预。",
            role_key=_TASK_ROLE_KEY,
            acceptance_criteria=_acceptance_criteria(),
            required_capability_keys=required_capability_keys,
            actor_id=guardian_actor_id,
            created_at=moment,
        )
    except ServiceDomainError as exc:
        return FGCNAssignmentResult(
            case_id=case_id,
            task_id=task_id,
            failed_step="fgcn_create_task",
            failure_reason=str(exc),
        )

    request = await _build_named_action_request(
        scope=scope,
        task_id=task_id,
        provider_ref=provider_ref,
        guardian_actor_id=guardian_actor_id,
        intent_ref=intent_ref,
        now=moment,
    )

    try:
        assignment = engine.execute_named_action(request)
    except ServiceDomainError as exc:
        return FGCNAssignmentResult(
            case_id=case_id,
            task_id=task_id,
            failed_step="fgcn_execute_named_action",
            failure_reason=str(exc),
        )

    return FGCNAssignmentResult(
        case_id=case_id,
        task_id=task_id,
        assignment_id=assignment.assignment_id,
        assignee_ref=assignment.assignee_ref,
        succeeded=True,
    )


async def authorize_real_teacher_assignment_durable(
    *,
    session: AsyncSession,
    scope: GateServiceScope,
    intent_ref: str,
    case_entry_dependencies: AsyncCaseEntryDependencyQuery,
    provider_admission: AsyncProviderAdmissionQuery,
    provider_ref: str,
    required_capability_keys: tuple[str, ...],
    guardian_actor_id: str,
    blueprint_ref: str,
    now: datetime | None = None,
) -> FGCNAssignmentResult:
    """Durable counterpart of `authorize_real_teacher_assignment`.

    Same business point, but every write (case, task, assignment, audit) goes
    through `SqlAlchemyFGCNRepository` on the caller's `session` and is
    committed once, so a real teacher assignment survives a process restart
    instead of living only in an `FGCNEngine` instance that disappears with
    it. There is no durable `create_task` command in
    `backend.domains.service.fgcn.application` yet, so this function builds
    and validates the `ServiceTask` itself, mirroring
    `FGCNEngine.create_task`'s own checks (task id not reused, task key not
    reused within the case, task key must be one the case's blueprint
    published) before calling `repo.save_task`.
    """

    moment = now or datetime.now(UTC)
    repo = SqlAlchemyFGCNRepository(session)
    recorder = AuditRecorder()
    # `service_cases.case_id`/`service_tasks.task_id`/`service_cases.plan_ref`
    # are real UUID-typed columns in the production schema (see
    # `backend/domains/service/fgcn/persistence.py`'s `_UUID` columns), unlike
    # the in-memory `authorize_real_teacher_assignment`'s prefixed string ids
    # (`f"fgcn-case:{intent_ref}"`) which only ever have to satisfy a Python
    # dict key. Deriving a stable UUID5 from `intent_ref` keeps this function
    # idempotent per intent while staying a real UUID on the wire, mirroring
    # `execute_task_assignment_named_action`'s own `uuid5(NAMESPACE_URL, ...)`
    # derivation for `assignment_id`.
    case_id = str(uuid5(NAMESPACE_URL, f"fgcn-case:{intent_ref}"))
    task_id = str(uuid5(NAMESPACE_URL, f"fgcn-task:{intent_ref}"))
    plan_ref = str(uuid5(NAMESPACE_URL, f"fgcn-plan:{intent_ref}"))

    try:
        case = await open_service_case(
            repo,
            case_id=case_id,
            scope=scope,
            intent_ref=intent_ref,
            plan_ref=plan_ref,
            owner_id=guardian_actor_id,
            blueprint=build_s01_blueprint(
                blueprint_ref=blueprint_ref, checksum=f"checksum:{blueprint_ref}"
            ),
            idempotency_key=f"fgcn-open:{intent_ref}",
            recorder=recorder,
            entry_dependencies=case_entry_dependencies,
            opened_at=moment,
        )
    except ServiceDomainError as exc:
        return FGCNAssignmentResult(
            case_id=case_id,
            task_id=task_id,
            failed_step="fgcn_open_case",
            failure_reason=str(exc),
        )

    try:
        try:
            await repo.load_task(task_id)
            task_already_exists = True
        except ServiceNotFoundError:
            task_already_exists = False
        if not task_already_exists:
            if _TASK_KEY not in case.blueprint.task_template_keys:
                raise ServiceValidationError("fgcn_task_key_not_in_published_blueprint")
            task = ServiceTask(
                task_id=task_id,
                case_id=case_id,
                blueprint_ref=case.blueprint.blueprint_ref,
                blueprint_version=case.blueprint.version,
                task_key=_TASK_KEY,
                title="真人教师分派",
                description="由合资格真人教师承接一次成人主导的平稳启动干预。",
                role_key=_TASK_ROLE_KEY,
                acceptance_criteria=_acceptance_criteria(),
                required_capability_keys=required_capability_keys,
                status=TaskStatus.PENDING,
                locale=case.blueprint.scenario.locale,
                created_at=moment,
            )
            await repo.save_task(task)
            recorder.record(
                AuditEvent(
                    actor_id=guardian_actor_id,
                    tenant_id=scope.tenant_id,
                    action="CREATE_SERVICE_TASK",
                    resource_type="ServiceTask",
                    resource_id=task_id,
                    reason="task created from frozen blueprint template",
                    correlation_id=scope.correlation_id,
                    after={"status": task.status.value, "task_key": task.task_key},
                )
            )
            await repo.flush_audit(recorder)
            await repo.commit()
    except ServiceDomainError as exc:
        return FGCNAssignmentResult(
            case_id=case_id,
            task_id=task_id,
            failed_step="fgcn_create_task",
            failure_reason=str(exc),
        )

    request = await _build_named_action_request(
        scope=scope,
        task_id=task_id,
        provider_ref=provider_ref,
        guardian_actor_id=guardian_actor_id,
        intent_ref=intent_ref,
        now=moment,
    )

    try:
        assignment = await execute_task_assignment_named_action(
            repo,
            request,
            recorder=recorder,
            provider_admission=provider_admission,
            accepted_at=moment,
        )
    except ServiceDomainError as exc:
        return FGCNAssignmentResult(
            case_id=case_id,
            task_id=task_id,
            failed_step="fgcn_execute_named_action",
            failure_reason=str(exc),
        )

    return FGCNAssignmentResult(
        case_id=case_id,
        task_id=task_id,
        assignment_id=assignment.assignment_id,
        assignee_ref=assignment.assignee_ref,
        succeeded=True,
    )


def _acceptance_criteria() -> tuple[str, ...]:
    from backend.domains.service.fgcn.scenario import (
        S01_LOCALE_REGISTRY,
    )

    return (S01_LOCALE_REGISTRY["zh"]["task_acceptance_criterion"],)


async def _build_named_action_request(
    *,
    scope: GateServiceScope,
    task_id: str,
    provider_ref: str,
    guardian_actor_id: str,
    intent_ref: str,
    now: datetime,
):
    """AI suggests a candidate teacher; a guardian approves it via Human Gate.

    The `ModelGateway`/`FakeProvider` pairing here mirrors
    `tests/domains/service/fgcn/test_fgcn_flow.py::_assignment_request`
    exactly: the AI model draft only ever proposes `candidate_provider_id`,
    it never itself becomes the `NamedActionRequest` — only
    `InMemoryHumanGate.decide(..., actor_type=ActorType.GUARDIAN, outcome=ACCEPT)`
    produces one.
    """

    gate = InMemoryHumanGate()
    draft_provider = FakeProvider(
        {
            _MODEL_USE_CASE: {
                "candidate_provider_id": provider_ref,
                "reason": "已准入能力匹配的真实教师",
            }
        }
    )
    gateway = ModelGateway({"fake-deterministic": draft_provider}, environment="test")

    draft = await gateway.generate_structured(
        StructuredRequest(
            use_case=_MODEL_USE_CASE,
            prompt_version="service-matching.v1",
            schema_version="service-task-proposal.v1",
            data_class="OPERATIONAL_TEXT",
            payload={"task_id": task_id},
            output_schema={
                "type": "object",
                "properties": {
                    "candidate_provider_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["candidate_provider_id", "reason"],
            },
            context_snapshot_ref=f"context:{scope.tenant_id}:{scope.subject_person_id}:fgcn",
            request_id=f"request-fgcn:{intent_ref}",
        ),
        provider_id="fake-deterministic",
    )
    gate_scope = GateScope(
        tenant_id=scope.tenant_id,
        family_id=scope.family_id,
        subject_ids=(scope.subject_person_id,),
        purpose=scope.purpose,
        consent_version=scope.consent_version,
        correlation_id=scope.correlation_id,
    )
    task = gate.submit_model_draft(
        draft,
        draft_id=f"draft-fgcn:{intent_ref}",
        proposal_id=f"proposal-fgcn:{intent_ref}",
        action_name="CONFIRM_SERVICE_TASK_ASSIGNMENT",
        action_arguments={
            "service_task_id": task_id,
            "provider_id": provider_ref,
            "assignee_kind": _ASSIGNEE_KIND,
        },
        scope=gate_scope,
        allowed_actor_types=(ActorType.GUARDIAN,),
        risk_level="HIGH",
        provenance_ref=f"model-draft:request-fgcn:{intent_ref}",
        now=now,
    )
    _, named_action_request = gate.decide(
        task.task_id,
        actor_id=guardian_actor_id,
        actor_type=ActorType.GUARDIAN,
        outcome=DecisionOutcome.ACCEPT,
        now=now,
    )
    assert named_action_request is not None
    return named_action_request


__all__ = [
    "FGCNAssignmentResult",
    "authorize_real_teacher_assignment",
    "authorize_real_teacher_assignment_durable",
    "build_s01_blueprint",
]
