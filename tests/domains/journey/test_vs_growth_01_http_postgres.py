from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.domains.journey.api.s01_routes import (
    S01ActorContext,
    S01HttpDependencies,
    build_vs_growth_01_router,
)
from backend.domains.journey.application.s01_vertical_slice import (
    AssessmentSignal,
    AuditEventName,
)
from backend.domains.journey.domain.errors import JourneyConflictError
from backend.domains.journey.infrastructure.s01_postgres import (
    S01PostgresAssessmentRepository,
)
from backend.platform.consent import (
    ConsentGrant,
    ConsentPurpose,
    ConsentStatus,
    GuardianRelation,
    SubjectAge,
)

NOW = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
TENANT = "123e4567-e89b-12d3-a456-426614174001"
FAMILY = "123e4567-e89b-12d3-a456-426614174002"
CHILD = "123e4567-e89b-12d3-a456-426614174003"
SESSION = "123e4567-e89b-12d3-a456-426614174004"


def _signal() -> AssessmentSignal:
    return AssessmentSignal(
        signal_id=SESSION,
        tenant_id=TENANT,
        family_id=FAMILY,
        subject_ref=CHILD,
        assessment_session_id=SESSION,
        evidence_refs=("123e4567-e89b-12d3-a456-426614174005",),
        summary="家庭测评已提交，当前关注点：PARENT_CHILD_COMMUNICATION",
        captured_at=NOW,
        locale="zh-CN",
    )


def _grant(purpose: ConsentPurpose, status: ConsentStatus = ConsentStatus.GRANTED) -> ConsentGrant:
    return ConsentGrant(
        consent_id=f"123e4567-e89b-12d3-a456-42661417400{purpose.value[0]}",
        subject_person_id=CHILD,
        guardian_person_id="123e4567-e89b-12d3-a456-426614174006",
        purpose=purpose,
        status=status,
        granted_at=NOW,
        subject_age=SubjectAge(years=18),
        guardian_relation=GuardianRelation.GUARDIAN,
    )


class FakeRepository:
    def __init__(self) -> None:
        self.status = ConsentStatus.GRANTED
        self.responses: dict[str, dict[str, Any]] = {}

    async def load_submitted_signal(self, **kwargs: Any) -> AssessmentSignal | None:
        if kwargs["tenant_id"] != TENANT or kwargs["family_id"] != FAMILY:
            return None
        if kwargs["assessment_session_id"] != SESSION:
            return None
        return AssessmentSignal(**{**_signal().__dict__, "locale": kwargs["locale"]})

    async def load_consent_grants(
        self, *, purpose: ConsentPurpose, **_: Any
    ) -> tuple[ConsentGrant, ...]:
        return (_grant(purpose, self.status),)

    async def append_signal_acceptance(
        self,
        *,
        signal: AssessmentSignal,
        response: dict[str, Any],
        idempotency_key: str,
        **_: Any,
    ) -> tuple[dict[str, Any], bool]:
        existing = self.responses.get(idempotency_key)
        if existing is not None:
            if existing != response:
                raise JourneyConflictError("idempotency_conflict")
            return existing, True
        self.responses[idempotency_key] = response
        return response, False


def _client(repository: FakeRepository, actor: S01ActorContext | None = None) -> TestClient:
    actor = actor or S01ActorContext(
        actor_id="123e4567-e89b-12d3-a456-426614174006",
        tenant_id=TENANT,
        family_id=FAMILY,
    )

    async def resolve_actor(authorization: str | None, family_id: str) -> S01ActorContext:
        if authorization != "Bearer valid-token":
            raise HTTPException(status_code=401, detail="authorization_required")
        return actor

    @asynccontextmanager
    async def open_repository():
        yield repository

    app = FastAPI()
    app.include_router(
        build_vs_growth_01_router(
            S01HttpDependencies(resolve_actor=resolve_actor, open_repository=open_repository)
        )
    )
    return TestClient(app)


def _headers(key: str = "accept-1") -> dict[str, str]:
    return {
        "Authorization": "Bearer valid-token",
        "X-Tenant-Id": TENANT,
        "Idempotency-Key": key,
        "X-Correlation-Id": "correlation-1",
    }


def test_http_accept_signal_uses_actor_tenant_and_replays() -> None:
    repository = FakeRepository()
    with _client(repository) as client:
        path = f"/families/{FAMILY}/growth/vs-growth-01/signals/{SESSION}/accept"
        first = client.post(path, headers=_headers(), json={})
        assert first.status_code == 200, first.text
        assert first.json()["capability_id"] == "VS-GROWTH-01"
        assert first.json()["replayed"] is False
        replay = client.post(path, headers=_headers(), json={})
        assert replay.status_code == 200, replay.text
        assert replay.json()["replayed"] is True


def test_http_rejects_missing_auth_tenant_scope_and_consent() -> None:
    repository = FakeRepository()
    with _client(repository) as client:
        path = f"/families/{FAMILY}/growth/vs-growth-01/signals/{SESSION}/accept"
        missing_auth = client.post(
            path,
            headers={"X-Tenant-Id": TENANT, "Idempotency-Key": "no-auth"},
            json={},
        )
        assert missing_auth.status_code == 401

        wrong_tenant = client.post(
            path,
            headers={**_headers("wrong-tenant"), "X-Tenant-Id": FAMILY},
            json={},
        )
        assert wrong_tenant.status_code == 403

        repository.status = ConsentStatus.WITHDRAWN
        revoked = client.post(path, headers=_headers("revoked"), json={})
        assert revoked.status_code == 403
        assert revoked.json()["detail"] == "consent_required"

        repository.status = ConsentStatus.EXPIRED
        expired = client.post(path, headers=_headers("expired"), json={})
        assert expired.status_code == 403
        assert expired.json()["detail"] == "consent_required"


def test_http_rejects_missing_idempotency_and_cross_tenant_signal() -> None:
    repository = FakeRepository()
    with _client(repository) as client:
        path = f"/families/{FAMILY}/growth/vs-growth-01/signals/{SESSION}/accept"
        missing_key = client.post(
            path,
            headers={"Authorization": "Bearer valid-token", "X-Tenant-Id": TENANT},
            json={},
        )
        assert missing_key.status_code == 400

    foreign_actor = S01ActorContext(
        actor_id="123e4567-e89b-12d3-a456-426614174006",
        tenant_id="123e4567-e89b-12d3-a456-426614174007",
        family_id=FAMILY,
    )
    with _client(repository, actor=foreign_actor) as client:
        response = client.post(
            path,
            headers={
                **_headers("foreign"),
                "X-Tenant-Id": foreign_actor.tenant_id,
            },
            json={},
        )
        assert response.status_code == 404


def test_http_rejects_invalid_assessment_session_uuid() -> None:
    repository = FakeRepository()
    with _client(repository) as client:
        response = client.post(
            f"/families/{FAMILY}/growth/vs-growth-01/signals/not-a-uuid/accept",
            headers=_headers("invalid-session"),
            json={},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "assessment_session_id_must_be_uuid"


def test_http_rejects_same_key_with_different_locale() -> None:
    repository = FakeRepository()
    with _client(repository) as client:
        path = f"/families/{FAMILY}/growth/vs-growth-01/signals/{SESSION}/accept"
        first = client.post(path, headers=_headers("locale-conflict"), json={"locale": "zh-CN"})
        assert first.status_code == 200
        conflict = client.post(
            path,
            headers=_headers("locale-conflict"),
            json={"locale": "en-US"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"] == "idempotency_conflict"


class FakeResult:
    def __init__(self, row: dict[str, Any] | None = None, rows: list[dict[str, Any]] | None = None):
        self.row = row
        self.rows = rows or []

    def mappings(self) -> FakeResult:
        return self

    def first(self) -> dict[str, Any] | None:
        return self.row

    def __iter__(self):
        return iter(self.rows)


class FakeConnection:
    def __init__(self, results: list[FakeResult]):
        self.results = results
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, statement, parameters: dict[str, Any] | None = None) -> FakeResult:
        self.calls.append((str(statement), parameters or {}))
        return self.results.pop(0)


@pytest.mark.asyncio
async def test_postgres_signal_read_is_submitted_current_and_evidence_bound() -> None:
    connection = FakeConnection(
        [
            FakeResult(
                {
                    "assessment_session_id": SESSION,
                    "tenant_id": TENANT,
                    "family_id": FAMILY,
                    "subject_person_id": CHILD,
                    "captured_at": NOW,
                    "responses": [
                        {
                            "response_id": "123e4567-e89b-12d3-a456-426614174005",
                            "item_ref": "FOCUS",
                            "response_value": "PARENT_CHILD_COMMUNICATION",
                            "author_person_id": "123e4567-e89b-12d3-a456-426614174006",
                        }
                    ],
                }
            )
        ]
    )
    repository = S01PostgresAssessmentRepository(connection)
    signal = await repository.load_submitted_signal(
        tenant_id=TENANT,
        family_id=FAMILY,
        assessment_session_id=SESSION,
        locale="zh-CN",
    )
    assert signal is not None
    assert signal.assessment_session_id == SESSION
    assert signal.evidence_refs
    assert "s.status in ('SUBMITTED','ANALYZING','READY','ACKNOWLEDGED')" in connection.calls[0][0]
    assert connection.calls[0][1]["tenant_id"] == TENANT


@pytest.mark.asyncio
async def test_postgres_signal_without_focus_is_not_admitted() -> None:
    connection = FakeConnection(
        [
            FakeResult(
                {
                    "assessment_session_id": SESSION,
                    "tenant_id": TENANT,
                    "family_id": FAMILY,
                    "subject_person_id": CHILD,
                    "captured_at": NOW,
                    "responses": [
                        {
                            "response_id": "123e4567-e89b-12d3-a456-426614174005",
                            "item_ref": "FAMILY_STRUCTURE",
                            "response_value": "TWO_PARENT",
                            "author_person_id": "123e4567-e89b-12d3-a456-426614174006",
                        }
                    ],
                }
            )
        ]
    )
    repository = S01PostgresAssessmentRepository(connection)
    assert (
        await repository.load_submitted_signal(
            tenant_id=TENANT,
            family_id=FAMILY,
            assessment_session_id=SESSION,
        )
        is None
    )


@pytest.mark.asyncio
async def test_postgres_signal_without_evidence_provenance_is_not_admitted() -> None:
    connection = FakeConnection(
        [
            FakeResult(
                {
                    "assessment_session_id": SESSION,
                    "tenant_id": TENANT,
                    "family_id": FAMILY,
                    "subject_person_id": CHILD,
                    "captured_at": NOW,
                    "responses": [
                        {
                            "response_id": "123e4567-e89b-12d3-a456-426614174005",
                            "item_ref": "FOCUS",
                            "response_value": "PARENT_CHILD_COMMUNICATION",
                            "author_person_id": None,
                        }
                    ],
                }
            )
        ]
    )
    repository = S01PostgresAssessmentRepository(connection)
    assert (
        await repository.load_submitted_signal(
            tenant_id=TENANT,
            family_id=FAMILY,
            assessment_session_id=SESSION,
        )
        is None
    )


@pytest.mark.asyncio
async def test_postgres_consent_loader_maps_status_and_fails_closed_without_birth_date() -> None:
    connection = FakeConnection(
        [
            FakeResult(
                rows=[
                    {
                        "consent_id": "123e4567-e89b-12d3-a456-426614174008",
                        "subject_person_id": CHILD,
                        "guardian_person_id": "123e4567-e89b-12d3-a456-426614174006",
                        "purpose": "ASSESSMENT",
                        "status": "WITHDRAWN",
                        "granted_at": NOW,
                        "birth_date": date(2008, 8, 30),
                    },
                    {
                        "consent_id": "123e4567-e89b-12d3-a456-426614174009",
                        "subject_person_id": CHILD,
                        "guardian_person_id": "123e4567-e89b-12d3-a456-426614174006",
                        "purpose": "ASSESSMENT",
                        "status": "GRANTED",
                        "granted_at": NOW,
                        "birth_date": None,
                    },
                ]
            )
        ]
    )
    repository = S01PostgresAssessmentRepository(connection)
    grants = await repository.load_consent_grants(
        family_id=FAMILY,
        subject_person_id=CHILD,
        purpose=ConsentPurpose.ASSESSMENT,
    )
    assert len(grants) == 1
    assert grants[0].status is ConsentStatus.WITHDRAWN
    assert grants[0].subject_age.years == 18


class IdempotencyConnection(FakeConnection):
    def __init__(self, existing: dict[str, Any] | None = None):
        super().__init__([])
        self.existing = existing
        self.request_hash: str | None = None

    async def execute(self, statement, parameters: dict[str, Any] | None = None) -> FakeResult:
        params = parameters or {}
        sql = str(statement)
        self.calls.append((sql, params))
        if "insert into idempotency_keys" in sql:
            self.request_hash = params["request_hash"]
            return FakeResult()
        if "select action_name,request_hash,response_body" in sql:
            existing = self.existing or {
                "action_name": "VS-GROWTH-01.AcceptSignal",
                "request_hash": self.request_hash,
                "response_body": None,
            }
            return FakeResult(existing)
        return FakeResult()


class FailingOutboxConnection(IdempotencyConnection):
    async def execute(self, statement, parameters: dict[str, Any] | None = None) -> FakeResult:
        if "insert into outbox_events" in str(statement):
            raise RuntimeError("simulated_outbox_failure")
        return await super().execute(statement, parameters)


@pytest.mark.asyncio
async def test_postgres_acceptance_appends_audit_outbox_and_conflict_is_refused() -> None:
    signal = _signal()
    response = {"capability_id": "VS-GROWTH-01", "stage": "SIGNAL_ACCEPTED"}
    connection = IdempotencyConnection()
    repository = S01PostgresAssessmentRepository(connection)
    persisted, replay = await repository.append_signal_acceptance(
        signal=signal,
        actor_id="123e4567-e89b-12d3-a456-426614174006",
        idempotency_key="accept-1",
        correlation_id="corr-1",
        response=response,
    )
    assert persisted == response
    assert replay is False
    assert any("insert into audit_logs" in sql for sql, _ in connection.calls)
    assert any("insert into outbox_events" in sql for sql, _ in connection.calls)
    assert any("update idempotency_keys" in sql for sql, _ in connection.calls)
    assert all(
        params.get("event_name") == AuditEventName.SIGNAL_ACCEPTED.value
        for sql, params in connection.calls
        if "insert into audit_logs" in sql or "insert into outbox_events" in sql
    )
    connection.existing = {
        "action_name": "VS-GROWTH-01.AcceptSignal",
        "request_hash": connection.request_hash,
        "response_body": response,
    }
    replayed, replay = await repository.append_signal_acceptance(
        signal=signal,
        actor_id="123e4567-e89b-12d3-a456-426614174006",
        idempotency_key="accept-1",
        correlation_id="corr-retry",
        response=response,
    )
    assert replayed == response
    assert replay is True

    conflict = IdempotencyConnection(
        {
            "action_name": "VS-GROWTH-01.AcceptSignal",
            "request_hash": "different-request",
            "response_body": None,
        }
    )
    with pytest.raises(JourneyConflictError, match="idempotency_conflict"):
        await S01PostgresAssessmentRepository(conflict).append_signal_acceptance(
            signal=signal,
            actor_id="123e4567-e89b-12d3-a456-426614174006",
            idempotency_key="accept-1",
            correlation_id="corr-1",
            response=response,
        )


@pytest.mark.asyncio
async def test_postgres_acceptance_propagates_outbox_failure_for_transaction_rollback() -> None:
    connection = FailingOutboxConnection()
    with pytest.raises(RuntimeError, match="simulated_outbox_failure"):
        await S01PostgresAssessmentRepository(connection).append_signal_acceptance(
            signal=_signal(),
            actor_id="123e4567-e89b-12d3-a456-426614174006",
            idempotency_key="accept-rollback",
            correlation_id="corr-rollback",
            response={"capability_id": "VS-GROWTH-01", "stage": "SIGNAL_ACCEPTED"},
        )
    assert not any("update idempotency_keys" in sql for sql, _ in connection.calls)
