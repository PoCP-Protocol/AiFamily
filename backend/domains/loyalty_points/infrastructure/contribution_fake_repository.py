"""In-memory adapter for the adult contribution ledger.

The fake stores the same records, audit events, outbox messages and point
entries as the SQL adapter.  ``fail_next_commit`` is deliberately available to
exercise the transaction rollback path without pretending that a fake is a
database.
"""

from __future__ import annotations

from copy import deepcopy

from ..application.contribution_ports import ContributionRepositoryPort
from ..domain.contribution import (
    ContributionAuditEvent,
    ContributionNotFoundError,
    ContributionOperation,
    ContributionOutboxEvent,
    ContributionRecord,
    PlatformPoint,
)


class FakeContributionRepository(ContributionRepositoryPort):
    def __init__(self) -> None:
        self.records: dict[str, ContributionRecord] = {}
        self.operations: dict[tuple[str, str, str], ContributionOperation] = {}
        self.audits: list[ContributionAuditEvent] = []
        self.outbox: list[ContributionOutboxEvent] = []
        self.platform_points: list[PlatformPoint] = []
        self.fail_next_commit = False
        self._checkpoint: tuple[dict, dict, list, list, list] | None = None

    async def checkpoint(self) -> None:
        self._checkpoint = deepcopy(
            (
                self.records,
                self.operations,
                self.audits,
                self.outbox,
                self.platform_points,
            )
        )

    async def commit(self) -> None:
        if self.fail_next_commit:
            self.fail_next_commit = False
            raise RuntimeError("injected_contribution_commit_failure")
        self._checkpoint = None

    async def rollback(self) -> None:
        if self._checkpoint is None:
            return
        (
            self.records,
            self.operations,
            self.audits,
            self.outbox,
            self.platform_points,
        ) = deepcopy(self._checkpoint)
        self._checkpoint = None

    async def save_record(self, record: ContributionRecord) -> None:
        self.records[record.contribution_id] = record.model_copy(deep=True)

    async def get_record(self, tenant_id: str, contribution_id: str) -> ContributionRecord:
        record = self.records.get(contribution_id)
        if record is None or record.tenant_id != tenant_id:
            raise ContributionNotFoundError("contribution_not_found")
        return record.model_copy(deep=True)

    async def find_operation(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> ContributionOperation | None:
        return self.operations.get((tenant_id, family_id, idempotency_key))

    async def save_operation(self, operation: ContributionOperation) -> None:
        self.operations[(operation.tenant_id, operation.family_id, operation.idempotency_key)] = (
            operation.model_copy(deep=True)
        )

    async def append_audit(self, event: ContributionAuditEvent) -> None:
        self.audits.append(event.model_copy(deep=True))

    async def append_outbox(self, event: ContributionOutboxEvent) -> None:
        self.outbox.append(event.model_copy(deep=True))

    async def append_platform_point(self, entry: PlatformPoint) -> None:
        self.platform_points.append(entry.model_copy(deep=True))

    async def list_audits(
        self, tenant_id: str, contribution_id: str
    ) -> list[ContributionAuditEvent]:
        return [
            event.model_copy(deep=True)
            for event in self.audits
            if event.tenant_id == tenant_id and event.resource_id == contribution_id
        ]

    async def list_outbox(
        self, tenant_id: str, contribution_id: str
    ) -> list[ContributionOutboxEvent]:
        return [
            event.model_copy(deep=True)
            for event in self.outbox
            if event.tenant_id == tenant_id and event.aggregate_id == contribution_id
        ]

    async def list_platform_points(self, tenant_id: str, family_id: str) -> list[PlatformPoint]:
        return [
            entry.model_copy(deep=True)
            for entry in self.platform_points
            if entry.tenant_id == tenant_id and entry.family_id == family_id
        ]
