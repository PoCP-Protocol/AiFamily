"""Durable storage for the Human Gate aggregate.

The in-memory gate is useful for contract tests, but it cannot carry an
accepted action across a process restart.  This adapter stores the complete
reviewable proposal, its decision, and the resulting ``NamedActionRequest``
in one row so the aggregate can be rehydrated without asking a model to
recreate the past.

This module deliberately has no import from a business domain.  It records a
Human Gate outcome and leaves execution of the request to the owning domain;
the FGCN worker is the consumer of that request, not the gate itself.

Transaction model
-----------------
``submit`` and ``decide`` stage changes in the caller's ``AsyncSession`` and
require an ``AuditRecorder``.  They do not commit.  The caller must flush the
recorder and commit the same session, so a task/decision and its audit event
are visible together.  This is the same transaction rule used by the FGCN
repository and prevents a durable decision with no audit trail.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, DateTime, Index, MetaData, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

from backend.platform.audit import AuditEvent, AuditRecorder

from .contracts import (
    HUMAN_ACTOR_TYPES,
    ActionProposal,
    ActorType,
    DecisionOutcome,
    GateScope,
    GateStatus,
    HumanDecision,
    HumanTask,
    NamedActionRequest,
)
from .errors import HumanGateError

HUMAN_TASKS_TABLE = "ai_human_tasks"
_TZ_DATETIME = DateTime(timezone=True)
_NULLABLE_JSON = JSON(none_as_null=True)


class HumanGateBase(DeclarativeBase):
    """Metadata owned by the Human Gate persistence adapter."""

    metadata = MetaData()


class HumanTaskRow(HumanGateBase):
    """One durable HumanTask aggregate.

    The proposal/decision/request payloads are snapshots rather than ORM
    relationships.  They preserve the exact immutable value objects that were
    reviewed, while the scalar columns provide tenant, expiry, and replay
    indexes for workers and operational queries.
    """

    __tablename__ = HUMAN_TASKS_TABLE
    __table_args__ = (
        CheckConstraint(
            "status IN ('OPEN', 'DECIDED', 'EXPIRED')",
            name="ck_ai_human_tasks_status",
        ),
        CheckConstraint(
            "(status IN ('OPEN', 'EXPIRED') AND decision_payload IS NULL "
            "AND action_request_payload IS NULL) OR "
            "(status = 'DECIDED' AND decision_payload IS NOT NULL)",
            name="ck_ai_human_tasks_lifecycle_shape",
        ),
        Index(
            "uq_ai_human_tasks_tenant_proposal",
            "tenant_id",
            "proposal_id",
            unique=True,
        ),
        Index(
            "uq_ai_human_tasks_decision_id",
            "decision_id",
            unique=True,
            postgresql_where=sa.text("decision_id IS NOT NULL"),
            sqlite_where=sa.text("decision_id IS NOT NULL"),
        ),
        Index(
            "uq_ai_human_tasks_request_id",
            "request_id",
            unique=True,
            postgresql_where=sa.text("request_id IS NOT NULL"),
            sqlite_where=sa.text("request_id IS NOT NULL"),
        ),
    )

    task_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    family_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    subject_ids: Mapped[list] = mapped_column(_NULLABLE_JSON, nullable=False)
    purpose: Mapped[str] = mapped_column(String(96), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(160), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    proposal_id: Mapped[str] = mapped_column(String(160), nullable=False)
    draft_id: Mapped[str] = mapped_column(String(160), nullable=False)
    action_name: Mapped[str] = mapped_column(String(128), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    provenance_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    proposal_payload: Mapped[dict] = mapped_column(_NULLABLE_JSON, nullable=False)

    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(_TZ_DATETIME, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(_TZ_DATETIME, nullable=False, index=True)

    decision_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(_TZ_DATETIME, nullable=True)
    decision_payload: Mapped[dict | None] = mapped_column(_NULLABLE_JSON, nullable=True)

    request_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    action_request_payload: Mapped[dict | None] = mapped_column(_NULLABLE_JSON, nullable=True)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise HumanGateError("INVALID_CONTRACT", f"{field_name} must be timezone-aware")
    return value


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HumanGateError("INVALID_CONTRACT", f"{field_name} is required")
    return value


def _json_ready(value: object, field_name: str) -> object:
    """Copy JSON-shaped input and reject opaque/non-JSON values early."""

    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, nested in value.items():
            if not isinstance(key, str):
                raise HumanGateError(
                    "INVALID_CONTRACT", f"{field_name} mapping keys must be strings"
                )
            result[key] = _json_ready(nested, field_name)
        return result
    if isinstance(value, (list, tuple)):
        return [_json_ready(item, field_name) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise HumanGateError("INVALID_CONTRACT", f"{field_name} contains a non-JSON value")


def _json_object(value: object, field_name: str) -> dict[str, Any]:
    ready = _json_ready(value, field_name)
    if not isinstance(ready, dict):
        raise HumanGateError("INVALID_CONTRACT", f"{field_name} must be a JSON object")
    try:
        # ``allow_nan=False`` matters because PostgreSQL JSON rejects NaN and
        # accepting it on SQLite would make the two persistence paths diverge.
        encoded = json.dumps(ready, ensure_ascii=False, allow_nan=False, sort_keys=True)
        decoded = json.loads(encoded)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HumanGateError("INVALID_CONTRACT", f"{field_name} is not valid JSON") from exc
    if not isinstance(decoded, dict):  # pragma: no cover - guarded above
        raise HumanGateError("INVALID_CONTRACT", f"{field_name} must be a JSON object")
    return decoded


def _scope_payload(scope: GateScope) -> dict[str, object]:
    return {
        "tenant_id": scope.tenant_id,
        "family_id": scope.family_id,
        "subject_ids": list(scope.subject_ids),
        "purpose": scope.purpose,
        "consent_version": scope.consent_version,
        "correlation_id": scope.correlation_id,
    }


def _proposal_payload(proposal: ActionProposal) -> dict[str, Any]:
    return _json_object(
        {
            "proposal_id": proposal.proposal_id,
            "draft_id": proposal.draft_id,
            "draft_status": proposal.draft_status,
            "action_name": proposal.action_name,
            "action_arguments": proposal.action_arguments,
            "scope": _scope_payload(proposal.scope),
            "allowed_actor_types": [
                actor_type.value for actor_type in proposal.allowed_actor_types
            ],
            "risk_level": proposal.risk_level,
            "provenance_ref": proposal.provenance_ref,
            "created_at": proposal.created_at.isoformat(),
            "expires_at": proposal.expires_at.isoformat(),
        },
        "proposal_payload",
    )


def _decision_payload(decision: HumanDecision) -> dict[str, Any]:
    return _json_object(
        {
            "decision_id": decision.decision_id,
            "task_id": decision.task_id,
            "actor_id": decision.actor_id,
            "actor_type": decision.actor_type.value,
            "outcome": decision.outcome.value,
            "reason": decision.reason,
            "decided_at": decision.decided_at.isoformat(),
        },
        "decision_payload",
    )


def _request_payload(request: NamedActionRequest) -> dict[str, Any]:
    return _json_object(
        {
            "request_id": request.request_id,
            "action_name": request.action_name,
            "action_arguments": request.action_arguments,
            "task_id": request.task_id,
            "proposal_id": request.proposal_id,
            "decision_id": request.decision_id,
            "actor_id": request.actor_id,
            "actor_type": request.actor_type.value,
            "scope": _scope_payload(request.scope),
            "provenance_ref": request.provenance_ref,
            "idempotency_key": request.idempotency_key,
        },
        "action_request_payload",
    )


def _datetime_from_payload(payload: Mapping[str, object], name: str) -> datetime:
    raw = payload.get(name)
    if not isinstance(raw, str):
        raise HumanGateError("PERSISTED_SHAPE_INVALID", f"{name} is missing")
    try:
        value = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise HumanGateError("PERSISTED_SHAPE_INVALID", f"{name} is invalid") from exc
    return _aware(value, name)


def _scope_from_payload(raw: object) -> GateScope:
    if not isinstance(raw, Mapping):
        raise HumanGateError("PERSISTED_SHAPE_INVALID", "scope is missing")
    subjects = raw.get("subject_ids")
    if not isinstance(subjects, (list, tuple)):
        raise HumanGateError("PERSISTED_SHAPE_INVALID", "subject_ids is invalid")
    return GateScope(
        tenant_id=_text(raw.get("tenant_id"), "tenant_id"),
        family_id=(
            raw.get("family_id")
            if raw.get("family_id") is None
            else _text(raw.get("family_id"), "family_id")
        ),
        subject_ids=tuple(_text(item, "subject_id") for item in subjects),
        purpose=_text(raw.get("purpose"), "purpose"),
        consent_version=_text(raw.get("consent_version"), "consent_version"),
        correlation_id=_text(raw.get("correlation_id"), "correlation_id"),
    )


def _proposal_from_payload(raw: object) -> ActionProposal:
    if not isinstance(raw, Mapping):
        raise HumanGateError("PERSISTED_SHAPE_INVALID", "proposal_payload is missing")
    allowed = raw.get("allowed_actor_types")
    arguments = raw.get("action_arguments")
    if not isinstance(allowed, (list, tuple)) or not isinstance(arguments, Mapping):
        raise HumanGateError("PERSISTED_SHAPE_INVALID", "proposal payload shape is invalid")
    return ActionProposal(
        proposal_id=_text(raw.get("proposal_id"), "proposal_id"),
        draft_id=_text(raw.get("draft_id"), "draft_id"),
        draft_status=_text(raw.get("draft_status"), "draft_status"),
        action_name=_text(raw.get("action_name"), "action_name"),
        action_arguments=dict(arguments),
        scope=_scope_from_payload(raw.get("scope")),
        allowed_actor_types=tuple(ActorType(item) for item in allowed),
        risk_level=_text(raw.get("risk_level"), "risk_level"),
        provenance_ref=_text(raw.get("provenance_ref"), "provenance_ref"),
        created_at=_datetime_from_payload(raw, "created_at"),
        expires_at=_datetime_from_payload(raw, "expires_at"),
    )


def _decision_from_payload(raw: object) -> HumanDecision | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise HumanGateError("PERSISTED_SHAPE_INVALID", "decision_payload is invalid")
    return HumanDecision(
        decision_id=_text(raw.get("decision_id"), "decision_id"),
        task_id=_text(raw.get("task_id"), "task_id"),
        actor_id=_text(raw.get("actor_id"), "actor_id"),
        actor_type=ActorType(raw.get("actor_type")),
        outcome=DecisionOutcome(raw.get("outcome")),
        reason=(
            raw.get("reason")
            if raw.get("reason") is None
            else _text(raw.get("reason"), "reason")
        ),
        decided_at=_datetime_from_payload(raw, "decided_at"),
    )


def _request_from_payload(raw: object) -> NamedActionRequest | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise HumanGateError("PERSISTED_SHAPE_INVALID", "action_request_payload is invalid")
    arguments = raw.get("action_arguments")
    if not isinstance(arguments, Mapping):
        raise HumanGateError("PERSISTED_SHAPE_INVALID", "action arguments are invalid")
    return NamedActionRequest(
        request_id=_text(raw.get("request_id"), "request_id"),
        action_name=_text(raw.get("action_name"), "action_name"),
        action_arguments=dict(arguments),
        task_id=_text(raw.get("task_id"), "task_id"),
        proposal_id=_text(raw.get("proposal_id"), "proposal_id"),
        decision_id=_text(raw.get("decision_id"), "decision_id"),
        actor_id=_text(raw.get("actor_id"), "actor_id"),
        actor_type=ActorType(raw.get("actor_type")),
        scope=_scope_from_payload(raw.get("scope")),
        provenance_ref=_text(raw.get("provenance_ref"), "provenance_ref"),
        idempotency_key=_text(raw.get("idempotency_key"), "idempotency_key"),
    )


def _persisted_task(row: HumanTaskRow) -> HumanTask:
    """Rehydrate and revalidate every immutable component of a row."""

    try:
        proposal = _proposal_from_payload(row.proposal_payload)
        decision = _decision_from_payload(row.decision_payload)
        request = _request_from_payload(row.action_request_payload)
        status = GateStatus(row.status)
        if (
            row.tenant_id != proposal.scope.tenant_id
            or row.family_id != proposal.scope.family_id
            or tuple(row.subject_ids) != proposal.scope.subject_ids
            or row.purpose != proposal.scope.purpose
            or row.consent_version != proposal.scope.consent_version
            or row.correlation_id != proposal.scope.correlation_id
            or row.proposal_id != proposal.proposal_id
            or row.draft_id != proposal.draft_id
            or row.action_name != proposal.action_name
            or row.risk_level != proposal.risk_level
            or row.provenance_ref != proposal.provenance_ref
            or _utc(row.created_at) != proposal.created_at
            or _utc(row.expires_at) != proposal.expires_at
        ):
            raise HumanGateError("PERSISTED_SHAPE_INVALID", "proposal scalar snapshot mismatch")
        if row.decision_id != (decision.decision_id if decision else None):
            raise HumanGateError("PERSISTED_SHAPE_INVALID", "decision id mismatch")
        if row.request_id != (request.request_id if request else None):
            raise HumanGateError("PERSISTED_SHAPE_INVALID", "request id mismatch")
        if _utc(row.decided_at) != (decision.decided_at if decision else None):
            raise HumanGateError("PERSISTED_SHAPE_INVALID", "decision timestamp mismatch")
        if decision is not None and decision.task_id != row.task_id:
            raise HumanGateError("PERSISTED_SHAPE_INVALID", "decision task mismatch")
        if decision is not None and decision.outcome is DecisionOutcome.ACCEPT and request is None:
            raise HumanGateError(
                "PERSISTED_SHAPE_INVALID", "an accepted decision must have an action request"
            )
        if (
            decision is not None
            and decision.outcome is not DecisionOutcome.ACCEPT
            and request is not None
        ):
            raise HumanGateError(
                "PERSISTED_SHAPE_INVALID", "only an accepted decision may have an action request"
            )
        if request is not None and (
            request.task_id != row.task_id
            or request.proposal_id != proposal.proposal_id
            or request.action_name != proposal.action_name
            or request.scope != proposal.scope
            or request.provenance_ref != proposal.provenance_ref
            or decision is None
            or request.decision_id != decision.decision_id
        ):
            raise HumanGateError("PERSISTED_SHAPE_INVALID", "action request snapshot mismatch")
        return HumanTask(
            task_id=row.task_id,
            proposal=proposal,
            status=status,
            decision=decision,
            action_request=request,
            created_at=_utc(row.created_at) or proposal.created_at,
        )
    except HumanGateError as exc:
        if exc.code == "PERSISTED_SHAPE_INVALID":
            raise
        raise HumanGateError(
            "PERSISTED_SHAPE_INVALID", "persisted HumanTask violates its contract"
        ) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise HumanGateError(
            "PERSISTED_SHAPE_INVALID", "persisted HumanTask shape is invalid"
        ) from exc


def _same_decision(
    previous: HumanDecision | None,
    *,
    decision_id: str,
    actor_id: str,
    actor_type: ActorType,
    outcome: DecisionOutcome,
    reason: str | None,
) -> bool:
    return (
        previous is not None
        and previous.decision_id == decision_id
        and previous.actor_id == actor_id
        and previous.actor_type is actor_type
        and previous.outcome is outcome
        and (previous.reason or "").strip() == (reason or "").strip()
    )


class SqlAlchemyHumanGate:
    """Durable Human Gate adapter; the caller owns the transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, task_id: str) -> HumanTask:
        row = await self._session.get(HumanTaskRow, task_id)
        if row is None:
            raise HumanGateError("TASK_NOT_FOUND", f"unknown human task {task_id!r}")
        return _persisted_task(row)

    async def submit(
        self,
        proposal: ActionProposal,
        *,
        recorder: AuditRecorder,
        task_id: str | None = None,
    ) -> HumanTask:
        if not isinstance(proposal, ActionProposal):
            raise HumanGateError("INVALID_CONTRACT", "proposal is invalid")
        existing = await self._session.scalar(
            sa.select(HumanTaskRow).where(
                HumanTaskRow.tenant_id == proposal.scope.tenant_id,
                HumanTaskRow.proposal_id == proposal.proposal_id,
            )
        )
        if existing is not None:
            current = _persisted_task(existing)
            if current.proposal != proposal:
                raise HumanGateError(
                    "PROPOSAL_REPLAY_MISMATCH", "proposal id was reused with new content"
                )
            return current

        # The tenant is part of the generated id.  Proposal ids are only
        # unique within a tenant, so omitting it would make two legitimate
        # tenants collide whenever they both use ``proposal-1``.
        resolved_task_id = task_id or (
            f"human-task:{proposal.scope.tenant_id}:{proposal.proposal_id}"
        )
        by_id = await self._session.get(HumanTaskRow, resolved_task_id)
        if by_id is not None:
            raise HumanGateError("TASK_ID_COLLISION", "task_id is already registered")
        payload = _proposal_payload(proposal)
        row = HumanTaskRow(
            task_id=resolved_task_id,
            tenant_id=proposal.scope.tenant_id,
            family_id=proposal.scope.family_id,
            subject_ids=list(proposal.scope.subject_ids),
            purpose=proposal.scope.purpose,
            consent_version=proposal.scope.consent_version,
            correlation_id=proposal.scope.correlation_id,
            proposal_id=proposal.proposal_id,
            draft_id=proposal.draft_id,
            action_name=proposal.action_name,
            risk_level=proposal.risk_level,
            provenance_ref=proposal.provenance_ref,
            proposal_payload=payload,
            status=GateStatus.OPEN.value,
            created_at=proposal.created_at,
            expires_at=proposal.expires_at,
            decision_id=None,
            decided_at=None,
            decision_payload=None,
            request_id=None,
            action_request_payload=None,
        )
        self._session.add(row)
        await self._session.flush()
        recorder.record(
            AuditEvent(
                actor_id="system:human-gate",
                tenant_id=proposal.scope.tenant_id,
                action="CREATE_HUMAN_TASK",
                resource_type="HumanTask",
                resource_id=resolved_task_id,
                reason="AI draft entered the Human Gate for human review",
                correlation_id=proposal.scope.correlation_id,
                after={
                    "status": GateStatus.OPEN.value,
                    "proposal_id": proposal.proposal_id,
                    "provenance_ref": proposal.provenance_ref,
                },
            )
        )
        return _persisted_task(row)

    async def decide(
        self,
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
        # A plain read followed by an ORM update permits two workers to decide
        # the same OPEN task concurrently.  PostgreSQL honours this row lock;
        # SQLite ignores it but remains a useful fast test backend.
        row = await self._session.scalar(
            sa.select(HumanTaskRow)
            .where(HumanTaskRow.task_id == task_id)
            .with_for_update()
        )
        if row is None:
            raise HumanGateError("TASK_NOT_FOUND", f"unknown human task {task_id!r}")
        task = _persisted_task(row)
        resolved_decision_id = decision_id or f"decision:{task_id}"
        if task.status is GateStatus.EXPIRED:
            raise HumanGateError("TASK_EXPIRED", "the human task is past its review deadline")
        try:
            resolved_actor_type = ActorType(actor_type)
            resolved_outcome = DecisionOutcome(outcome)
        except ValueError as exc:
            raise HumanGateError(
                "INVALID_DECISION", "unknown actor type or decision outcome"
            ) from exc
        actor_id = _text(actor_id, "actor_id")
        if actor_id.lower().startswith("ai:") or actor_id.upper() in {"AI", "SYSTEM"}:
            raise HumanGateError("HUMAN_REVIEWER_REQUIRED", "AI and system actors cannot decide")

        if task.status is GateStatus.DECIDED:
            if _same_decision(
                task.decision,
                decision_id=resolved_decision_id,
                actor_id=actor_id,
                actor_type=resolved_actor_type,
                outcome=resolved_outcome,
                reason=reason,
            ):
                return task, task.action_request
            raise HumanGateError("TASK_ALREADY_DECIDED", "a human task can be decided only once")

        current = _aware(now or datetime.now(UTC), "now")
        if current >= task.proposal.expires_at:
            row.status = GateStatus.EXPIRED.value
            await self._session.flush()
            recorder.record(
                AuditEvent(
                    actor_id="system:human-gate-expirer",
                    tenant_id=task.proposal.scope.tenant_id,
                    action="EXPIRE_HUMAN_TASK",
                    resource_type="HumanTask",
                    resource_id=task_id,
                    reason="Human Gate review deadline passed before a decision",
                    correlation_id=task.proposal.scope.correlation_id,
                    before={"status": GateStatus.OPEN.value},
                    after={"status": GateStatus.EXPIRED.value},
                )
            )
            raise HumanGateError("TASK_EXPIRED", "the human task is past its review deadline")

        if resolved_actor_type not in HUMAN_ACTOR_TYPES:
            raise HumanGateError("HUMAN_REVIEWER_REQUIRED", "AI and system actors cannot decide")
        if resolved_actor_type not in task.proposal.allowed_actor_types:
            raise HumanGateError("REVIEWER_NOT_ALLOWED", "actor is not allowed for this proposal")

        decision = HumanDecision(
            decision_id=resolved_decision_id,
            task_id=task_id,
            actor_id=actor_id,
            actor_type=resolved_actor_type,
            outcome=resolved_outcome,
            reason=reason,
            decided_at=current,
        )
        action_request = None
        if resolved_outcome is DecisionOutcome.ACCEPT:
            action_request = NamedActionRequest(
                request_id=f"named-action-request:{task_id}",
                action_name=task.proposal.action_name,
                action_arguments=task.proposal.action_arguments,
                task_id=task_id,
                proposal_id=task.proposal.proposal_id,
                decision_id=decision.decision_id,
                actor_id=actor_id,
                actor_type=resolved_actor_type,
                scope=task.proposal.scope,
                provenance_ref=task.proposal.provenance_ref,
                idempotency_key=(
                    f"{task.proposal.scope.tenant_id}:"
                    f"{task.proposal.action_name}:{task.proposal.proposal_id}"
                ),
            )
        row.status = GateStatus.DECIDED.value
        row.decision_id = decision.decision_id
        row.decided_at = decision.decided_at
        row.decision_payload = _decision_payload(decision)
        row.request_id = action_request.request_id if action_request is not None else None
        row.action_request_payload = (
            _request_payload(action_request) if action_request is not None else None
        )
        await self._session.flush()
        recorder.record(
            AuditEvent(
                actor_id=actor_id,
                tenant_id=task.proposal.scope.tenant_id,
                action="DECIDE_HUMAN_TASK",
                resource_type="HumanTask",
                resource_id=task_id,
                reason=reason or f"human decision: {resolved_outcome.value}",
                correlation_id=task.proposal.scope.correlation_id,
                before={"status": GateStatus.OPEN.value},
                after={
                    "status": GateStatus.DECIDED.value,
                    "outcome": resolved_outcome.value,
                    "decision_id": decision.decision_id,
                    "request_id": action_request.request_id if action_request else None,
                },
            )
        )
        decided = _persisted_task(row)
        return decided, decided.action_request

    async def expire_due(
        self,
        *,
        recorder: AuditRecorder,
        now: datetime | None = None,
    ) -> int:
        """Mark all currently-open expired tasks and return the count.

        This is a worker-friendly, idempotent sweep.  It only changes OPEN
        rows; a second sweep creates no duplicate audit event.
        """

        current = _aware(now or datetime.now(UTC), "now")
        rows = (
            await self._session.scalars(
                sa.select(HumanTaskRow)
                .where(HumanTaskRow.status == GateStatus.OPEN.value)
                .with_for_update()
            )
        ).all()
        expired = 0
        for row in rows:
            expires_at = _utc(row.expires_at)
            if expires_at is None or expires_at > current:
                continue
            task = _persisted_task(row)
            row.status = GateStatus.EXPIRED.value
            expired += 1
            recorder.record(
                AuditEvent(
                    actor_id="system:human-gate-expirer",
                    tenant_id=task.proposal.scope.tenant_id,
                    action="EXPIRE_HUMAN_TASK",
                    resource_type="HumanTask",
                    resource_id=row.task_id,
                    reason="Human Gate review deadline passed during expiry sweep",
                    correlation_id=task.proposal.scope.correlation_id,
                    before={"status": GateStatus.OPEN.value},
                    after={"status": GateStatus.EXPIRED.value},
                )
            )
        if expired:
            await self._session.flush()
        return expired

    async def flush_audit(self, recorder: AuditRecorder) -> int:
        return await recorder.flush(self._session)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()


__all__ = [
    "HUMAN_TASKS_TABLE",
    "HumanGateBase",
    "HumanTaskRow",
    "SqlAlchemyHumanGate",
]
