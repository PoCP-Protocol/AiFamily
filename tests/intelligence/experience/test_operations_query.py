from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.evaluation.operator_identity import (
    OperatorIdentity,
    OperatorIdentityError,
)
from backend.intelligence.experience.operations_query import (
    EXPERIENCE_OPERATIONS_READ_SCOPE,
    AuthorizedExperienceOperationsQueryService,
    ExperienceOperationsAuditEvent,
    ExperienceOperationsCursorError,
    ExperienceOperationsQueryError,
    HmacExperienceOperationsCursorSigner,
)
from backend.intelligence.experience.persistence import (
    ExperienceDeliveryAttemptCursor,
    ExperienceDeliveryAttemptPage,
    ExperienceDeliveryAttemptStatus,
    ExperienceDeliveryAttemptSummary,
    StoredExperienceDeliveryAttempt,
)


class IdentityPort:
    def __init__(self, identity: OperatorIdentity) -> None:
        self.identity = identity

    async def resolve(self, *, environment: str) -> OperatorIdentity:
        return self.identity


class Runtime:
    async def delivery_attempts_page(self, **_kwargs):
        item = StoredExperienceDeliveryAttempt(
            message_id="attempt-1",
            attempts=1,
            status=ExperienceDeliveryAttemptStatus.PUBLISHED,
            last_error=None,
            updated_at=datetime(2026, 8, 30, tzinfo=UTC),
            terminal_at=datetime(2026, 8, 30, tzinfo=UTC),
            lease_owner=None,
            lease_until=None,
        )
        return ExperienceDeliveryAttemptPage(items=(item,), next_cursor=None)

    async def delivery_attempt_summary(self):
        return ExperienceDeliveryAttemptSummary(
            counts=((ExperienceDeliveryAttemptStatus.PUBLISHED, 1),)
        )


class AuditSink:
    def __init__(self) -> None:
        self.events: list[ExperienceOperationsAuditEvent] = []

    async def record(self, event: ExperienceOperationsAuditEvent) -> None:
        self.events.append(event)


class FailingAuditSink:
    async def record(self, _event: ExperienceOperationsAuditEvent) -> None:
        raise RuntimeError("audit unavailable")


class FailingIdentityPort:
    async def resolve(self, *, environment: str) -> OperatorIdentity:
        raise OperatorIdentityError(f"identity unavailable for {environment}")


def _identity(*scopes: str, environment: str = "production") -> OperatorIdentity:
    return OperatorIdentity(
        operator_id="operator-1",
        environment=environment,
        authorization_ref="authz-1",
        scopes=tuple(scopes),
    )


@pytest.mark.asyncio
async def test_authorized_operations_query_delegates_metadata_only() -> None:
    service = AuthorizedExperienceOperationsQueryService(
        environment="production",
        identity_port=IdentityPort(_identity(EXPERIENCE_OPERATIONS_READ_SCOPE)),
        runtime=Runtime(),
    )

    page = await service.list_attempts_page(limit=10)
    summary = await service.summary()

    assert page.items[0].message_id == "attempt-1"
    assert summary.count(ExperienceDeliveryAttemptStatus.PUBLISHED) == 1


@pytest.mark.asyncio
async def test_operations_query_rejects_missing_or_mismatched_operator_scope() -> None:
    missing = AuthorizedExperienceOperationsQueryService(
        environment="production",
        identity_port=IdentityPort(_identity("ai.other.read")),
        runtime=Runtime(),
    )
    with pytest.raises(PermissionError, match="SCOPE_MISSING"):
        await missing.summary()

    mismatched = AuthorizedExperienceOperationsQueryService(
        environment="production",
        identity_port=IdentityPort(
            _identity(EXPERIENCE_OPERATIONS_READ_SCOPE, environment="staging")
        ),
        runtime=Runtime(),
    )
    with pytest.raises(OperatorIdentityError, match="ENVIRONMENT_MISMATCH"):
        await mismatched.summary()


@pytest.mark.asyncio
async def test_operations_query_records_metadata_only_audit_events() -> None:
    sink = AuditSink()
    service = AuthorizedExperienceOperationsQueryService(
        environment="production",
        identity_port=IdentityPort(_identity(EXPERIENCE_OPERATIONS_READ_SCOPE)),
        runtime=Runtime(),
        audit_sink=sink,
    )

    await service.summary()

    assert len(sink.events) == 1
    assert sink.events[0].operator_id == "operator-1"
    assert sink.events[0].authorization_ref == "authz-1"
    assert sink.events[0].operation == "summary"
    assert sink.events[0].outcome == "ALLOWED"

    denied_sink = AuditSink()
    denied = AuthorizedExperienceOperationsQueryService(
        environment="production",
        identity_port=IdentityPort(_identity("ai.other.read")),
        runtime=Runtime(),
        audit_sink=denied_sink,
    )
    with pytest.raises(PermissionError):
        await denied.summary()
    assert denied_sink.events[0].outcome == "DENIED"

    identity_sink = AuditSink()
    identity_failure = AuthorizedExperienceOperationsQueryService(
        environment="production",
        identity_port=FailingIdentityPort(),
        runtime=Runtime(),
        audit_sink=identity_sink,
    )
    with pytest.raises(OperatorIdentityError):
        await identity_failure.summary()
    assert identity_sink.events[0].outcome == "IDENTITY_ERROR"


@pytest.mark.asyncio
async def test_operations_query_fails_closed_when_audit_sink_is_unavailable() -> None:
    service = AuthorizedExperienceOperationsQueryService(
        environment="production",
        identity_port=IdentityPort(_identity(EXPERIENCE_OPERATIONS_READ_SCOPE)),
        runtime=Runtime(),
        audit_sink=FailingAuditSink(),
    )

    with pytest.raises(ExperienceOperationsQueryError, match="AUDIT_UNAVAILABLE"):
        await service.summary()


def test_operations_cursor_signer_binds_status_and_expiry() -> None:
    signer = HmacExperienceOperationsCursorSigner(
        b"0123456789abcdef", ttl=timedelta(minutes=1)
    )
    cursor = ExperienceDeliveryAttemptCursor(
        datetime(2026, 8, 30, 12, tzinfo=UTC), "attempt-1"
    )
    token = signer.encode(
        cursor,
        status=ExperienceDeliveryAttemptStatus.PENDING,
        now=datetime(2026, 8, 30, 12, tzinfo=UTC),
    )

    assert signer.decode(
        token,
        status=ExperienceDeliveryAttemptStatus.PENDING,
        now=datetime(2026, 8, 30, 12, 0, 30, tzinfo=UTC),
    ) == cursor
    with pytest.raises(ExperienceOperationsCursorError, match="STATUS_MISMATCH"):
        signer.decode(token, status=ExperienceDeliveryAttemptStatus.PUBLISHED)
    with pytest.raises(ExperienceOperationsCursorError, match="EXPIRED"):
        signer.decode(
            token,
            status=ExperienceDeliveryAttemptStatus.PENDING,
            now=datetime(2026, 8, 30, 12, 2, tzinfo=UTC),
        )


def test_operations_query_validates_runtime_and_environment() -> None:
    with pytest.raises(ExperienceOperationsQueryError, match="ENVIRONMENT_INVALID"):
        AuthorizedExperienceOperationsQueryService(
            environment="test",
            identity_port=IdentityPort(_identity(EXPERIENCE_OPERATIONS_READ_SCOPE)),
            runtime=Runtime(),
        )
    with pytest.raises(ExperienceOperationsQueryError, match="RUNTIME_REQUIRED"):
        AuthorizedExperienceOperationsQueryService(
            environment="production",
            identity_port=IdentityPort(_identity(EXPERIENCE_OPERATIONS_READ_SCOPE)),
            runtime=object(),
        )
