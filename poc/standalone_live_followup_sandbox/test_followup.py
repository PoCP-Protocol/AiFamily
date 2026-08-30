"""Executable synthetic tests for the H-LIVE-06 next-step read."""

from __future__ import annotations

import pytest

from poc.standalone_live_followup_sandbox.followup import (
    SANDBOX_SOURCE,
    ActorType,
    EndedSessionFixture,
    FollowupActor,
    FollowupBoundaryError,
    FollowupRejected,
    FollowupScopeViolation,
    InMemoryServiceCatalogFixture,
    LiveFollowupSandbox,
    ServiceCatalogUnavailable,
    ServiceNextStep,
    SessionState,
)

ADULT = FollowupActor("tenant.synthetic", "family.synthetic", "adult.1", ActorType.ADULT)
CHILD = FollowupActor("tenant.synthetic", "family.synthetic", "child.1", ActorType.CHILD)
OTHER = FollowupActor("tenant.synthetic", "family.other", "adult.2", ActorType.ADULT)
SESSION = EndedSessionFixture(
    "tenant.synthetic", "family.synthetic", "live.synthetic.1", "attendance.synthetic.1"
)
STEP = ServiceNextStep(
    "service.synthetic.1",
    "家庭沟通练习",
    "查看适合本家庭的下一步服务",
    "tenant.synthetic",
    "family.synthetic",
)


def test_ended_accepted_session_returns_one_family_scoped_service_step() -> None:
    catalog = InMemoryServiceCatalogFixture(STEP)
    view = LiveFollowupSandbox(catalog=catalog).next_step(session=SESSION, actor=ADULT)
    assert view.kind == "SERVICE_NEXT_STEP"
    assert view.service_ref == "service.synthetic.1"
    assert len(catalog.calls) == 1
    assert catalog.calls[0]["attendance_ref"] == "attendance.synthetic.1"


def test_no_step_is_a_real_empty_state_and_does_not_create_booking() -> None:
    catalog = InMemoryServiceCatalogFixture(None)
    view = LiveFollowupSandbox(catalog=catalog).next_step(session=SESSION, actor=ADULT)
    assert view.kind == "EMPTY"
    assert view.service_ref is None
    assert not hasattr(catalog, "bookings")

    not_accepted = EndedSessionFixture(
        "tenant.synthetic",
        "family.synthetic",
        "live.not-accepted",
        "attendance.not-accepted",
        attendance_accepted=False,
    )
    assert (
        LiveFollowupSandbox(catalog=catalog).next_step(session=not_accepted, actor=ADULT).kind
        == "EMPTY"
    )


def test_withdrawn_or_expired_session_stops_before_catalog_read() -> None:
    catalog = InMemoryServiceCatalogFixture(STEP)
    for state in (SessionState.WITHDRAWN, SessionState.EXPIRED):
        session = EndedSessionFixture(
            "tenant.synthetic",
            "family.synthetic",
            f"live.{state.value.lower()}",
            "attendance.synthetic",
            state=state,
        )
        view = LiveFollowupSandbox(catalog=catalog).next_step(session=session, actor=ADULT)
        assert view.kind == "EMPTY"
    assert catalog.calls == []


def test_child_cross_family_and_missing_catalog_fail_closed() -> None:
    sandbox = LiveFollowupSandbox(catalog=InMemoryServiceCatalogFixture(STEP))
    with pytest.raises(FollowupRejected):
        sandbox.next_step(session=SESSION, actor=CHILD)
    with pytest.raises(FollowupScopeViolation):
        sandbox.next_step(session=SESSION, actor=OTHER)
    unavailable = LiveFollowupSandbox(catalog=InMemoryServiceCatalogFixture(STEP, unavailable=True))
    with pytest.raises(ServiceCatalogUnavailable):
        unavailable.next_step(session=SESSION, actor=ADULT)


def test_catalog_scope_and_fixture_boundary_are_enforced() -> None:
    wrong_scope = ServiceNextStep(
        "service.other", "越界", "不应展示", "tenant.synthetic", "family.other"
    )
    with pytest.raises(FollowupScopeViolation):
        LiveFollowupSandbox(catalog=InMemoryServiceCatalogFixture(wrong_scope)).next_step(
            session=SESSION, actor=ADULT
        )
    with pytest.raises(FollowupBoundaryError):
        EndedSessionFixture(
            "tenant.synthetic",
            "family.synthetic",
            "real-session",
            "real-attendance",
            source="real",
        )
    assert SESSION.source == SANDBOX_SOURCE
    assert SESSION.fixture_only is True
