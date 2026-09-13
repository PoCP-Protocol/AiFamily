"""Provider-neutral contracts for the first AGI-native path slice.

The objects here are projections and drafts only.  They intentionally have no
repository or mutation method: selecting a path cannot itself create a family
fact, action, booking, or commercial consequence.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol, runtime_checkable

from backend.intelligence.context_engine.contracts import ContextScope

PathDraftStatus = Literal["DRAFT"]


class PathDraftError(ValueError):
    """Base error for invalid path drafting inputs."""


class PathDraftScopeError(PathDraftError):
    """Raised when a projection crosses its trusted family scope."""


@dataclass(frozen=True, slots=True)
class PathFeedbackSignal:
    """Structured guardian correction consumed by the next draft."""

    feedback_ref: str
    decision: Literal["REJECT", "PREFER", "CLARIFY"]
    reason: str
    excluded_capability_refs: tuple[str, ...] = ()
    preferred_fit_tags: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.feedback_ref.strip() or not self.reason.strip():
            raise PathDraftError("path feedback ref and reason are required")
        if any(not ref.strip() for ref in self.excluded_capability_refs):
            raise PathDraftError("path feedback excluded refs cannot be blank")
        if any(not tag.strip() for tag in self.preferred_fit_tags):
            raise PathDraftError("path feedback preferred tags cannot be blank")


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
    feedback_signals: tuple[PathFeedbackSignal, ...] = ()

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
    feedback_signals: tuple[PathFeedbackSignal, ...] = ()
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
    """Read-only catalogue of reviewed capability candidates.

    Production implementations must derive the returned candidates from a
    registered knowledge/capability source and must genuinely use `context`
    to vary what is returned across families.  An implementation that
    discards `context` (or `scope`) and returns a fixed pool regardless of
    the family's real evidence is a development-only placeholder, not a
    real capability source — it must say so explicitly in its own docstring
    and must not be described as "context-driven" in any composition-root
    wiring or ADR evidence entry.  See ADR-0158's "零模型调用" discussion
    thread for why this distinction matters: a fixed candidate pool with a
    scoring function on top is still a disguised if/else table, not an
    AGI-native capability.
    """

    async def list_candidates(
        self, *, scope: ContextScope, context: FamilyPathContext
    ) -> tuple[CapabilityCandidate, ...]: ...


@runtime_checkable
class PathDraftPersistencePort(Protocol):
    """Durable seam for idempotent path draft version storage.

    A deterministic ``draft_id`` (same tenant/family/need/context_snapshot_ref
    and same selected capability refs always hash to the same id) proves that
    the *planner's computation* is idempotent, but it does not by itself prove
    that a draft survives a process restart, that a caller re-requesting the
    same need+snapshot gets back the exact same persisted row (not a fresh
    in-memory recomputation that merely happens to collide on id), or that the
    model version, evidence lineage, and feedback lineage that produced a
    draft remain retrievable later.  This port is the adapter seam that closes
    that gap; it deliberately says nothing about *how* drafts are stored
    (SQL table, event store, etc.) — only the contract an adapter must honor.

    Implementations MUST satisfy:
      * ``get_or_create`` is idempotent by ``(tenant_id, family_id, need_id,
        context_snapshot_ref, draft_id)``: calling it twice with an
        equal draft returns the same persisted version both times and does
        not create a second row.
      * The returned ``PathDraft`` is the one already durably stored when one
        exists for that key, not a re-derived value — callers must be able to
        trust the returned ``version`` and ``generated_at`` as the original
        write's values, not the second call's inputs.
      * A new ``context_snapshot_ref`` for the same ``need_id`` is a new
        logical draft lineage; it never silently overwrites a prior version,
        and querying by ``need_id`` alone must be able to return history
        (``get_versions``) across snapshot changes.
      * Storage is scoped to the same tenant/family boundary already enforced
        by ``FamilyPathContextPort`` — this port trusts its caller to pass a
        draft that has already passed scope validation; it does not
        re-derive or re-check scope itself.
    """

    async def get_or_create(self, draft: PathDraft) -> PathDraft: ...

    async def get_latest(
        self, *, tenant_id: str, family_id: str, need_id: str
    ) -> PathDraft | None: ...

    async def get_versions(
        self, *, tenant_id: str, family_id: str, need_id: str
    ) -> tuple[PathDraft, ...]: ...


__all__ = [
    "CapabilityCandidate",
    "CapabilityCandidatePort",
    "FamilyPathContext",
    "FamilyPathContextPort",
    "PathDraft",
    "PathDraftEvidence",
    "PathDraftPersistencePort",
    "PathFeedbackSignal",
    "PathDraftError",
    "PathDraftScopeError",
]
