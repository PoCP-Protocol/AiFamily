"""Provider-neutral contracts for the first AGI-native path slice.

The objects here are projections and drafts only.  They intentionally have no
repository or mutation method: selecting a path cannot itself create a family
fact, action, booking, or commercial consequence.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol

from backend.intelligence.context_engine.contracts import ContextScope

PathDraftStatus = Literal["DRAFT"]


class PathDraftError(ValueError):
    """Base error for invalid path drafting inputs."""


class PathDraftScopeError(PathDraftError):
    """Raised when a projection crosses its trusted family scope."""


@dataclass(frozen=True, slots=True)
class PathDraftEvidence:
    """A source reference explaining why a draft node was selected."""

    ref: str
    kind: str
    version: str
    excerpt: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (self.ref, self.kind, self.version, self.excerpt)
        ):
            raise PathDraftError("path draft evidence fields are required")


@dataclass(frozen=True, slots=True)
class FamilyPathContext:
    """Read-only, family-scoped context supplied by a canonical evidence port."""

    tenant_id: str
    family_id: str
    need_id: str
    need_statement: str
    subject_ids: tuple[str, ...]
    context_snapshot_ref: str
    evidence: tuple[PathDraftEvidence, ...]
    fit_tags: frozenset[str] = field(default_factory=frozenset)
    unknowns: tuple[str, ...] = ()
    feedback_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        required = (
            self.tenant_id,
            self.family_id,
            self.need_id,
            self.need_statement,
            self.context_snapshot_ref,
        )
        if not all(isinstance(value, str) and value.strip() for value in required):
            raise PathDraftError("family path context identity is required")
        if not self.subject_ids or any(not value.strip() for value in self.subject_ids):
            raise PathDraftError("family path context subjects are required")
        if not self.evidence:
            raise PathDraftError("family path context evidence is required")
        if any(not tag.strip() for tag in self.fit_tags):
            raise PathDraftError("family path context fit tags cannot be blank")


@dataclass(frozen=True, slots=True)
class CapabilityCandidate:
    """A reviewed capability that an agent may place in a path draft."""

    capability_ref: str
    title: str
    description: str
    fit_tags: frozenset[str]
    evidence: tuple[PathDraftEvidence, ...]
    prerequisite_tags: frozenset[str] = field(default_factory=frozenset)
    estimated_minutes: int = 0

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (self.capability_ref, self.title, self.description)
        ):
            raise PathDraftError("capability candidate identity and description are required")
        if not self.evidence:
            raise PathDraftError("capability candidate evidence is required")
        if self.estimated_minutes < 0:
            raise PathDraftError("capability candidate effort cannot be negative")


@dataclass(frozen=True, slots=True)
class PathDraft:
    """A versioned, explainable route proposal; never a business fact."""

    draft_id: str
    version: int
    tenant_id: str
    family_id: str
    need_id: str
    context_snapshot_ref: str
    nodes: tuple[CapabilityCandidate, ...]
    selected_reasons: Mapping[str, tuple[str, ...]]
    clarifying_questions: tuple[str, ...]
    feedback_refs: tuple[str, ...]
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: PathDraftStatus = "DRAFT"

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (
                self.draft_id,
                self.tenant_id,
                self.family_id,
                self.need_id,
                self.context_snapshot_ref,
            )
        ):
            raise PathDraftError("path draft identity is required")
        if self.version < 1 or self.status != "DRAFT":
            raise PathDraftError("path drafts must remain versioned DRAFTs")
        if self.generated_at.tzinfo is None:
            raise PathDraftError("path draft timestamp must be timezone-aware")
        if len({node.capability_ref for node in self.nodes}) != len(self.nodes):
            raise PathDraftError("path draft capability refs must be unique")
        if set(self.selected_reasons) != {node.capability_ref for node in self.nodes}:
            raise PathDraftError("path draft reasons must cover every selected node")

    @property
    def may_mutate_business_state(self) -> bool:
        return False


class FamilyPathContextPort(Protocol):
    """Canonical read-only source for one family need's evidence projection."""

    async def read(self, *, scope: ContextScope, need_id: str) -> FamilyPathContext: ...


class CapabilityCandidatePort(Protocol):
    """Read-only catalogue of reviewed capability candidates."""

    async def list_candidates(
        self, *, scope: ContextScope, context: FamilyPathContext
    ) -> tuple[CapabilityCandidate, ...]: ...


__all__ = [
    "CapabilityCandidate",
    "CapabilityCandidatePort",
    "FamilyPathContext",
    "FamilyPathContextPort",
    "PathDraft",
    "PathDraftEvidence",
    "PathDraftError",
    "PathDraftScopeError",
]
