"""Server-owned immutable snapshots for reviewed understanding composition."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from backend.intelligence.family_understanding.contracts import (
    ProblemUnderstandingDraftV1,
)

_SCOPE_SUFFIX = "problem-understanding"


class UnderstandingSnapshotRejected(ValueError):
    """Fail-closed snapshot lookup with a stable reason code."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def problem_understanding_scope(*, tenant_id: str, family_id: str) -> str:
    if not tenant_id.strip() or not family_id.strip():
        raise ValueError("tenant_id and family_id are required")
    return f"family://{tenant_id}/{family_id}/{_SCOPE_SUFFIX}"


@dataclass(frozen=True, slots=True)
class ImmutableUnderstandingDraftSnapshot:
    """A server-generated draft binding; never a FamilyNeed or canonical fact."""

    understanding_run_ref: str
    tenant_id: str
    family_id: str
    scope: str
    subject_ref: str
    consent_ref: str
    artifact_hash: str
    request_hash: str
    draft_version: int
    provenance_ref: str
    prior_draft_artifact_hash: str | None
    context_snapshot_ref: str
    evidence_refs: tuple[str, ...]
    expires_at: datetime
    draft: ProblemUnderstandingDraftV1

    def __post_init__(self) -> None:
        required = (
            self.understanding_run_ref,
            self.tenant_id,
            self.family_id,
            self.scope,
            self.subject_ref,
            self.consent_ref,
            self.artifact_hash,
            self.request_hash,
            self.provenance_ref,
            self.context_snapshot_ref,
        )
        if any(not value.strip() for value in required):
            raise ValueError("immutable understanding snapshot fields cannot be blank")
        if self.scope != problem_understanding_scope(
            tenant_id=self.tenant_id, family_id=self.family_id
        ):
            raise ValueError("snapshot scope must exactly match tenant and family")
        if self.draft_version < 1:
            raise ValueError("draft_version must be positive")
        if not self.evidence_refs or any(not ref.strip() for ref in self.evidence_refs):
            raise ValueError("evidence_refs must contain non-empty server-owned references")
        if self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        if self.draft.status != "DRAFT" or self.draft.may_mutate_business_state:
            raise ValueError("snapshot may contain only a non-mutating AI draft")
        if self.draft.provenance.context_snapshot_ref != self.context_snapshot_ref:
            raise ValueError("draft provenance does not match snapshot context")

    @property
    def may_mutate_business_state(self) -> bool:
        return False


class UnderstandingDraftSnapshotStore(Protocol):
    async def put(self, snapshot: ImmutableUnderstandingDraftSnapshot) -> None: ...

    async def get(
        self, understanding_run_ref: str
    ) -> ImmutableUnderstandingDraftSnapshot | None: ...

    async def revoke(self, understanding_run_ref: str) -> None: ...

    async def is_revoked(self, understanding_run_ref: str) -> bool: ...


class InMemoryUnderstandingDraftSnapshotStore:
    """Reference adapter for tests/composition; not a production persistence claim."""

    def __init__(self) -> None:
        self._snapshots: dict[str, ImmutableUnderstandingDraftSnapshot] = {}
        self._revoked: set[str] = set()

    async def put(self, snapshot: ImmutableUnderstandingDraftSnapshot) -> None:
        current = self._snapshots.get(snapshot.understanding_run_ref)
        if current is not None and current != snapshot:
            raise UnderstandingSnapshotRejected("RUN_REF_CONFLICT")
        self._snapshots[snapshot.understanding_run_ref] = snapshot

    async def get(self, understanding_run_ref: str) -> ImmutableUnderstandingDraftSnapshot | None:
        return self._snapshots.get(understanding_run_ref)

    async def revoke(self, understanding_run_ref: str) -> None:
        self._revoked.add(understanding_run_ref)

    async def is_revoked(self, understanding_run_ref: str) -> bool:
        return understanding_run_ref in self._revoked


@dataclass(frozen=True, slots=True)
class ReadUnderstandingDraftQuery:
    understanding_run_ref: str
    tenant_id: str
    family_id: str
    scope: str
    artifact_hash: str
    draft_version: int
    provenance_ref: str


class ImmutableUnderstandingDraftReader:
    def __init__(
        self,
        store: UnderstandingDraftSnapshotStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._clock = clock or (lambda: datetime.now(UTC))

    async def read(self, query: ReadUnderstandingDraftQuery) -> ImmutableUnderstandingDraftSnapshot:
        expected_scope = problem_understanding_scope(
            tenant_id=query.tenant_id, family_id=query.family_id
        )
        if query.scope != expected_scope:
            raise UnderstandingSnapshotRejected("SCOPE_MISMATCH")
        snapshot = await self._store.get(query.understanding_run_ref)
        if snapshot is None:
            raise UnderstandingSnapshotRejected("SNAPSHOT_NOT_FOUND")
        if (
            snapshot.tenant_id != query.tenant_id
            or snapshot.family_id != query.family_id
            or snapshot.scope != query.scope
        ):
            raise UnderstandingSnapshotRejected("SCOPE_MISMATCH")
        if await self._store.is_revoked(query.understanding_run_ref):
            raise UnderstandingSnapshotRejected("SNAPSHOT_REVOKED")
        if snapshot.expires_at <= self._clock():
            raise UnderstandingSnapshotRejected("SNAPSHOT_EXPIRED")
        if (
            snapshot.artifact_hash != query.artifact_hash
            or snapshot.draft_version != query.draft_version
            or snapshot.provenance_ref != query.provenance_ref
        ):
            raise UnderstandingSnapshotRejected("BINDING_MISMATCH")
        return snapshot
