"""Human-confirmed service Blueprint proposal fact.

This is the business-domain landing point for the AI intervention action
``PROPOSE_SERVICE_BLUEPRINT``.  It records that a human accepted a specific,
evidence-bound recommendation; it does not open a service case, assign a
provider, book a slot, notify anyone or create an external effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import JSON, DateTime, String, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.human_gate.contracts import NamedActionRequest
from backend.intelligence.tool_runtime.accepted_dispatch import ActionExecutionReceipt
from backend.platform.audit import AuditEvent, AuditRecorder


class BlueprintProposalError(ValueError):
    """Raised when a proposal cannot cross the Human Gate boundary."""


@dataclass(frozen=True, slots=True)
class ServiceBlueprintProposal:
    proposal_id: str
    request_id: str
    tenant_id: str
    family_id: str
    subject_ids: tuple[str, ...]
    blueprint_ref: str
    primary_contradiction_ref: str
    action_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    provenance_ref: str
    correlation_id: str
    accepted_by_actor_id: str
    accepted_at: datetime
    status: str = "ACCEPTED"

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.proposal_id, "proposal_id"),
            (self.request_id, "request_id"),
            (self.tenant_id, "tenant_id"),
            (self.family_id, "family_id"),
            (self.blueprint_ref, "blueprint_ref"),
            (self.primary_contradiction_ref, "primary_contradiction_ref"),
            (self.provenance_ref, "provenance_ref"),
            (self.correlation_id, "correlation_id"),
            (self.accepted_by_actor_id, "accepted_by_actor_id"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise BlueprintProposalError(f"{field_name}_required")
        if self.accepted_by_actor_id.lower().startswith("ai:") or (
            self.accepted_by_actor_id.upper() in {"AI", "SYSTEM"}
        ):
            raise BlueprintProposalError("human_actor_required")
        if not self.subject_ids or any(not item.strip() for item in self.subject_ids):
            raise BlueprintProposalError("subject_ids_required")
        if not self.action_refs or any(not item.strip() for item in self.action_refs):
            raise BlueprintProposalError("action_refs_required")
        if not self.evidence_refs or any(not item.strip() for item in self.evidence_refs):
            raise BlueprintProposalError("evidence_refs_required")
        if self.status != "ACCEPTED":
            raise BlueprintProposalError("proposal_status_invalid")
        if self.accepted_at.tzinfo is None or self.accepted_at.utcoffset() is None:
            raise BlueprintProposalError("accepted_at_must_be_timezone_aware")


class ServiceBlueprintProposalStore(Protocol):
    async def get_by_request_id(self, request_id: str) -> ServiceBlueprintProposal | None: ...

    async def save(self, proposal: ServiceBlueprintProposal) -> ServiceBlueprintProposal: ...

    async def flush_audit(self, recorder: AuditRecorder) -> int: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class BlueprintProposalBase(DeclarativeBase):
    """SQL metadata boundary for the service proposal fact."""


class BlueprintProposalRow(BlueprintProposalBase):
    __tablename__ = "family_service_blueprint_proposals"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "request_id", name="uq_family_service_blueprint_proposal_request"
        ),
    )

    proposal_id: Mapped[str] = mapped_column(String(192), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(160), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    family_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    subject_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    blueprint_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    primary_contradiction_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    action_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    provenance_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(256), nullable=False)
    accepted_by_actor_id: Mapped[str] = mapped_column(String(160), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    stable_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class SqlAlchemyServiceBlueprintProposalStore:
    """Async SQL adapter; callers own the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_request_id(self, request_id: str) -> ServiceBlueprintProposal | None:
        row = await self._session.scalar(
            select(BlueprintProposalRow).where(BlueprintProposalRow.request_id == request_id)
        )
        return None if row is None else _stored(row)

    async def save(self, proposal: ServiceBlueprintProposal) -> ServiceBlueprintProposal:
        existing = await self._session.get(BlueprintProposalRow, proposal.proposal_id)
        if existing is not None:
            if existing.stable_payload != _stable_payload(proposal):
                raise BlueprintProposalError("proposal_replay_mismatch")
            return _stored(existing)
        by_request = await self.get_by_request_id(proposal.request_id)
        if by_request is not None:
            if by_request != proposal:
                raise BlueprintProposalError("proposal_request_replay_mismatch")
            return by_request
        row = BlueprintProposalRow(
            proposal_id=proposal.proposal_id,
            request_id=proposal.request_id,
            tenant_id=proposal.tenant_id,
            family_id=proposal.family_id,
            subject_ids=list(proposal.subject_ids),
            blueprint_ref=proposal.blueprint_ref,
            primary_contradiction_ref=proposal.primary_contradiction_ref,
            action_refs=list(proposal.action_refs),
            evidence_refs=list(proposal.evidence_refs),
            provenance_ref=proposal.provenance_ref,
            correlation_id=proposal.correlation_id,
            accepted_by_actor_id=proposal.accepted_by_actor_id,
            accepted_at=proposal.accepted_at,
            status=proposal.status,
            stable_payload=_stable_payload(proposal),
        )
        self._session.add(row)
        await self._session.flush()
        return proposal

    async def flush_audit(self, recorder: AuditRecorder) -> int:
        return await recorder.flush(self._session)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()


class FGCNBlueprintProposalHandler:
    """Accepted-action handler that records a proposal without opening delivery."""

    def __init__(self, store: ServiceBlueprintProposalStore, *, recorder: AuditRecorder) -> None:
        self._store = store
        self._recorder = recorder

    async def __call__(self, request: NamedActionRequest) -> ActionExecutionReceipt:
        if request.action_name != "PROPOSE_SERVICE_BLUEPRINT":
            raise BlueprintProposalError("action_not_supported")
        family_id = request.scope.family_id
        if not family_id:
            raise BlueprintProposalError("family_scope_required")
        args = request.action_arguments
        blueprint_ref = _argument(args, "blueprint_ref")
        contradiction_ref = _argument(args, "primary_contradiction_ref")
        recommendation_status = _argument(args, "recommendation_status")
        if recommendation_status != "DRAFT":
            raise BlueprintProposalError("draft_recommendation_required")
        action_refs = _arguments(args, "action_refs")
        evidence_refs = _arguments(args, "evidence_refs")
        proposal_id = f"service-blueprint-proposal:{request.request_id}"
        existing = await self._store.get_by_request_id(request.request_id)
        if existing is not None:
            if existing.proposal_id != proposal_id:
                raise BlueprintProposalError("proposal_request_replay_mismatch")
            return _receipt(request, existing.proposal_id)
        proposal = ServiceBlueprintProposal(
            proposal_id=proposal_id,
            request_id=request.request_id,
            tenant_id=request.scope.tenant_id,
            family_id=family_id,
            subject_ids=request.scope.subject_ids,
            blueprint_ref=blueprint_ref,
            primary_contradiction_ref=contradiction_ref,
            action_refs=action_refs,
            evidence_refs=evidence_refs,
            provenance_ref=request.provenance_ref,
            correlation_id=request.scope.correlation_id,
            accepted_by_actor_id=request.actor_id,
            accepted_at=datetime.now(UTC),
        )
        await self._store.save(proposal)
        self._recorder.record(
            AuditEvent(
                actor_id=request.actor_id,
                tenant_id=request.scope.tenant_id,
                action="PROPOSE_SERVICE_BLUEPRINT",
                resource_type="ServiceBlueprintProposal",
                resource_id=proposal.proposal_id,
                reason="human-confirmed evidence-bound service blueprint proposal",
                correlation_id=request.scope.correlation_id,
                after={
                    "status": proposal.status,
                    "blueprint_ref": proposal.blueprint_ref,
                    "evidence_refs": proposal.evidence_refs,
                },
            )
        )
        await self._store.flush_audit(self._recorder)
        await self._store.commit()
        return _receipt(request, proposal.proposal_id)


def _argument(arguments: Any, name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise BlueprintProposalError(f"{name}_required")
    return value.strip()


def _arguments(arguments: Any, name: str) -> tuple[str, ...]:
    value = arguments.get(name)
    if not isinstance(value, (list, tuple)):
        raise BlueprintProposalError(f"{name}_required")
    result = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    if not result:
        raise BlueprintProposalError(f"{name}_required")
    return result


def _stable_payload(proposal: ServiceBlueprintProposal) -> dict[str, Any]:
    return {
        "request_id": proposal.request_id,
        "tenant_id": proposal.tenant_id,
        "family_id": proposal.family_id,
        "subject_ids": list(proposal.subject_ids),
        "blueprint_ref": proposal.blueprint_ref,
        "primary_contradiction_ref": proposal.primary_contradiction_ref,
        "action_refs": list(proposal.action_refs),
        "evidence_refs": list(proposal.evidence_refs),
        "provenance_ref": proposal.provenance_ref,
        "correlation_id": proposal.correlation_id,
        "accepted_by_actor_id": proposal.accepted_by_actor_id,
        "status": proposal.status,
    }


def _stored(row: BlueprintProposalRow) -> ServiceBlueprintProposal:
    if row.stable_payload != _stable_payload(
        ServiceBlueprintProposal(
            proposal_id=row.proposal_id,
            request_id=row.request_id,
            tenant_id=row.tenant_id,
            family_id=row.family_id,
            subject_ids=tuple(row.subject_ids or ()),
            blueprint_ref=row.blueprint_ref,
            primary_contradiction_ref=row.primary_contradiction_ref,
            action_refs=tuple(row.action_refs or ()),
            evidence_refs=tuple(row.evidence_refs or ()),
            provenance_ref=row.provenance_ref,
            correlation_id=row.correlation_id,
            accepted_by_actor_id=row.accepted_by_actor_id,
            accepted_at=_aware(row.accepted_at),
            status=row.status,
        )
    ):
        raise BlueprintProposalError("persisted_proposal_shape_invalid")
    return ServiceBlueprintProposal(
        proposal_id=row.proposal_id,
        request_id=row.request_id,
        tenant_id=row.tenant_id,
        family_id=row.family_id,
        subject_ids=tuple(row.subject_ids or ()),
        blueprint_ref=row.blueprint_ref,
        primary_contradiction_ref=row.primary_contradiction_ref,
        action_refs=tuple(row.action_refs or ()),
        evidence_refs=tuple(row.evidence_refs or ()),
        provenance_ref=row.provenance_ref,
        correlation_id=row.correlation_id,
        accepted_by_actor_id=row.accepted_by_actor_id,
        accepted_at=_aware(row.accepted_at),
        status=row.status,
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _receipt(request: NamedActionRequest, result_ref: str) -> ActionExecutionReceipt:
    return ActionExecutionReceipt(
        request_id=request.request_id,
        action_name=request.action_name,
        result_ref=result_ref,
    )


__all__ = [
    "BlueprintProposalBase",
    "BlueprintProposalError",
    "BlueprintProposalRow",
    "FGCNBlueprintProposalHandler",
    "ServiceBlueprintProposal",
    "ServiceBlueprintProposalStore",
    "SqlAlchemyServiceBlueprintProposalStore",
]
