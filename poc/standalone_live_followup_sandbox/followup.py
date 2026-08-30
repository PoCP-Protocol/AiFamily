"""Synthetic H-LIVE-06 family next-step contract.

This sandbox validates a narrow read path: after an accepted live session has
ended, an authenticated adult can see one eligible service next step from the
canonical service catalog.  It does not create a booking, consent, payment,
notification, family fact, ranking, or AI recommendation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

SANDBOX_SOURCE = "SANDBOX_SYNTHETIC"


class FollowupBoundaryError(ValueError):
    """A follow-up fixture violates the explicit sandbox boundary."""


class FollowupRejected(RuntimeError):
    """The requested family next-step read is not allowed."""


class FollowupScopeViolation(FollowupRejected):
    """A follow-up request crossed tenant/family scope."""


class ServiceCatalogUnavailable(FollowupRejected):
    """The canonical service catalog is absent or unavailable."""


class ActorType(StrEnum):
    ADULT = "ADULT"
    CHILD = "CHILD"


class SessionState(StrEnum):
    ENDED = "ENDED"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class FollowupActor:
    tenant_id: str
    family_id: str
    actor_id: str
    actor_type: ActorType

    def __post_init__(self) -> None:
        if not all((self.tenant_id, self.family_id, self.actor_id)):
            raise ValueError("follow-up actor scope fields must not be empty")


@dataclass(frozen=True, slots=True)
class EndedSessionFixture:
    tenant_id: str
    family_id: str
    session_ref: str
    attendance_ref: str
    state: SessionState = SessionState.ENDED
    attendance_accepted: bool = True
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True

    def __post_init__(self) -> None:
        if not self.fixture_only or self.source != SANDBOX_SOURCE:
            raise FollowupBoundaryError("follow-up fixture must be explicitly synthetic")
        if not all((self.tenant_id, self.family_id, self.session_ref, self.attendance_ref)):
            raise ValueError("session and attendance identity must not be empty")


@dataclass(frozen=True, slots=True)
class ServiceNextStep:
    service_ref: str
    title: str
    purpose: str
    tenant_id: str
    family_id: str
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True


class CanonicalServiceCatalogPort(Protocol):
    """AiFamily service catalog boundary; no local booking implementation."""

    def get_family_next_step(
        self,
        *,
        tenant_id: str,
        family_id: str,
        attendance_ref: str,
    ) -> ServiceNextStep | None: ...


class InMemoryServiceCatalogFixture:
    """Synthetic catalog read double; it cannot create bookings."""

    def __init__(self, step: ServiceNextStep | None, *, unavailable: bool = False) -> None:
        self.step = step
        self.unavailable = unavailable
        self.calls: list[dict[str, str]] = []

    def get_family_next_step(self, **kwargs: str) -> ServiceNextStep | None:
        self.calls.append(dict(kwargs))
        if self.unavailable:
            raise RuntimeError("synthetic service catalog unavailable")
        return self.step


@dataclass(frozen=True, slots=True)
class NextStepView:
    kind: str
    session_ref: str
    service_ref: str | None
    title: str | None
    message: str
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True


class LiveFollowupSandbox:
    """Read-only family follow-up over the canonical catalog port."""

    def __init__(self, *, catalog: CanonicalServiceCatalogPort) -> None:
        self.catalog = catalog

    def next_step(self, *, session: EndedSessionFixture, actor: FollowupActor) -> NextStepView:
        if session.tenant_id != actor.tenant_id or session.family_id != actor.family_id:
            raise FollowupScopeViolation("follow-up request crossed tenant/family scope")
        if actor.actor_type is not ActorType.ADULT:
            raise FollowupRejected("family next step is adult-visible only")
        if session.state is not SessionState.ENDED or not session.attendance_accepted:
            return NextStepView(
                kind="EMPTY",
                session_ref=session.session_ref,
                service_ref=None,
                title=None,
                message="当前场次没有可用的家庭下一步",
            )
        try:
            step = self.catalog.get_family_next_step(
                tenant_id=actor.tenant_id,
                family_id=actor.family_id,
                attendance_ref=session.attendance_ref,
            )
        except Exception as exc:  # pragma: no cover - provider boundary
            raise ServiceCatalogUnavailable("service catalog unavailable") from exc
        if step is None:
            return NextStepView(
                kind="EMPTY",
                session_ref=session.session_ref,
                service_ref=None,
                title=None,
                message="当前没有适合本家庭的下一步",
            )
        if step.tenant_id != actor.tenant_id or step.family_id != actor.family_id:
            raise FollowupScopeViolation("service catalog result crossed family scope")
        if not step.fixture_only or step.source != SANDBOX_SOURCE:
            raise FollowupBoundaryError("service next step must remain synthetic")
        return NextStepView(
            kind="SERVICE_NEXT_STEP",
            session_ref=session.session_ref,
            service_ref=step.service_ref,
            title=step.title,
            message=step.purpose,
        )
