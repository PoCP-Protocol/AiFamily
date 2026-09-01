"""Immutable server-side snapshot contract for generated understanding drafts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class UnderstandingNeedCandidate:
    """Server-projected candidate; never a confirmed FamilyNeed by itself."""

    need_type: str
    required_capability_keys: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.need_type.strip():
            raise ValueError("understanding need candidate type is required")
        if not self.required_capability_keys or any(
            not value.strip() for value in self.required_capability_keys
        ):
            raise ValueError("understanding need candidate capabilities are required")
        if not self.evidence_refs or any(not value.strip() for value in self.evidence_refs):
            raise ValueError("understanding need candidate evidence is required")


@dataclass(frozen=True, slots=True)
class UnderstandingDraftSnapshot:
    tenant_id: str
    family_id: str
    understanding_run_ref: str
    artifact_ref: str
    artifact_version: int
    prior_artifact_ref: str | None
    provenance_ref: str
    subject_person_id: str
    desired_change: str
    need_type: str
    required_capability_keys: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    source_refs: tuple[str, ...]
    knowledge_refs: tuple[str, ...]
    provider_id: str
    model: str
    model_version: str
    prompt_version: str
    schema_version: str
    context_snapshot_ref: str
    expires_at: datetime
    status: Literal["DRAFT"] = "DRAFT"

    def __post_init__(self) -> None:
        required = (
            self.tenant_id,
            self.family_id,
            self.understanding_run_ref,
            self.artifact_ref,
            self.provenance_ref,
            self.subject_person_id,
            self.desired_change,
            self.need_type,
            self.provider_id,
            self.model,
            self.model_version,
            self.prompt_version,
            self.schema_version,
            self.context_snapshot_ref,
        )
        if not all(value.strip() for value in required):
            raise ValueError("understanding draft snapshot binding is incomplete")
        if self.artifact_version < 1:
            raise ValueError("understanding draft snapshot version is invalid")
        for name, values in (
            ("required_capability_keys", self.required_capability_keys),
            ("evidence_refs", self.evidence_refs),
            ("source_refs", self.source_refs),
            ("knowledge_refs", self.knowledge_refs),
        ):
            if not values or any(not value.strip() for value in values):
                raise ValueError(f"understanding draft snapshot {name} is required")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("understanding draft snapshot expiry must be timezone-aware")

    @property
    def scope_ref(self) -> str:
        return f"family://{self.tenant_id}/{self.family_id}/problem-understanding"


class UnderstandingNeedCandidateProjector(Protocol):
    async def project(
        self,
        *,
        tenant_id: str,
        family_id: str,
        subject_person_id: str,
        desired_change: str,
        source_refs: tuple[str, ...],
        knowledge_refs: tuple[str, ...],
    ) -> UnderstandingNeedCandidate: ...


class UnderstandingDraftSnapshotWriter(Protocol):
    async def save(self, snapshot: UnderstandingDraftSnapshot) -> None: ...


class UnderstandingDraftSnapshotReader(Protocol):
    async def load(
        self,
        *,
        tenant_id: str,
        family_id: str,
        artifact_ref: str,
        artifact_version: int,
        provenance_ref: str,
    ) -> UnderstandingDraftSnapshot | None: ...


__all__ = [
    "UnderstandingDraftSnapshot",
    "UnderstandingDraftSnapshotReader",
    "UnderstandingDraftSnapshotWriter",
    "UnderstandingNeedCandidate",
    "UnderstandingNeedCandidateProjector",
]
