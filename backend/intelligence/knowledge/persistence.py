"""Contract-only persistence boundary for canonical reviewed knowledge."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from backend.intelligence.knowledge.contracts import (
    KnowledgeSource,
    KnowledgeStatus,
    meets_evidence_gate,
)
from backend.packages.contracts.evidence import EvidenceLevel, Provenance

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REF = re.compile(r"^(?P<claim>[^@\s]+)@(?P<version>[^@\s]+)$")
_SHARED_SCOPE = "shared"
_TRANSITIONS: dict[KnowledgeStatus | None, frozenset[KnowledgeStatus]] = {
    None: frozenset({"INGESTED"}),
    "INGESTED": frozenset({"PARSED", "RETIRED"}),
    "PARSED": frozenset({"CHUNKED", "RETIRED"}),
    "CHUNKED": frozenset({"GROUNDED", "RETIRED"}),
    "GROUNDED": frozenset({"REVIEWED", "RETIRED"}),
    "REVIEWED": frozenset({"PUBLISHED", "RETIRED"}),
    "PUBLISHED": frozenset({"RETIRED"}),
    "RETIRED": frozenset(),
}


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
        if self.scope == "*":
            raise ValueError("claim scope must be explicit")
        if not _SHA256.fullmatch(self.content_digest) or self.content_digest != content_digest(
            self.text
        ):
            raise ValueError("content_digest must be matching lowercase sha256")
        if self.provenance.source_ref != self.source_id:
            raise ValueError("claim provenance must reference source")
        if not self.limitations or any(not item.strip() for item in self.limitations):
            raise ValueError("limitations are required")
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("expiry must include timezone")
        if self.replacement_ref is not None and not _REF.fullmatch(self.replacement_ref):
            raise ValueError("replacement_ref must use claim_id@version")
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
    scope: str
    sequence: int
    previous_status: KnowledgeStatus | None
    status: KnowledgeStatus
    occurred_at: datetime
    actor_ref: str
    expected_version: str

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (self.event_id, self.claim_id, self.version, self.scope, self.actor_ref)
        ):
            raise ValueError("lifecycle event references are required")
        if self.scope == "*":
            raise ValueError("lifecycle scope must be explicit")
        if self.sequence <= 0 or self.expected_version != self.version:
            raise ValueError("lifecycle sequence and expected version are required")
        if self.occurred_at.tzinfo is None:
            raise ValueError("lifecycle time must include timezone")


@dataclass(frozen=True, slots=True)
class KnowledgeClaimStatusProjection:
    claim_id: str
    version: str
    scope: str
    status: KnowledgeStatus
    sequence: int
    latest_event_id: str
    replacement_ref: str | None
    withdrawn: bool


@dataclass(frozen=True, slots=True)
class KnowledgeSelectionCommand:
    selection_id: str
    request_ref: str
    request_fingerprint: str
    policy_version: str
    purpose: str
    scope: str
    selected_at: datetime
    minimum_evidence: EvidenceLevel

    def __post_init__(self) -> None:
        if not self.scope.strip() or self.scope == "*":
            raise ValueError("selection scope must be explicit")
        if not _SHA256.fullmatch(self.request_fingerprint):
            raise ValueError("request_fingerprint must be lowercase sha256")
        if self.selected_at.tzinfo is None:
            raise ValueError("selection time must include timezone")


@dataclass(frozen=True, slots=True)
class KnowledgeSelectionItem:
    claim_id: str
    version: str
    content_digest: str
    provenance_locator: str
    provenance_hash: str


@dataclass(frozen=True, slots=True, init=False)
class KnowledgeSelectionReceipt:
    selection_id: str
    request_ref: str
    request_fingerprint: str
    policy_version: str
    purpose: str
    scope: str
    selected_at: datetime
    items: tuple[KnowledgeSelectionItem, ...]

    def __new__(cls, _factory_token: object | None = None):
        if _factory_token is not _RECEIPT_FACTORY_TOKEN:
            raise TypeError("selection receipts must be created by the controlled factory")
        return super().__new__(cls)


_RECEIPT_FACTORY_TOKEN = object()


class KnowledgePersistencePort(Protocol):
    def append_source(self, source: KnowledgeSource) -> None: ...
    def append_claim_version(self, claim: PersistedKnowledgeClaimVersion) -> None: ...
    def append_lifecycle_event(self, event: KnowledgeLifecycleEvent) -> None: ...
    def project_status(
        self, *, claim_id: str, version: str
    ) -> KnowledgeClaimStatusProjection | None: ...
    def append_selection_receipt(self, receipt: KnowledgeSelectionReceipt) -> None: ...
    def get_selection_receipt(
        self, *, scope: str, selection_id: str, request_fingerprint: str
    ) -> KnowledgeSelectionReceipt | None: ...


def advance_lifecycle(
    projection: KnowledgeClaimStatusProjection | None,
    event: KnowledgeLifecycleEvent,
) -> KnowledgeClaimStatusProjection:
    current = projection.status if projection else None
    expected_sequence = projection.sequence + 1 if projection else 1
    if projection is not None and (
        projection.claim_id != event.claim_id
        or projection.version != event.expected_version
        or projection.scope != event.scope
    ):
        raise ValueError("lifecycle aggregate identity/version/scope mismatch")
    if event.previous_status != current or event.sequence != expected_sequence:
        raise ValueError("lifecycle optimistic sequence mismatch")
    if event.status not in _TRANSITIONS[current]:
        raise ValueError(f"invalid lifecycle transition: {current}->{event.status}")
    return KnowledgeClaimStatusProjection(
        event.claim_id,
        event.version,
        event.scope,
        event.status,
        event.sequence,
        event.event_id,
        projection.replacement_ref if projection else None,
        event.status == "RETIRED",
    )


def validate_replacement_chain(
    claim: PersistedKnowledgeClaimVersion,
    versions: dict[str, PersistedKnowledgeClaimVersion],
    *,
    max_depth: int = 8,
) -> None:
    current = claim
    seen = {current.ref}
    for _ in range(max_depth):
        if current.replacement_ref is None:
            return
        replacement = versions.get(current.replacement_ref)
        if replacement is None or replacement.scope != claim.scope:
            raise ValueError("replacement must exist in the same scope")
        if replacement.ref in seen:
            raise ValueError("replacement chain contains a cycle")
        seen.add(replacement.ref)
        current = replacement
    raise ValueError("replacement chain exceeds maximum depth")


def create_selection_receipt(
    command: KnowledgeSelectionCommand,
    candidates: tuple[
        tuple[PersistedKnowledgeClaimVersion, KnowledgeClaimStatusProjection, KnowledgeSource], ...
    ],
) -> KnowledgeSelectionReceipt:
    items = []
    for claim, projection, source in candidates:
        if (claim.claim_id, claim.version) != (
            projection.claim_id,
            projection.version,
        ) or projection.scope != claim.scope:
            raise ValueError("claim and projection identity/version/scope mismatch")
        if projection.status != "PUBLISHED" or projection.withdrawn:
            raise ValueError("only published claims may be selected")
        if source.status != "ACTIVE" or not source.verified or not source.license_ref.strip():
            raise ValueError("source is not selectable")
        if claim.source_id != source.source_id or claim.scope not in {
            command.scope,
            _SHARED_SCOPE,
        }:
            raise ValueError("claim source or scope mismatch")
        if claim.allowed_purposes and command.purpose not in claim.allowed_purposes:
            raise ValueError("claim purpose mismatch")
        if claim.expires_at is not None and claim.expires_at <= command.selected_at:
            raise ValueError("expired claim cannot be selected")
        if not meets_evidence_gate(claim.provenance.level, command.minimum_evidence):
            raise ValueError("claim does not meet evidence gate")
        locator = f"{claim.source_id}:{claim.claim_id}@{claim.version}"
        items.append(
            KnowledgeSelectionItem(
                claim.claim_id,
                claim.version,
                claim.content_digest,
                locator,
                content_digest(locator),
            )
        )
    receipt = object.__new__(KnowledgeSelectionReceipt)
    for name, value in (
        ("selection_id", command.selection_id),
        ("request_ref", command.request_ref),
        ("request_fingerprint", command.request_fingerprint),
        ("policy_version", command.policy_version),
        ("purpose", command.purpose),
        ("scope", command.scope),
        ("selected_at", command.selected_at),
        ("items", tuple(items)),
    ):
        object.__setattr__(receipt, name, value)
    return receipt


def content_digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


__all__ = [
    "KnowledgeClaimStatusProjection",
    "KnowledgeLifecycleEvent",
    "KnowledgePersistencePort",
    "KnowledgeSelectionCommand",
    "KnowledgeSelectionReceipt",
    "PersistedKnowledgeClaimVersion",
    "advance_lifecycle",
    "content_digest",
    "create_selection_receipt",
    "validate_replacement_chain",
]
