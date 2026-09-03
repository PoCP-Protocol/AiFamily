"""Authorized, metadata-only operational queries for Experience delivery.

The service is deliberately separate from family-facing API routes.  It accepts
an externally resolved operator identity and delegates only to bounded runtime
queries; no family scope, outbox payload, or model output crosses this boundary.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import inspect
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from backend.intelligence.evaluation.operator_identity import (
    OperatorIdentity,
    OperatorIdentityError,
    OperatorIdentityPort,
)
from backend.intelligence.experience.persistence import (
    ExperienceDeliveryAttemptCursor,
    ExperienceDeliveryAttemptPage,
    ExperienceDeliveryAttemptStatus,
    ExperienceDeliveryAttemptSummary,
)

EXPERIENCE_OPERATIONS_READ_SCOPE = "ai.experience.operations.read"
_QUERY_ENVIRONMENTS = frozenset({"staging", "production"})


class ExperienceOperationsQueryError(ValueError):
    """Raised when an operational query cannot be authorized or served."""


class ExperienceOperationsCursorError(ValueError):
    """Raised when a dashboard cursor is malformed, expired, or tampered with."""


@dataclass(frozen=True, slots=True)
class ExperienceOperationsAuditEvent:
    """Metadata-only operator access event; no token or family content."""

    operator_id: str
    authorization_ref: str
    environment: str
    operation: str
    outcome: str
    occurred_at: datetime


class ExperienceOperationsAuditSink(Protocol):
    async def record(self, event: ExperienceOperationsAuditEvent) -> None: ...


@dataclass(frozen=True, slots=True)
class HmacExperienceOperationsCursorSigner:
    """Sign short-lived dashboard cursors with an injected operator secret."""

    secret: bytes
    ttl: timedelta = timedelta(minutes=10)

    def __post_init__(self) -> None:
        if not isinstance(self.secret, bytes) or len(self.secret) < 16:
            raise ExperienceOperationsCursorError("EXPERIENCE_CURSOR_SECRET_INVALID")
        if self.ttl <= timedelta(0):
            raise ExperienceOperationsCursorError("EXPERIENCE_CURSOR_TTL_INVALID")

    def encode(
        self,
        cursor: ExperienceDeliveryAttemptCursor,
        *,
        status: ExperienceDeliveryAttemptStatus | None = None,
        now: datetime | None = None,
    ) -> str:
        if not isinstance(cursor, ExperienceDeliveryAttemptCursor):
            raise ExperienceOperationsCursorError("EXPERIENCE_CURSOR_INVALID")
        issued_at = _aware(now or datetime.now(UTC))
        payload = {
            "cursor_updated_at": _aware(cursor.updated_at).isoformat(),
            "message_id": cursor.message_id,
            "status": None if status is None else status.value,
            "issued_at": issued_at.isoformat(),
        }
        encoded = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
        signature = self._sign(encoded)
        return f"{encoded}.{signature}"

    def decode(
        self,
        token: str,
        *,
        status: ExperienceDeliveryAttemptStatus | None = None,
        now: datetime | None = None,
    ) -> ExperienceDeliveryAttemptCursor:
        if not isinstance(token, str) or not token.strip() or token.count(".") != 1:
            raise ExperienceOperationsCursorError("EXPERIENCE_CURSOR_INVALID")
        encoded, signature = token.split(".", 1)
        if not hmac.compare_digest(signature, self._sign(encoded)):
            raise ExperienceOperationsCursorError("EXPERIENCE_CURSOR_SIGNATURE_INVALID")
        try:
            payload = json.loads(_unb64(encoded).decode("utf-8"))
            cursor = ExperienceDeliveryAttemptCursor(
                updated_at=datetime.fromisoformat(payload["cursor_updated_at"]),
                message_id=payload["message_id"],
            )
            issued_at = _aware(datetime.fromisoformat(payload["issued_at"]))
            token_status = payload.get("status")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ExperienceOperationsCursorError("EXPERIENCE_CURSOR_INVALID") from error
        expected_status = None if status is None else status.value
        if token_status != expected_status:
            raise ExperienceOperationsCursorError("EXPERIENCE_CURSOR_STATUS_MISMATCH")
        reference = _aware(now or datetime.now(UTC))
        if issued_at > reference or reference - issued_at > self.ttl:
            raise ExperienceOperationsCursorError("EXPERIENCE_CURSOR_EXPIRED")
        return cursor

    def _sign(self, encoded: str) -> str:
        digest = hmac.new(self.secret, encoded.encode("ascii"), hashlib.sha256).digest()
        return _b64(digest)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class ExperienceOperationsQueryRuntime(Protocol):
    async def delivery_attempts_page(
        self,
        *,
        limit: int = 100,
        status: ExperienceDeliveryAttemptStatus | None = None,
        after: ExperienceDeliveryAttemptCursor | None = None,
    ) -> ExperienceDeliveryAttemptPage: ...

    async def delivery_attempt_summary(self) -> ExperienceDeliveryAttemptSummary: ...


@dataclass(frozen=True, slots=True)
class AuthorizedExperienceOperationsQueryService:
    """Operator-scoped facade for dashboard and alerting metadata."""

    environment: str
    identity_port: OperatorIdentityPort
    runtime: ExperienceOperationsQueryRuntime
    required_scope: str = EXPERIENCE_OPERATIONS_READ_SCOPE
    audit_sink: ExperienceOperationsAuditSink | None = None

    def __post_init__(self) -> None:
        if self.environment not in _QUERY_ENVIRONMENTS:
            raise ExperienceOperationsQueryError(
                "EXPERIENCE_OPERATIONS_QUERY_ENVIRONMENT_INVALID"
            )
        if not callable(getattr(self.identity_port, "resolve", None)):
            raise ExperienceOperationsQueryError(
                "EXPERIENCE_OPERATIONS_QUERY_IDENTITY_PORT_REQUIRED"
            )
        if not callable(getattr(self.runtime, "delivery_attempts_page", None)) or not callable(
            getattr(self.runtime, "delivery_attempt_summary", None)
        ):
            raise ExperienceOperationsQueryError("EXPERIENCE_OPERATIONS_QUERY_RUNTIME_REQUIRED")
        if not isinstance(self.required_scope, str) or not self.required_scope.strip():
            raise ExperienceOperationsQueryError("EXPERIENCE_OPERATIONS_QUERY_SCOPE_REQUIRED")
        if self.audit_sink is not None and not callable(getattr(self.audit_sink, "record", None)):
            raise ExperienceOperationsQueryError("EXPERIENCE_OPERATIONS_QUERY_AUDIT_SINK_REQUIRED")

    async def list_attempts_page(
        self,
        *,
        limit: int = 100,
        status: ExperienceDeliveryAttemptStatus | None = None,
        after: ExperienceDeliveryAttemptCursor | None = None,
    ) -> ExperienceDeliveryAttemptPage:
        await self._authorize("list_attempts_page")
        try:
            return await self.runtime.delivery_attempts_page(
                limit=limit,
                status=status,
                after=after,
            )
        except ExperienceOperationsQueryError:
            raise
        except Exception as error:  # noqa: BLE001 - query boundary fails closed
            raise ExperienceOperationsQueryError(
                "EXPERIENCE_OPERATIONS_QUERY_RUNTIME_UNAVAILABLE"
            ) from error

    async def summary(self) -> ExperienceDeliveryAttemptSummary:
        await self._authorize("summary")
        try:
            return await self.runtime.delivery_attempt_summary()
        except ExperienceOperationsQueryError:
            raise
        except Exception as error:  # noqa: BLE001 - query boundary fails closed
            raise ExperienceOperationsQueryError(
                "EXPERIENCE_OPERATIONS_QUERY_RUNTIME_UNAVAILABLE"
            ) from error

    async def _authorize(self, operation: str) -> OperatorIdentity:
        try:
            identity = await self.identity_port.resolve(environment=self.environment)
        except OperatorIdentityError:
            await self._record_audit("unknown", "unknown", operation, "IDENTITY_ERROR")
            raise
        except Exception as error:  # noqa: BLE001 - identity boundary fails closed
            await self._record_audit("unknown", "unknown", operation, "IDENTITY_ERROR")
            raise OperatorIdentityError(
                "EXPERIENCE_OPERATIONS_QUERY_IDENTITY_UNAVAILABLE"
            ) from error
        if not isinstance(identity, OperatorIdentity):
            await self._record_audit("unknown", "unknown", operation, "IDENTITY_ERROR")
            raise OperatorIdentityError("EXPERIENCE_OPERATIONS_QUERY_IDENTITY_INVALID")
        if identity.environment != self.environment:
            await self._record_audit(
                identity.operator_id,
                identity.authorization_ref,
                operation,
                "DENIED",
            )
            raise OperatorIdentityError("EXPERIENCE_OPERATIONS_QUERY_ENVIRONMENT_MISMATCH")
        if self.required_scope not in identity.scopes:
            await self._record_audit(
                identity.operator_id,
                identity.authorization_ref,
                operation,
                "DENIED",
            )
            raise PermissionError("EXPERIENCE_OPERATIONS_QUERY_SCOPE_MISSING")
        await self._record_audit(
            identity.operator_id,
            identity.authorization_ref,
            operation,
            "ALLOWED",
        )
        return identity

    async def _record_audit(
        self,
        operator_id: str,
        authorization_ref: str,
        operation: str,
        outcome: str,
    ) -> None:
        if self.audit_sink is None:
            return
        event = ExperienceOperationsAuditEvent(
            operator_id=operator_id,
            authorization_ref=authorization_ref,
            environment=self.environment,
            operation=operation,
            outcome=outcome,
            occurred_at=datetime.now(UTC),
        )
        try:
            result = self.audit_sink.record(event)
            if inspect.isawaitable(result):
                await result
        except Exception as error:  # noqa: BLE001 - audit boundary fails closed
            raise ExperienceOperationsQueryError(
                "EXPERIENCE_OPERATIONS_QUERY_AUDIT_UNAVAILABLE"
            ) from error


__all__ = [
    "AuthorizedExperienceOperationsQueryService",
    "EXPERIENCE_OPERATIONS_READ_SCOPE",
    "ExperienceOperationsAuditEvent",
    "ExperienceOperationsAuditSink",
    "ExperienceOperationsCursorError",
    "ExperienceOperationsQueryError",
    "ExperienceOperationsQueryRuntime",
    "HmacExperienceOperationsCursorSigner",
]
