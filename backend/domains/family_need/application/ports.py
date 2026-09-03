"""Ports for the Family Need use cases.

Implementations may be in-memory, PostgreSQL or a regional cell.  This module
contains no FastAPI, ORM, model-provider or order/service implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from ..domain.entities import (
    AssignmentPlan,
    FamilyConfirmedOutcome,
    FamilyNeed,
    NeedProfile,
    NeedSignal,
    SolutionDraft,
)
from ..domain.value_objects import (
    ActorType,
    DataClass,
    EvidenceRef,
    NeedCategory,
    NeedContext,
    NeedSignalSource,
    ResourceGap,
    ResourceGapReason,
    SolutionComponentRef,
    SupplyShape,
)

if TYPE_CHECKING:
    from .service import CaptureSignalResult, SolutionDraftResult


@dataclass(frozen=True)
class NeedSignalInput:
    """N0 input envelope; raw family expression remains immutable evidence."""

    context: NeedContext
    raw_text: str
    source: NeedSignalSource | str
    signal_id: str | None = None
    expires_at: datetime | None = None
    subject_person_ids: tuple[str, ...] = ()
    statement: str | None = None
    desired_outcome: str | None = None
    category: NeedCategory = NeedCategory.EDUCATION
    idempotency_key: str | None = None
    evidence_refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class NeedClarificationInput:
    need_id: str
    context: NeedContext
    statement: str
    desired_outcome: str
    subject_person_ids: tuple[str, ...]
    expected_version: int
    idempotency_key: str | None = None


@dataclass(frozen=True)
class NeedProfileInput:
    need_id: str
    context: NeedContext
    expected_need_version: int
    urgency: str
    complexity: str
    risk_level: str
    preferred_shapes: tuple[SupplyShape, ...]
    required_capability_keys: tuple[str, ...] = ()
    idempotency_key: str | None = None


@dataclass(frozen=True)
class SolutionDraftInput:
    need_id: str
    profile_id: str
    context: NeedContext
    expected_profile_version: int
    shape: SupplyShape
    component_refs: tuple[SolutionComponentRef, ...]
    commercial_intent: bool = False
    idempotency_key: str | None = None


@dataclass(frozen=True)
class NeedEvent:
    event_name: str
    aggregate_id: str
    tenant_id: str
    family_id: str
    version: int
    correlation_id: str | None
    occurred_at: datetime
    purpose: str = "FAMILY_NEED"
    consent_version: str | None = None
    data_class: DataClass | None = None
    subject_person_ids: tuple[str, ...] = ()
    idempotency_key: str | None = None


class FamilyNeedRepositoryPort(Protocol):
    """Facts and state owned by this bounded context only."""

    async def save_signal(self, signal: NeedSignal) -> None: ...

    async def get_signal(
        self, *, tenant_id: str, family_id: str, signal_id: str
    ) -> NeedSignal | None: ...

    async def save_need(self, need: FamilyNeed) -> None: ...

    async def get_need(
        self, *, tenant_id: str, family_id: str, need_id: str
    ) -> FamilyNeed | None: ...

    async def save_profile(self, profile: NeedProfile) -> None: ...

    async def get_profile(
        self, *, tenant_id: str, family_id: str, profile_id: str
    ) -> NeedProfile | None: ...

    async def save_solution_draft(self, draft: SolutionDraft) -> None: ...

    async def get_solution_draft(
        self, *, tenant_id: str, family_id: str, draft_id: str
    ) -> SolutionDraft | None: ...

    async def append_event(self, event: NeedEvent) -> None: ...

    async def save_outcome(self, outcome: FamilyConfirmedOutcome) -> None: ...

    async def get_outcomes_for_need(
        self, *, tenant_id: str, family_id: str, need_id: str
    ) -> tuple[FamilyConfirmedOutcome, ...]: ...

    async def save_assignment_plan(self, plan: AssignmentPlan) -> None: ...

    async def get_assignment_plan(
        self, *, tenant_id: str, family_id: str, plan_id: str
    ) -> AssignmentPlan | None: ...


class FamilyNeedPolicyPort(Protocol):
    """Authorization/consent is injected; the domain never guesses it."""

    async def assert_tenant_family_scope(self, *, context: NeedContext, actor_id: str) -> None: ...

    async def assert_subject_scope(
        self, *, context: NeedContext, subject_person_ids: tuple[str, ...]
    ) -> None: ...

    async def assert_consent(
        self, *, context: NeedContext, purpose: str, data_class: DataClass
    ) -> None: ...

    async def assert_can_manage(
        self, *, context: NeedContext, actor_id: str, actor_type: ActorType
    ) -> None: ...


class SupplyReferencePort(Protocol):
    """Read-only references into Product/Service/FGCN contexts.

    The port must return a versioned reference or ``None``.  It must not create
    a product, book a service, assign a provider, charge a payment, or mutate a
    FGCN case.  Resource shortage is explicit so that the caller can present a
    warm, honest fallback to the family.
    """

    async def resolve_component(
        self,
        *,
        tenant_id: str,
        region: str,
        locale: str,
        shape: SupplyShape,
        component_id: str,
        version: str,
    ) -> SolutionComponentRef | None: ...

    async def check_resource_capacity(
        self,
        *,
        tenant_id: str,
        family_id: str,
        need_id: str = "",
        component_refs: tuple[SolutionComponentRef, ...],
    ) -> ResourceGap | None: ...

    async def get_resource_gap(
        self, *, need_id: str, reason: ResourceGapReason, detail: str
    ) -> ResourceGap: ...


# More explicit name for callers that only need solution composition.  The
# alias intentionally exposes the same read-only contract and does not create a
# second implementation location (R2).
SolutionReferencePort = SupplyReferencePort
NeedRepositoryPort = FamilyNeedRepositoryPort
NeedPolicyPort = FamilyNeedPolicyPort


class NeedEventPort(Protocol):
    async def publish(self, event: NeedEvent) -> None: ...


class FamilyNeedApplicationPort(Protocol):
    """Use-case facade contract for a future API/worker adapter."""

    async def capture_signal(self, command: NeedSignalInput) -> CaptureSignalResult: ...

    async def clarify_need(self, command: NeedClarificationInput) -> FamilyNeed: ...

    async def profile_need(self, command: NeedProfileInput) -> NeedProfile: ...

    async def draft_solution(self, command: SolutionDraftInput) -> SolutionDraftResult: ...

    async def resource_gap(
        self, *, context: NeedContext, need_id: str, reason: ResourceGapReason, detail: str
    ) -> ResourceGap: ...


__all__ = [
    "FamilyNeedApplicationPort",
    "FamilyNeedPolicyPort",
    "FamilyNeedRepositoryPort",
    "NeedClarificationInput",
    "NeedEvent",
    "NeedEventPort",
    "NeedProfileInput",
    "NeedPolicyPort",
    "NeedRepositoryPort",
    "NeedSignalInput",
    "SolutionDraftInput",
    "SolutionReferencePort",
    "SupplyReferencePort",
]
