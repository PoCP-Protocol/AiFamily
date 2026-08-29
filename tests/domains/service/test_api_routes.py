"""HTTP acceptance tests for the SERVICE endpoints.

Runs the whole chain over HTTP with the four fail-closed dependencies supplied
through `app.dependency_overrides` — the intended mechanism (see
`api/dependencies.py`), not a workaround.

**Why these tests build their own `FastAPI()` instead of calling
`backend.apps.family_api.main.create_app()`**, which is what
`tests/apps/family_api/test_assessment_routes.py` does: the service router is
mounted in `create_app` (and `test_service_router_is_mounted_in_the_app` below
asserts that), but importing that module also pulls in every *other* mounted
router. At the time of writing the assessment domain is mid-refactor from
`api.py` to an `api/` package by a concurrent session and
`backend.domains.assessment.api` exports no `install_state`, so
`create_app()` raises `ImportError` and takes `tests/apps/family_api/*` down with
it. That breakage predates and is independent of this domain (verified by
stashing this task's `main.py` edit and re-running — the same three errors
appear).

Coupling this domain's HTTP coverage to that import would mean SERVICE has no
route-level tests whenever a neighbouring domain is halfway through a rename.
The router is the unit under test here, so it is mounted directly. The one thing
a local app cannot prove — that the router is actually reachable in the real
process — is covered by `test_service_router_is_mounted_in_the_app`, which is
skipped rather than failed while the app import is broken, and states so.

Three properties are only provable at this layer, and each has a test:

1. **Scope never comes from the URL.** A valid token for family A requesting
   family B's URL is 403, and a foreign `family_id` in a request body has no
   effect because no request model has that field to begin with.
2. **Every mutation requires an idempotency-key header.** Missing → 400.
3. **The Human Gate is the engine's, not the route's.** An AI `ActorContext` is
   denied on confirm/fulfil/cancel by `PolicyEngine`'s `human_only` veto, before
   any command runs.

SQLite is used via the same repository class the domain tests use, so these
tests exercise the real ORM mapping rather than a fake.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import timedelta

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.domains.service.api import dependencies as deps
from backend.domains.service.api.routes import router as service_router
from backend.domains.service.application.context import ActionContext
from backend.domains.service.domain.entities import utcnow
from backend.domains.service.infrastructure.fake_repository import FakeConsentQuery
from backend.domains.service.infrastructure.sqlalchemy_models import Base
from backend.domains.service.infrastructure.sqlalchemy_repository import (
    SqlAlchemyServiceRepository,
)
from backend.platform.audit.recorder import AuditRecorder
from backend.platform.identity.context import ActorContext, ActorType

from .helpers import CHILD, CONSENT_REF, FAMILY, GUARDIAN, TENANT, granted

CORRELATION = "corr-http-001"


class _Wiring:
    """Holds the objects the overrides hand out, so a test can inspect them."""

    def __init__(self, repo, consent: FakeConsentQuery, recorder: AuditRecorder) -> None:
        self.repo = repo
        self.consent = consent
        self.recorder = recorder
        self.idempotency_key: str | None = None
        self.actor_type = ActorType.HUMAN

    def ctx(self) -> ActionContext:
        return ActionContext(
            tenant_id=TENANT,
            family_id=FAMILY,
            actor_person_id=GUARDIAN,
            actor="guardian:001",
            correlation_id=CORRELATION,
            environment="TEST",
            idempotency_key=self.idempotency_key,
        )

    def actor(self) -> ActorContext:
        return ActorContext(
            actor_id="guardian:001" if self.actor_type is ActorType.HUMAN else "ai:planner",
            actor_type=self.actor_type,
            tenant_id=TENANT,
            correlation_id=CORRELATION,
        )


@pytest_asyncio.fixture
async def wiring() -> AsyncIterator[_Wiring]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield _Wiring(SqlAlchemyServiceRepository(session), FakeConsentQuery(), AuditRecorder())
    await engine.dispose()


def build_service_app() -> FastAPI:
    """The service router on a bare app. See the module docstring for why."""
    app = FastAPI()
    app.include_router(service_router)
    return app


@pytest.fixture
def client(wiring: _Wiring) -> Iterator[TestClient]:
    app = build_service_app()

    async def _repo():
        return wiring.repo

    async def _consent():
        return wiring.consent

    async def _ctx():
        return wiring.ctx()

    async def _actor():
        return wiring.actor()

    app.dependency_overrides[deps.get_repository] = _repo
    app.dependency_overrides[deps.get_consent_query] = _consent
    app.dependency_overrides[deps.get_action_context] = _ctx
    app.dependency_overrides[deps.get_actor_context] = _actor
    app.dependency_overrides[deps.get_audit_recorder] = lambda: wiring.recorder
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _key(wiring: _Wiring, value: str) -> dict[str, str]:
    """Set the context's idempotency key and return the matching header.

    Both together because the route validates the key on the context (see
    `_require_idempotency_key`) — a test that set only the header would prove
    nothing about the path the commands actually take.
    """
    wiring.idempotency_key = value
    return {"idempotency-key": value}


def _seed_supply_http(client: TestClient, wiring: _Wiring) -> tuple[str, str]:
    provider = client.post(
        f"/families/{FAMILY}/service/providers",
        json={
            "provider_ref": "TEACHER_LI",
            "display_name": "李老师",
            "provider_kind": "TEACHER",
            "qualification_status": "ACTIVE",
            "admission_status": "ADMITTED",
            "source_ref": "supply:http",
        },
        headers=_key(wiring, "prov-1"),
    )
    assert provider.status_code == 200, provider.text
    provider_id = provider.json()["provider_id"]

    offering = client.post(
        f"/families/{FAMILY}/service/offerings",
        json={
            "provider_id": provider_id,
            "service_offering_ref": "PARENT_COACHING_60",
            "title": "家长一对一辅导 60 分钟",
            "admission_status": "ADMITTED",
            "source_ref": "supply:http",
        },
        headers=_key(wiring, "offer-1"),
    )
    assert offering.status_code == 200, offering.text
    offering_id = offering.json()["service_offering_id"]

    starts = utcnow() + timedelta(days=3)
    slot = client.post(
        f"/families/{FAMILY}/service/availability-slots",
        json={
            "service_offering_id": offering_id,
            "availability_slot_ref": "SLOT-HTTP-1",
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=1)).isoformat(),
            "channel": "VIDEO",
            "capacity": 1,
        },
        headers=_key(wiring, "slot-1"),
    )
    assert slot.status_code == 200, slot.text
    return offering_id, slot.json()["availability_slot_id"]


def _submit(client: TestClient, wiring: _Wiring, offering_id: str, slot_id: str, key: str):
    return client.post(
        f"/families/{FAMILY}/orchestration/test-loop/services/booking-requests",
        json={
            "service_offering_id": offering_id,
            "availability_slot_id": slot_id,
            "booking_ref": f"BOOK-{key}",
            "source_page_id": "UI-21",
            "subject_person_id": CHILD,
            "consent_ref": CONSENT_REF,
        },
        headers=_key(wiring, key),
    )


def test_http_chain_browse_book_confirm_fulfil(client: TestClient, wiring: _Wiring) -> None:
    wiring.consent.add(granted())
    offering_id, slot_id = _seed_supply_http(client, wiring)

    offerings = client.get(f"/families/{FAMILY}/orchestration/test-loop/services/offerings")
    assert offerings.status_code == 200
    assert [o["service_offering_ref"] for o in offerings.json()] == ["PARENT_COACHING_60"]
    assert offerings.json()[0]["open_slot_count"] == 1

    slots = client.get(f"/families/{FAMILY}/orchestration/test-loop/services/slots")
    assert slots.status_code == 200
    assert slots.json()[0]["remaining_capacity"] == 1

    booking = _submit(client, wiring, offering_id, slot_id, "book-1")
    assert booking.status_code == 200, booking.text
    booking_id = booking.json()["booking_request_id"]
    assert booking.json()["status"] == "REQUESTED"

    confirm = client.post(
        f"/families/{FAMILY}/service/booking-requests/{booking_id}/confirm",
        headers=_key(wiring, "confirm-1"),
    )
    assert confirm.status_code == 200, confirm.text
    record_id = confirm.json()["service_record"]["booking_service_record_id"]

    fulfil = client.post(
        f"/families/{FAMILY}/service/service-records/{record_id}/fulfil",
        json={"quality_rating": "POSITIVE"},
        headers=_key(wiring, "fulfil-1"),
    )
    assert fulfil.status_code == 200, fulfil.text
    assert fulfil.json()["status"] == "COMPLETED"

    projection = client.get(
        f"/families/{FAMILY}/orchestration/test-loop/services/customer-projection"
    )
    assert projection.status_code == 200
    row = projection.json()["bookings"][0]
    assert row["booking_status"] == "CONFIRMED"
    assert row["service_record_status"] == "COMPLETED"
    # The projection is honest that this is fixture supply, not a real appointment.
    assert row["external_effect"] is False
    assert row["source_system"] == "TEST_FIXTURE"


def test_service_journey_and_private_checkin_draft(client: TestClient, wiring: _Wiring) -> None:
    draft = client.post(
        f"/families/{FAMILY}/growth/onboardings/onb-1/service-journey/checkin-drafts",
        json={"action_ref": "WEEKLY_ACTION_SEE"},
        headers=_key(wiring, "checkin-1"),
    )
    assert draft.status_code == 200, draft.text

    journey = client.get(f"/families/{FAMILY}/growth/onboardings/onb-1/service-journey")
    assert journey.status_code == 200
    assert [d["action_ref"] for d in journey.json()["checkin_drafts"]] == ["WEEKLY_ACTION_SEE"]

    # Allow-list refusal surfaces as the source contract's 400-class code, not a
    # pydantic error, because the domain policy runs before entity construction.
    rejected = client.post(
        f"/families/{FAMILY}/growth/onboardings/onb-1/service-journey/checkin-drafts",
        json={"action_ref": "FREE_TEXT_NOTE"},
        headers=_key(wiring, "checkin-2"),
    )
    assert rejected.status_code == 400
    assert rejected.json()["detail"] == "unsupported_private_checkin_action_ref:FREE_TEXT_NOTE"


def test_booking_without_consent_is_403(client: TestClient, wiring: _Wiring) -> None:
    """ConsentGate over HTTP. The `consent` source is empty by default."""
    offering_id, slot_id = _seed_supply_http(client, wiring)
    response = _submit(client, wiring, offering_id, slot_id, "book-noconsent")
    assert response.status_code == 403
    assert response.json()["detail"].startswith("consent_required:service:")


def test_cross_family_url_is_403(client: TestClient, wiring: _Wiring) -> None:
    """The `{family_id}` path segment is an assertion the server checks, never a
    selector it obeys."""
    for path in (
        "/families/family-999/orchestration/test-loop/services/offerings",
        "/families/family-999/orchestration/test-loop/services/customer-projection",
        "/families/family-999/growth/onboardings/onb-1/service-journey",
    ):
        assert client.get(path).status_code == 403, path

    response = client.post(
        "/families/family-999/orchestration/test-loop/services/booking-requests",
        json={
            "service_offering_id": "x",
            "availability_slot_id": "y",
            "booking_ref": "BOOK-X",
            "source_page_id": "UI-21",
            "subject_person_id": CHILD,
            "consent_ref": CONSENT_REF,
        },
        headers=_key(wiring, "book-foreign"),
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "family_scope_violation"


def test_mutation_without_idempotency_key_is_400(client: TestClient, wiring: _Wiring) -> None:
    wiring.idempotency_key = None
    response = client.post(
        f"/families/{FAMILY}/orchestration/test-loop/services/booking-requests",
        json={
            "service_offering_id": "x",
            "availability_slot_id": "y",
            "booking_ref": "BOOK-X",
            "source_page_id": "UI-21",
            "subject_person_id": CHILD,
            "consent_ref": CONSENT_REF,
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "idempotency-key header is required"


def test_replayed_key_over_http_returns_the_same_booking(
    client: TestClient, wiring: _Wiring
) -> None:
    wiring.consent.add(granted())
    offering_id, slot_id = _seed_supply_http(client, wiring)
    first = _submit(client, wiring, offering_id, slot_id, "book-replay")
    second = _submit(client, wiring, offering_id, slot_id, "book-replay")
    assert first.status_code == second.status_code == 200
    assert first.json()["booking_request_id"] == second.json()["booking_request_id"]


def test_occupied_slot_over_http_is_409(client: TestClient, wiring: _Wiring) -> None:
    wiring.consent.add(granted())
    offering_id, slot_id = _seed_supply_http(client, wiring)
    assert _submit(client, wiring, offering_id, slot_id, "book-a").status_code == 200
    conflict = _submit(client, wiring, offering_id, slot_id, "book-b")
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "slot_not_available:RESERVED"


def test_ai_actor_is_denied_on_human_gated_actions(client: TestClient, wiring: _Wiring) -> None:
    """R8 — the veto is `PolicyEngine`'s, and it fires before any command runs."""
    wiring.consent.add(granted())
    offering_id, slot_id = _seed_supply_http(client, wiring)
    booking_id = _submit(client, wiring, offering_id, slot_id, "book-1").json()[
        "booking_request_id"
    ]

    wiring.actor_type = ActorType.AI
    confirm = client.post(
        f"/families/{FAMILY}/service/booking-requests/{booking_id}/confirm",
        headers=_key(wiring, "confirm-ai"),
    )
    assert confirm.status_code == 403
    assert "human_only" in confirm.json()["detail"]

    cancel = client.post(
        f"/families/{FAMILY}/service/booking-requests/{booking_id}/cancel",
        headers=_key(wiring, "cancel-ai"),
    )
    assert cancel.status_code == 403

    # The denial is itself audited — a refused attempt is what an operator needs
    # to see later.
    assert any(e.action.endswith(":denied") for e in wiring.recorder.all_events())


#: The SERVICE group of `contracts/openapi/UI_API_ENDPOINT_INVENTORY.md`, verbatim.
#: `{familyId}`/`{onboardingId}` become `{family_id}`/`{onboarding_id}` — FastAPI
#: path parameter names are Python identifiers; the wire shape is identical.
PUBLISHED_SERVICE_ENDPOINTS: set[tuple[str, str]] = {
    ("GET", "/families/{family_id}/orchestration/test-loop/services/offerings"),
    ("GET", "/families/{family_id}/orchestration/test-loop/services/slots"),
    ("POST", "/families/{family_id}/orchestration/test-loop/services/booking-requests"),
    ("GET", "/families/{family_id}/orchestration/test-loop/services/customer-projection"),
    ("GET", "/families/{family_id}/growth/onboardings/{onboarding_id}/service-journey"),
    (
        "POST",
        "/families/{family_id}/growth/onboardings/{onboarding_id}/service-journey/checkin-drafts",
    ),
}


def _registered(app: FastAPI) -> set[tuple[str, str]]:
    """(method, path) pairs from the OpenAPI schema.

    Read from `app.openapi()` rather than walking `app.routes`: this FastAPI
    version wraps an included router in an `_IncludedRouter` object with no
    `.path`, so a naive walk silently finds only the four docs routes and the
    assertion passes for the wrong reason. The schema is also the artefact the
    client contract is actually written against, which makes it the right thing
    to assert on regardless.
    """
    schema = app.openapi()
    return {
        (method.upper(), path)
        for path, operations in schema.get("paths", {}).items()
        for method in operations
        if method.upper() not in ("HEAD", "OPTIONS")
    }


def test_the_six_published_service_endpoints_are_registered() -> None:
    """Guards against a route being renamed and the client contract silently
    breaking. The mobile client already calls these six URLs."""
    missing = PUBLISHED_SERVICE_ENDPOINTS - _registered(build_service_app())
    assert not missing, f"unregistered SERVICE endpoints: {sorted(missing)}"


def test_service_router_is_mounted_in_the_app() -> None:
    """The one property a locally-built app cannot prove: the six endpoints are
    reachable in the real `family_api` process, not just on a test harness.

    Skips rather than fails while `create_app()` is un-importable — see the
    module docstring. A skip here means "cannot currently be verified", and the
    reason string says which neighbouring breakage is responsible; it does not
    mean the mount is absent.
    """
    try:
        from backend.apps.family_api.main import create_app
    except ImportError as exc:  # pragma: no cover - depends on concurrent work
        pytest.skip(f"backend.apps.family_api.main is not importable: {exc}")

    missing = PUBLISHED_SERVICE_ENDPOINTS - _registered(create_app())
    assert not missing, f"SERVICE endpoints not mounted in family_api: {sorted(missing)}"
