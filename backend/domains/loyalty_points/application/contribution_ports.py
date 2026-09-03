"""Ports and context for the adult contribution ledger."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..domain.contribution import (
    ContributionAuditEvent,
    ContributionOperation,
    ContributionOutboxEvent,
    ContributionRecord,
    PlatformPoint,
)


@dataclass(frozen=True)
class ContributionActionContext:
    tenant_id: str
    family_id: str
    actor_person_id: str
    actor: str
    correlation_id: str
    adult_verified: bool = False
    adult_verification_ref: str = ""
    idempotency_key: str | None = None
    # Populated by the authenticated tenant/family adapter, never by an HTTP
    # request.  An empty set intentionally means that cross-family access is
    # denied even when a caller guesses a family identifier.
    authorized_family_ids: frozenset[str] = frozenset()


class ContributionRepositoryPort(Protocol):
    async def checkpoint(self) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...

    async def save_record(self, record: ContributionRecord) -> None: ...

    async def get_record(self, tenant_id: str, contribution_id: str) -> ContributionRecord: ...

    async def find_operation(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> ContributionOperation | None: ...

    async def save_operation(self, operation: ContributionOperation) -> None: ...

    async def append_audit(self, event: ContributionAuditEvent) -> None: ...

    async def append_outbox(self, event: ContributionOutboxEvent) -> None: ...

    async def append_platform_point(self, entry: PlatformPoint) -> None: ...

    async def list_audits(
        self, tenant_id: str, contribution_id: str
    ) -> list[ContributionAuditEvent]: ...

    async def list_outbox(
        self, tenant_id: str, contribution_id: str
    ) -> list[ContributionOutboxEvent]: ...

    async def list_platform_points(self, tenant_id: str, family_id: str) -> list[PlatformPoint]: ...
