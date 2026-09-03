"""Persistence DTO and port for the canonical reviewed-knowledge registry.

K1 is contract-only. It defines no database table, migration, engine, or
``create_all`` path. A K2 adapter must implement this port after Data approval.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from backend.intelligence.knowledge.contracts import (
    KnowledgeSource,
    KnowledgeStatus,
)
from backend.packages.contracts.evidence import Provenance

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class PersistedKnowledgeClaimVersion:
    claim_id: str
    version: str
    content_digest: str
    text: str
    source_id: str
    provenance: Provenance
    scope: str
    allowed_purposes: tuple[str, ...]
    applicability: str
    limitations: tuple[str, ...]
    expires_at: datetime | None = None
    replacement_ref: str | None = None

    def __post_init__(self) -> None:
        required = (
            self.claim_id,
            self.version,
            self.text,
            self.source_id,
            self.scope,
            self.applicability,
        )
        if any(not value.strip() for value in required):
            raise ValueError("claim version fields must be non-empty")
        if not _SHA256.fullmatch(self.content_digest):
            raise ValueError("content_digest must be lowercase sha256 hex")
        if self.content_digest != content_digest(self.text):
            raise ValueError("content_digest does not match canonical text")
        if self.provenance.source_ref != self.source_id:
            raise ValueError("claim version provenance must reference its source")
        if not self.limitations or any(not item.strip() for item in self.limitations):
            raise ValueError("claim version limitations are required")
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("claim version expiry must include timezone")
        if self.replacement_ref == self.ref:
            raise ValueError("claim version cannot replace itself")

    @property
    def ref(self) -> str:
        return f"{self.claim_id}@{self.version}"


@dataclass(frozen=True, slots=True)
class KnowledgeLifecycleEvent:
    event_id: str
    claim_id: str
    version: str
    status: KnowledgeStatus
    occurred_at: datetime
    actor_ref: str
    reason_ref: str | None = None

    def __post_init__(self) -> None:
        required = (self.event_id, self.claim_id, self.version, self.actor_ref)
        if any(not value.strip() for value in required):
            raise ValueError("lifecycle event references are required")
        if self.occurred_at.tzinfo is None:
            raise ValueError("lifecycle event time must include timezone")


@dataclass(frozen=True, slots=True)
class KnowledgeSelectionItem:
    claim_id: str
    version: str
    content_digest: str
    provenance_ref: str
    status_at_selection: KnowledgeStatus
    replacement_ref: str | None = None

    def __post_init__(self) -> None:
        if not _SHA256.fullmatch(self.content_digest):
            raise ValueError("selection item digest must be lowercase sha256 hex")
        if any(not value.strip() for value in (self.claim_id, self.version, self.provenance_ref)):
            raise ValueError("selection item references are required")
        if self.status_at_selection != "PUBLISHED":
            raise ValueError("only a published claim version may enter a selection")


@dataclass(frozen=True, slots=True)
class KnowledgeSelectionReceipt:
    selection_id: str
    request_ref: str
    purpose: str
    scope: str
    selected_at: datetime
    items: tuple[KnowledgeSelectionItem, ...]

    def __post_init__(self) -> None:
        required = (self.selection_id, self.request_ref, self.purpose, self.scope)
        if any(not value.strip() for value in required):
            raise ValueError("selection receipt references are required")
        if self.selected_at.tzinfo is None:
            raise ValueError("selection receipt time must include timezone")
        keys = tuple((item.claim_id, item.version) for item in self.items)
        if len(keys) != len(set(keys)):
            raise ValueError("selection receipt cannot repeat a claim version")


@dataclass(frozen=True, slots=True)
class KnowledgeClaimStatusProjection:
    claim_id: str
    version: str
    status: KnowledgeStatus
    latest_event_id: str
    replacement_ref: str | None
    withdrawn: bool


class KnowledgePersistencePort(Protocol):
    """Single canonical persistence boundary to be implemented by K2."""

    def append_source(self, source: KnowledgeSource) -> None: ...

    def append_claim_version(self, claim: PersistedKnowledgeClaimVersion) -> None: ...

    def append_lifecycle_event(self, event: KnowledgeLifecycleEvent) -> None: ...

    def project_status(
        self, *, claim_id: str, version: str
    ) -> KnowledgeClaimStatusProjection | None: ...

    def append_selection_receipt(self, receipt: KnowledgeSelectionReceipt) -> None: ...

    def retrieve_published(
        self,
        *,
        purpose: str,
        scope: str,
        at: datetime,
    ) -> tuple[PersistedKnowledgeClaimVersion, ...]: ...

    def get_selection_receipt(self, selection_id: str) -> KnowledgeSelectionReceipt | None: ...


def content_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def selection_item(
    claim: PersistedKnowledgeClaimVersion,
    projection: KnowledgeClaimStatusProjection,
) -> KnowledgeSelectionItem:
    if (claim.claim_id, claim.version) != (projection.claim_id, projection.version):
        raise ValueError("selection projection does not match claim version")
    if projection.status != "PUBLISHED" or projection.withdrawn:
        raise ValueError("withdrawn or unpublished claim cannot enter a selection")
    return KnowledgeSelectionItem(
        claim_id=claim.claim_id,
        version=claim.version,
        content_digest=claim.content_digest,
        provenance_ref=claim.provenance.source_ref,
        status_at_selection="PUBLISHED",
        replacement_ref=projection.replacement_ref,
    )


__all__ = [
    "KnowledgeClaimStatusProjection",
    "KnowledgeLifecycleEvent",
    "KnowledgePersistencePort",
    "KnowledgeSelectionItem",
    "KnowledgeSelectionReceipt",
    "PersistedKnowledgeClaimVersion",
    "content_digest",
    "selection_item",
]
