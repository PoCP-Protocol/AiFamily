"""Authorized, metadata-only queries over archived AI evaluation evidence.

Evaluation reports are platform evidence, not family-facing business facts.  A
query therefore requires an externally resolved operator identity and an
explicit read scope.  The service deliberately delegates persistence to the
archive runtime and never accepts tenant/family identifiers from a caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.intelligence.evaluation.operator_identity import (
    OperatorIdentity,
    OperatorIdentityError,
    OperatorIdentityPort,
)
from backend.intelligence.evaluation.report_archive import BenchmarkReportArchive
from backend.intelligence.evaluation.slice_archive import BenchmarkSliceArchive

EVALUATION_READ_SCOPE = "ai.evaluation.read"
_QUERY_ENVIRONMENTS = frozenset({"staging", "production"})


class EvaluationQueryError(ValueError):
    """Raised when an evaluation query cannot be authorized or served."""


class EvaluationArchiveQueryRuntime(Protocol):
    async def list(
        self,
        *,
        case_version: str | None = None,
        dataset_fingerprint: str | None = None,
        limit: int = 50,
    ) -> tuple[BenchmarkReportArchive, ...]: ...

    async def list_slices(
        self,
        *,
        report_ref: str | None = None,
        dimension: str | None = None,
        value: str | None = None,
        limit: int = 100,
    ) -> tuple[BenchmarkSliceArchive, ...]: ...


@dataclass(frozen=True, slots=True)
class AuthorizedEvaluationQueryService:
    """Read-only facade with an operator scope and environment boundary."""

    environment: str
    identity_port: OperatorIdentityPort
    archive_runtime: EvaluationArchiveQueryRuntime
    required_scope: str = EVALUATION_READ_SCOPE

    def __post_init__(self) -> None:
        if self.environment not in _QUERY_ENVIRONMENTS:
            raise EvaluationQueryError("EVALUATION_QUERY_ENVIRONMENT_INVALID")
        if not callable(getattr(self.identity_port, "resolve", None)):
            raise EvaluationQueryError("EVALUATION_QUERY_IDENTITY_PORT_REQUIRED")
        if not callable(getattr(self.archive_runtime, "list", None)) or not callable(
            getattr(self.archive_runtime, "list_slices", None)
        ):
            raise EvaluationQueryError("EVALUATION_QUERY_RUNTIME_REQUIRED")
        if not isinstance(self.required_scope, str) or not self.required_scope.strip():
            raise EvaluationQueryError("EVALUATION_QUERY_SCOPE_REQUIRED")

    async def list_reports(
        self,
        *,
        case_version: str | None = None,
        dataset_fingerprint: str | None = None,
        limit: int = 50,
    ) -> tuple[BenchmarkReportArchive, ...]:
        await self._authorize()
        try:
            return await self.archive_runtime.list(
                case_version=case_version,
                dataset_fingerprint=dataset_fingerprint,
                limit=limit,
            )
        except EvaluationQueryError:
            raise
        except Exception as exc:  # noqa: BLE001 - query boundary fails closed
            raise EvaluationQueryError("EVALUATION_QUERY_RUNTIME_UNAVAILABLE") from exc

    async def list_slices(
        self,
        *,
        report_ref: str | None = None,
        dimension: str | None = None,
        value: str | None = None,
        limit: int = 100,
    ) -> tuple[BenchmarkSliceArchive, ...]:
        await self._authorize()
        try:
            return await self.archive_runtime.list_slices(
                report_ref=report_ref,
                dimension=dimension,
                value=value,
                limit=limit,
            )
        except EvaluationQueryError:
            raise
        except Exception as exc:  # noqa: BLE001 - query boundary fails closed
            raise EvaluationQueryError("EVALUATION_QUERY_RUNTIME_UNAVAILABLE") from exc

    async def _authorize(self) -> OperatorIdentity:
        try:
            identity = await self.identity_port.resolve(environment=self.environment)
        except OperatorIdentityError:
            raise
        except Exception as exc:  # noqa: BLE001 - identity boundary fails closed
            raise OperatorIdentityError("EVALUATION_QUERY_IDENTITY_UNAVAILABLE") from exc
        if not isinstance(identity, OperatorIdentity):
            raise OperatorIdentityError("EVALUATION_QUERY_IDENTITY_INVALID")
        if identity.environment != self.environment:
            raise OperatorIdentityError("EVALUATION_QUERY_ENVIRONMENT_MISMATCH")
        if self.required_scope not in identity.scopes:
            raise PermissionError("EVALUATION_QUERY_SCOPE_MISSING")
        return identity


__all__ = [
    "AuthorizedEvaluationQueryService",
    "EVALUATION_READ_SCOPE",
    "EvaluationArchiveQueryRuntime",
    "EvaluationQueryError",
]
