"""Synthetic operator-query composition for development and test only.

This module preserves the production API shape and authorization sequence while
using process-local simulated records.  It is deliberately guarded by the
explicit development environment allow-list and is never imported into a
production composition path as a fallback.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from fastapi import FastAPI

from backend.apps.family_api.dev_wiring import is_dev_environment
from backend.apps.family_api.evaluation_query_wiring import (
    build_production_evaluation_query_service,
    install_evaluation_query_service,
)
from backend.apps.family_api.experience_operations_query_wiring import (
    install_experience_operations_query,
)
from backend.intelligence.evaluation.operator_identity import OperatorIdentity
from backend.intelligence.evaluation.query import EVALUATION_READ_SCOPE
from backend.intelligence.evaluation.report_archive import BenchmarkReportArchive
from backend.intelligence.evaluation.request_operator_identity import current_operator_bearer
from backend.intelligence.evaluation.slice_archive import BenchmarkSliceArchive
from backend.intelligence.experience.operations_query import (
    EXPERIENCE_OPERATIONS_READ_SCOPE,
    AuthorizedExperienceOperationsQueryService,
    ExperienceOperationsAuditEvent,
    HmacExperienceOperationsCursorSigner,
)
from backend.intelligence.experience.persistence import (
    ExperienceDeliveryAttemptCursor,
    ExperienceDeliveryAttemptPage,
    ExperienceDeliveryAttemptStatus,
    ExperienceDeliveryAttemptSummary,
    StoredExperienceDeliveryAttempt,
)

_DEV_OPERATOR_ENVIRONMENT = "staging"
_DEV_CURSOR_SECRET = b"dev-only-experience-operations-key"


class DevOperatorIdentityPort:
    """Resolve a known dev-auth session as a synthetic operator identity."""

    async def resolve(self, *, environment: str) -> OperatorIdentity:
        if environment != _DEV_OPERATOR_ENVIRONMENT:
            raise ValueError("development operator environment must be staging")
        bearer = current_operator_bearer()
        from backend.domains.assessment.api.dev_auth import get_state

        identity = get_state().tokens.get(bearer)
        if not identity:
            from backend.intelligence.evaluation.operator_identity import OperatorIdentityError

            raise OperatorIdentityError("IDENTITY_REQUEST_TOKEN_INVALID")
        token_digest = hashlib.sha256(bearer.encode("utf-8")).hexdigest()[:16]
        return OperatorIdentity(
            operator_id=f"dev-operator:{identity['account_id']}",
            environment=environment,
            authorization_ref=f"dev-synthetic:{token_digest}",
            scopes=(EXPERIENCE_OPERATIONS_READ_SCOPE, EVALUATION_READ_SCOPE),
        )


class DevExperienceOperationsRuntime:
    """Deterministic metadata-only attempt ledger for dev/test dashboards."""

    def __init__(self) -> None:
        now = datetime(2026, 8, 31, 12, tzinfo=UTC)
        self._attempts = (
            StoredExperienceDeliveryAttempt(
                message_id="dev-attempt-pending",
                attempts=1,
                status=ExperienceDeliveryAttemptStatus.PENDING,
                last_error=None,
                updated_at=now,
                terminal_at=None,
                lease_owner="dev-worker",
                lease_until=None,
            ),
            StoredExperienceDeliveryAttempt(
                message_id="dev-attempt-published",
                attempts=1,
                status=ExperienceDeliveryAttemptStatus.PUBLISHED,
                last_error=None,
                updated_at=now.replace(hour=11),
                terminal_at=now.replace(hour=11),
                lease_owner=None,
                lease_until=None,
            ),
        )

    async def delivery_attempts_page(
        self,
        *,
        limit: int = 100,
        status: ExperienceDeliveryAttemptStatus | None = None,
        after: ExperienceDeliveryAttemptCursor | None = None,
    ) -> ExperienceDeliveryAttemptPage:
        values = tuple(item for item in self._attempts if status is None or item.status == status)
        if after is not None:
            values = tuple(
                item
                for item in values
                if (item.updated_at, item.message_id) < (after.updated_at, after.message_id)
            )
        page = values[:limit]
        next_cursor = (
            ExperienceDeliveryAttemptCursor(page[-1].updated_at, page[-1].message_id)
            if len(values) > len(page) and page
            else None
        )
        return ExperienceDeliveryAttemptPage(items=page, next_cursor=next_cursor)

    async def delivery_attempt_summary(self) -> ExperienceDeliveryAttemptSummary:
        counts = tuple(
            (status, sum(item.status == status for item in self._attempts))
            for status in ExperienceDeliveryAttemptStatus
        )
        return ExperienceDeliveryAttemptSummary(counts=counts)


class DevEvaluationArchiveRuntime:
    """Deterministic metadata-only evaluation archive for dev/test."""

    def __init__(self) -> None:
        archived_at = datetime(2026, 8, 31, 12, tzinfo=UTC)
        self._reports = (
            BenchmarkReportArchive(
                report_ref="benchmark:dev:gold.v1",
                case_version="gold.v1",
                dataset_fingerprint="d" * 64,
                total_cases=3,
                report_payload={"source": "synthetic", "status": "PASS"},
                archived_at=archived_at,
            ),
        )
        self._slices: tuple[BenchmarkSliceArchive, ...] = ()

    async def list(self, *, case_version=None, dataset_fingerprint=None, limit=50):
        return tuple(
            item
            for item in self._reports
            if (case_version is None or item.case_version == case_version)
            and (dataset_fingerprint is None or item.dataset_fingerprint == dataset_fingerprint)
        )[:limit]

    async def list_slices(self, *, report_ref=None, dimension=None, value=None, limit=100):
        return tuple(
            item
            for item in self._slices
            if (report_ref is None or item.report_ref == report_ref)
            and (dimension is None or item.dimension == dimension)
            and (value is None or item.value == value)
        )[:limit]


class DevOperationsAuditSink:
    """In-memory metadata audit sink; records are intentionally non-durable."""

    def __init__(self) -> None:
        self.events: list[ExperienceOperationsAuditEvent] = []

    async def record(self, event: ExperienceOperationsAuditEvent) -> None:
        self.events.append(event)


def install_dev_operator_query_wiring(application: FastAPI) -> None:
    """Install synthetic operator query services only in dev/test."""

    if not is_dev_environment():
        raise RuntimeError("dev operator query wiring refuses to run outside dev/test")
    audit_sink = DevOperationsAuditSink()
    operations_service = AuthorizedExperienceOperationsQueryService(
        environment=_DEV_OPERATOR_ENVIRONMENT,
        identity_port=DevOperatorIdentityPort(),
        runtime=DevExperienceOperationsRuntime(),
        audit_sink=audit_sink,
    )
    install_experience_operations_query(
        application,
        operations_service,
        HmacExperienceOperationsCursorSigner(_DEV_CURSOR_SECRET),
    )
    evaluation_service = build_production_evaluation_query_service(
        environment=_DEV_OPERATOR_ENVIRONMENT,
        identity_port=DevOperatorIdentityPort(),
        archive_runtime=DevEvaluationArchiveRuntime(),
    )
    install_evaluation_query_service(application, evaluation_service)


__all__ = [
    "DevEvaluationArchiveRuntime",
    "DevExperienceOperationsRuntime",
    "DevOperatorIdentityPort",
    "DevOperationsAuditSink",
    "install_dev_operator_query_wiring",
]
