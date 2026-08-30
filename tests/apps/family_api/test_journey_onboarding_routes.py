from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.apps.family_api import growth_onboarding_wiring
from backend.apps.family_api.growth_onboarding_wiring import (
    InMemoryGrowthOnboardingActorResolver,
    build_fake_growth_onboarding_runtime,
    install_growth_onboarding_dev_wiring,
    install_growth_onboarding_production_wiring,
)
from backend.domains.journey.api.growth_onboarding_routes import (
    GrowthOnboardingActorContext,
)
from backend.domains.journey.domain.growth_onboarding import (
    CONFIRMED_INTENT_BOUNDARY,
    ConfirmedGrowthIntent,
    GrowthOnboardingScope,
)

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


def _intent(
    *,
    intent_id: str = "00000000-0000-4000-8000-000000000001",
    tenant_id: str = "00000000-0000-4000-8000-000000000010",
    family_id: str = "00000000-0000-4000-8000-000000000011",
    actor_id: str = "00000000-0000-4000-8000-000000000012",
    status: str = "OPEN",
    confirmed_by: str | None = "00000000-0000-4000-8000-000000000012",
    confirmed_at: datetime | None = NOW,
) -> ConfirmedGrowthIntent:
    return ConfirmedGrowthIntent(
        intent_id=intent_id,
        tenant_id=tenant_id,
        family_id=family_id,
        subject_person_id="00000000-0000-4000-8000-000000000013",
        need_type="COMMUNICATION_SUPPORT",
        goal_text="先完整听完，再确认彼此听到的内容。",
        required_capability_keys=("CAP_PARENT_CHILD_COMMUNICATION",),
        status=status,
        confirmed_by=confirmed_by,
        confirmed_at=confirmed_at,
        boundary=CONFIRMED_INTENT_BOUNDARY,
    )


def _application() -> tuple[TestClient, object, GrowthOnboardingActorContext]:
    intent = _intent()
    runtime = build_fake_growth_onboarding_runtime([intent])
    scope = GrowthOnboardingActorContext(
        tenant_id=intent.tenant_id,
        family_id=intent.family_id,
        actor_id=intent.confirmed_by or "missing-guardian",
    )

    domain_scope = GrowthOnboardingScope(scope.tenant_id, scope.family_id, scope.actor_id)
    current = datetime.now(UTC)
    runtime.policy.allow(domain_scope)
    runtime.consent.grant(
        domain_scope,
        intent.subject_person_id,
        "GROWTH_TRACKING",
        granted_at=current - timedelta(minutes=1),
    )
    actor_resolver = InMemoryGrowthOnboardingActorResolver(
        {"parent-token": scope}
    )
    app = FastAPI()
    install_growth_onboarding_dev_wiring(
        app,
        runtime=runtime,
        actor_resolver=actor_resolver,
    )
    return TestClient(app), runtime, scope


def _headers(key: str, *, token: str = "parent-token") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": key,
        "X-Correlation-Id": f"correlation:{key}",
    }


def test_confirmed_intent_route_uses_application_and_replays_without_duplicates() -> None:
    client, runtime, scope = _application()
    path = f"/families/{scope.family_id}/growth/onboardings"

    first = client.post(
        path,
        headers=_headers("http-start"),
        json={"intent_id": "00000000-0000-4000-8000-000000000001"},
    )
    replay = client.post(
        path,
        headers=_headers("http-start"),
        json={"intent_id": "00000000-0000-4000-8000-000000000001"},
    )

    assert first.status_code == 200, first.text
    assert first.json()["created"] is True
    assert first.json()["event"]["event_name"] == "GrowthOnboardingStarted"
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["event"] == first.json()["event"]
    assert len(runtime.repository.onboardings) == 1
    assert len(runtime.transaction.audit_log) == 1
    assert len(runtime.transaction.outbox_events) == 1


@pytest.mark.parametrize(
    ("status", "confirmed_by", "confirmed_at"),
    [
        ("OPEN", None, NOW),
        ("OPEN", "", NOW),
        ("OPEN", "00000000-0000-4000-8000-000000000012", None),
        ("CANCELLED", "00000000-0000-4000-8000-000000000012", NOW),
    ],
)
def test_unconfirmed_or_dismissed_intent_is_not_startable(
    status: str, confirmed_by: str | None, confirmed_at: datetime | None
) -> None:
    client, runtime, scope = _application()
    intent = _intent(status=status, confirmed_by=confirmed_by, confirmed_at=confirmed_at)
    runtime.reader.add(intent)

    response = client.post(
        f"/families/{scope.family_id}/growth/onboardings",
        headers=_headers(f"not-confirmed-{status}-{confirmed_by}"),
        json={"intent_id": intent.intent_id},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "confirmed_growth_intent_not_found"}
    assert runtime.repository.onboardings == {}
    assert runtime.transaction.audit_log == []
    assert runtime.transaction.outbox_events == []


def test_missing_auth_idempotency_and_cross_family_headers_fail_closed() -> None:
    client, _runtime, scope = _application()
    path = f"/families/{scope.family_id}/growth/onboardings"
    payload = {"intent_id": "00000000-0000-4000-8000-000000000001"}

    missing_auth = client.post(path, json=payload)
    missing_key = client.post(
        path,
        headers={"Authorization": "Bearer parent-token"},
        json=payload,
    )
    cross_family = client.post(
        "/families/00000000-0000-4000-8000-000000000099/growth/onboardings",
        headers=_headers("cross-family"),
        json=payload,
    )

    assert missing_auth.status_code == 401
    assert missing_auth.json() == {"detail": "authorization_required"}
    assert missing_key.status_code == 400
    assert missing_key.json() == {"detail": "invalid_idempotency_key"}
    assert cross_family.status_code == 403
    assert cross_family.json() == {"detail": "family_access_denied"}


def test_cross_tenant_intent_is_not_visible_through_reader_scope() -> None:
    client, runtime, scope = _application()

    tenant_scope = GrowthOnboardingActorContext(
        tenant_id="00000000-0000-4000-8000-000000000099",
        family_id=scope.family_id,
        actor_id=scope.actor_id,
    )
    runtime.policy.allow(
        GrowthOnboardingScope(
            tenant_scope.tenant_id, tenant_scope.family_id, tenant_scope.actor_id
        )
    )
    runtime.consent.grant(
        GrowthOnboardingScope(
            tenant_scope.tenant_id, tenant_scope.family_id, tenant_scope.actor_id
        ),
        _intent().subject_person_id,
        "GROWTH_TRACKING",
    )
    actor_resolver = InMemoryGrowthOnboardingActorResolver({"other-tenant": tenant_scope})
    app = FastAPI()
    install_growth_onboarding_dev_wiring(
        app,
        runtime=runtime,
        actor_resolver=actor_resolver,
    )

    response = TestClient(app).post(
        f"/families/{scope.family_id}/growth/onboardings",
        headers=_headers("cross-tenant", token="other-tenant"),
        json={"intent_id": _intent().intent_id},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "confirmed_growth_intent_not_found"}
    assert runtime.repository.onboardings == {}


@pytest.mark.parametrize("operation", ["withdraw", "expire", "future"])
def test_withdrawn_expired_or_not_yet_effective_consent_is_denied(operation: str) -> None:
    client, runtime, scope = _application()

    domain_scope = GrowthOnboardingScope(scope.tenant_id, scope.family_id, scope.actor_id)
    subject_id = _intent().subject_person_id
    if operation == "withdraw":
        runtime.consent.withdraw(domain_scope, subject_id, "GROWTH_TRACKING")
    elif operation == "expire":
        runtime.consent.expire(domain_scope, subject_id, "GROWTH_TRACKING")
    else:
        runtime.consent.grants.clear()
        runtime.consent.grant(
            domain_scope,
            subject_id,
            "GROWTH_TRACKING",
            granted_at=datetime.now(UTC) + timedelta(minutes=1),
        )

    response = client.post(
        f"/families/{scope.family_id}/growth/onboardings",
        headers=_headers(f"consent-{operation}"),
        json={"intent_id": _intent().intent_id},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "missing_consent:GROWTH_TRACKING"}
    assert runtime.repository.onboardings == {}


def test_ai_actor_is_rejected_at_http_boundary() -> None:
    client, runtime, scope = _application()
    ai_context = GrowthOnboardingActorContext(
        tenant_id=scope.tenant_id,
        family_id=scope.family_id,
        actor_id="ai:principal",
        actor_type="AI",
    )
    actor_resolver = InMemoryGrowthOnboardingActorResolver({"ai-token": ai_context})
    app = FastAPI()
    install_growth_onboarding_dev_wiring(
        app,
        runtime=runtime,
        actor_resolver=actor_resolver,
    )

    response = TestClient(app).post(
        f"/families/{scope.family_id}/growth/onboardings",
        headers=_headers("ai-actor", token="ai-token"),
        json={"intent_id": _intent().intent_id},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "human_actor_required"}
    assert runtime.repository.onboardings == {}


def test_idempotency_conflict_does_not_create_second_onboarding() -> None:
    client, runtime, scope = _application()
    second = _intent(intent_id="00000000-0000-4000-8000-000000000002")
    runtime.reader.add(second)

    runtime.consent.grant(
        GrowthOnboardingScope(scope.tenant_id, scope.family_id, scope.actor_id),
        second.subject_person_id,
        "GROWTH_TRACKING",
    )
    path = f"/families/{scope.family_id}/growth/onboardings"
    first = client.post(
        path,
        headers=_headers("conflicting-key"),
        json={"intent_id": _intent().intent_id},
    )
    conflict = client.post(
        path,
        headers=_headers("conflicting-key"),
        json={"intent_id": second.intent_id},
    )

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json() == {"detail": "idempotency_conflict"}
    assert len(runtime.repository.onboardings) == 1
    assert len(runtime.transaction.audit_log) == 1
    assert len(runtime.transaction.outbox_events) == 1


@pytest.mark.parametrize(
    ("writer", "message"),
    [("audit", "audit_write_failed"), ("outbox", "outbox_write_failed")],
)
def test_audit_and_outbox_failures_roll_back_all_application_writes(
    writer: str, message: str
) -> None:
    client, runtime, scope = _application()

    async def fail(*_args) -> None:
        raise RuntimeError(message)

    if writer == "audit":
        runtime.transaction._audit_writer = fail
    else:
        runtime.transaction._outbox_writer = fail

    client = TestClient(client.app, raise_server_exceptions=False)
    response = client.post(
        f"/families/{scope.family_id}/growth/onboardings",
        headers=_headers(f"rollback-{writer}"),
        json={"intent_id": _intent().intent_id},
    )

    assert response.status_code == 500
    assert runtime.repository.onboardings == {}
    assert runtime.repository.bindings == {}
    assert runtime.transaction.idempotency == {}
    assert runtime.transaction.audit_log == []
    assert runtime.transaction.outbox_events == []


def test_production_wiring_installs_route_and_uses_postgres_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    sentinel_engine = object()
    sentinel_application = object()
    calls: list[str] = []
    monkeypatch.setattr(growth_onboarding_wiring, "get_engine", lambda url: sentinel_engine)

    def build(url: str):
        calls.append(url)
        return sentinel_application

    monkeypatch.setattr(
        growth_onboarding_wiring,
        "build_postgres_growth_onboarding_application",
        build,
    )
    growth_onboarding_wiring.install_growth_onboarding_production_wiring(
        app,
        database_url="postgresql+asyncpg://example/aifamily",
    )

    assert calls == ["postgresql+asyncpg://example/aifamily"]
    assert "/families/{family_id}/growth/onboardings" in app.openapi()["paths"]
    assert growth_onboarding_wiring.get_growth_onboarding_application in app.dependency_overrides
    assert growth_onboarding_wiring.get_growth_onboarding_actor_context in app.dependency_overrides


def test_production_wiring_rejects_non_postgres() -> None:
    with pytest.raises(RuntimeError, match="production_requires_postgresql"):
        install_growth_onboarding_production_wiring(
            FastAPI(), database_url="sqlite+aiosqlite:///:memory:"
        )
