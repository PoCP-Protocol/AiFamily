"""Shared contracts for reviewed knowledge used by the AI runtime.

The evidence vocabulary remains owned by ``backend.packages.contracts.evidence``.
This module adds the knowledge-specific lifecycle and source boundary around that
vocabulary; it does not create a second evidence scale.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from backend.packages.contracts.evidence import (
    NON_ESTABLISHING_LEVELS,
    EvidenceLevel,
    Provenance,
)

KnowledgeStatus = Literal[
    "INGESTED",
    "PARSED",
    "CHUNKED",
    "GROUNDED",
    "REVIEWED",
    "PUBLISHED",
    "RETIRED",
]
SourceStatus = Literal["ACTIVE", "RETIRED"]

_EVIDENCE_RANK: dict[str, int] = {f"E{i}": i for i in range(8)}


def evidence_rank(level: EvidenceLevel) -> int:
    """Return the shared E0-E7 ordering, or -1 for non-establishing sources."""

    if level in NON_ESTABLISHING_LEVELS:
        return -1
    return _EVIDENCE_RANK[level]


def meets_evidence_gate(level: EvidenceLevel, minimum: EvidenceLevel) -> bool:
    """Check an evidence gate without treating inferred data as evidence."""

    current_rank = evidence_rank(level)
    return current_rank >= 0 and current_rank >= evidence_rank(minimum)


@dataclass(frozen=True, slots=True)
class KnowledgeSource:
    """A registered, shared source boundary.

    Verification is deliberately explicit.  An unverified source may be
    ingested for review, but it cannot be published or retrieved by the runtime.
    """

    source_id: str
    title: str
    license_ref: str
    owner: str
    scope: str
    verified: bool = False
    status: SourceStatus = "ACTIVE"

    def __post_init__(self) -> None:
        missing = [
            name
            for name, value in (
                ("source_id", self.source_id),
                ("title", self.title),
                ("license_ref", self.license_ref),
                ("owner", self.owner),
                ("scope", self.scope),
            )
            if not value.strip()
        ]
        if missing:
            raise ValueError(f"KnowledgeSource is missing required field(s): {missing}")


@dataclass(frozen=True, slots=True)
class KnowledgeClaim:
    """A non-private claim that can be reviewed and published independently."""

    claim_id: str
    text: str
    source_id: str
    provenance: Provenance
    scope: str
    status: KnowledgeStatus = "INGESTED"
    allowed_purposes: tuple[str, ...] = ()
    expires_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    visibility: Literal["SHARED"] = "SHARED"

    def __post_init__(self) -> None:
        missing = [
            name
            for name, value in (
                ("claim_id", self.claim_id),
                ("text", self.text),
                ("source_id", self.source_id),
                ("scope", self.scope),
            )
            if not value.strip()
        ]
        if missing:
            raise ValueError(f"KnowledgeClaim is missing required field(s): {missing}")
        if self.visibility != "SHARED":
            raise ValueError("FAMILY_PRIVATE knowledge cannot enter the shared registry")
        if self.provenance.source_ref != self.source_id:
            raise ValueError("KnowledgeClaim provenance.source_ref must equal source_id")
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("KnowledgeClaim.expires_at must include a timezone")

    @property
    def supports_establishing_claim(self) -> bool:
        """Whether this claim may support an establishing conclusion.

        E0 is a registered baseline but is intentionally non-establishing; the
        same applies to inferred, simulated, unverified and unknown provenance.
        """

        return evidence_rank(self.provenance.level) >= 1

    def is_expired(self, *, at: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        moment = at or datetime.now(UTC)
        if moment.tzinfo is None:
            raise ValueError("KnowledgeClaim expiry comparison requires a timezone")
        return self.expires_at <= moment
