"""Family World State Kernel (AIFAMILY-FIC-002A).

Semantic contracts for "based on current evidence, how do we understand this
family" — deliberately distinct from the Truth Plane (authoritative business
domains own "what happened") and from Memory (what was said/observed in the
past, replayable as-is). See `docs/00_system/AIFAMILY_STRATEGIC_CONSTITUTION_V1.md`
§4 and `ADR-0169` §4 for the strategic mandate this module implements.

Non-goals for this kernel (intentionally deferred, see ADR-0171 Enforcement):
graph database, temporal query engine, LLM provider calls, a Goal Engine, a
Planner, or any rewrite of Family/FamilyNeed/Assessment/Action/Outcome/
GrowthGraph/Memory. This module only defines the semantic contracts; nothing
here writes to an authoritative domain.

Core invariant enforced throughout: an atom's `epistemic_kind` is immutable
once constructed (frozen dataclass). There is no method anywhere in this
module that changes a HYPOTHESIS/PERSPECTIVE atom into a FACT atom — "becoming
a fact" requires a brand-new FACT atom, and `promote_proposal_to_atom` refuses
to mint one when the asserting actor is AI. This is what makes "HYPOTHESIS
cannot silently become FACT" a structural property, not a policy someone has
to remember to check.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .contracts import ContextContractError, ContextScope, ContextScopeError


class WorldStateEpistemicKind(StrEnum):
    """What kind of claim a `WorldStateAtom` actually is.

    Deliberately a separate vocabulary from `family_need.domain.value_objects
    .EpistemicStatus`: that enum lives in the FamilyNeed bounded context (whose
    own docstring says it is "deliberately independent from AI/runtime"); this
    one lives in the AI/runtime context_engine boundary. The two contexts are
    allowed to converge later via an explicit ADR-backed mapping, but this
    kernel must not reach into FamilyNeed's domain module to avoid coupling
    two bounded contexts that were designed to stay independent.
    """

    FACT = "FACT"
    OBSERVATION = "OBSERVATION"
    SELF_REPORT = "SELF_REPORT"
    OTHER_REPORT = "OTHER_REPORT"
    PERSPECTIVE = "PERSPECTIVE"
    HYPOTHESIS = "HYPOTHESIS"
    UNKNOWN = "UNKNOWN"


#: Kinds that only an authoritative domain / a real person can assert.
#: An AI actor is never the `attributed_actor_type` for these kinds.
_NON_AI_ASSERTABLE_KINDS = frozenset(
    {
        WorldStateEpistemicKind.FACT,
        WorldStateEpistemicKind.OBSERVATION,
        WorldStateEpistemicKind.SELF_REPORT,
        WorldStateEpistemicKind.OTHER_REPORT,
    }
)

#: Kinds that require at least one evidence or source reference, because they
#: are derived rather than directly reported.
_DERIVED_KINDS = frozenset(
    {WorldStateEpistemicKind.HYPOTHESIS, WorldStateEpistemicKind.PERSPECTIVE}
)


class WorldStateAtomStatus(StrEnum):
    """Lifecycle of an atom. Append-oriented: status never rewrites content."""

    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    RETRACTED = "RETRACTED"


class WorldStateActorType(StrEnum):
    """Who is asserting a `WorldStateAtom` or authoring a `WorldStateProposal`."""

    FAMILY_MEMBER = "FAMILY_MEMBER"
    FAMILY_GUARDIAN = "FAMILY_GUARDIAN"
    PROFESSIONAL = "PROFESSIONAL"
    SYSTEM = "SYSTEM"
    AI = "AI"


class UnknownStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"
    STALE = "STALE"


class BeliefBand(StrEnum):
    """Three-tier categorical belief signal (AIFAMILY-WM-004B).

    Deliberately not a float probability: V1 has no calibration data to back
    a number like "support=0.73" — that would be fake precision. A model
    asked for a float will produce one regardless of whether it means
    anything; asked for one of four bands, it cannot manufacture false
    precision it doesn't have.
    """

    NONE = "NONE"
    WEAK = "WEAK"
    MODERATE = "MODERATE"
    STRONG = "STRONG"


class UncertaintyBand(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


def _require_text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContextContractError(f"{name}_required")


def _require_aware(name: str, value: datetime) -> None:
    if value.tzinfo is None:
        raise ContextContractError(f"{name}_requires_timezone")


@dataclass(frozen=True, slots=True)
class WorldStateAtom:
    """A single, immutable unit of "how we currently understand this family".

    Construction alone enforces the FIC-002A invariants that do not depend on
    who is asking for promotion (see `promote_proposal_to_atom` for the
    AI-cannot-assert-FACT check, which needs the actor type at the call site).
    """

    atom_id: str
    scope: ContextScope
    subject_ids: tuple[str, ...]
    epistemic_kind: WorldStateEpistemicKind
    predicate: str
    value_ref: str
    asserted_by: str
    attributed_actor_type: WorldStateActorType
    provenance: str
    observed_at: datetime
    recorded_at: datetime
    valid_from: datetime
    valid_until: datetime | None = None
    source_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    status: WorldStateAtomStatus = WorldStateAtomStatus.ACTIVE
    supersedes: str | None = None
    #: AIFAMILY-WM-004B.1 — belief metadata. REQUIRED (non-None) when
    #: `epistemic_kind is HYPOTHESIS`; left `None` ("not applicable", never
    #: a fabricated NONE/LOW default) for every other kind. Losing these on
    #: promotion was the exact gap this freeze closes: a HYPOTHESIS atom
    #: with no support/contradiction/uncertainty on it is indistinguishable
    #: from a FACT to anything reading the Atom Store later.
    support_level: BeliefBand | None = None
    contradiction_level: BeliefBand | None = None
    uncertainty: UncertaintyBand | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("atom_id", self.atom_id),
            ("predicate", self.predicate),
            ("value_ref", self.value_ref),
            ("asserted_by", self.asserted_by),
            ("provenance", self.provenance),
        ):
            _require_text(name, value)
        if not isinstance(self.subject_ids, tuple) or not self.subject_ids:
            raise ContextContractError("subject_ids must be a non-empty tuple")
        if any(sid not in self.scope.subject_ids for sid in self.subject_ids):
            raise ContextScopeError("WORLD_STATE_SUBJECT_OUT_OF_SCOPE")
        if self.epistemic_kind is WorldStateEpistemicKind.HYPOTHESIS and (
            self.support_level is None
            or self.contradiction_level is None
            or self.uncertainty is None
        ):
            raise ContextContractError("HYPOTHESIS_REQUIRES_BELIEF_METADATA")
        for name, value in (
            ("observed_at", self.observed_at),
            ("recorded_at", self.recorded_at),
            ("valid_from", self.valid_from),
        ):
            _require_aware(name, value)
        if self.valid_until is not None:
            _require_aware("valid_until", self.valid_until)
            if self.valid_until <= self.valid_from:
                raise ContextContractError("valid_until must follow valid_from")
        if (
            self.attributed_actor_type is WorldStateActorType.AI
            and self.epistemic_kind in _NON_AI_ASSERTABLE_KINDS
        ):
            raise ContextContractError("AI_CANNOT_ASSERT_THIS_EPISTEMIC_KIND")
        if self.epistemic_kind in _DERIVED_KINDS and not (self.source_refs or self.evidence_refs):
            raise ContextContractError("DERIVED_STATE_REQUIRES_EVIDENCE")

    def assert_readable_by(self, scope: ContextScope) -> None:
        """Fail closed before an atom can appear in a snapshot or a proposal."""

        scope.assert_active()
        if self.scope.tenant_id != scope.tenant_id:
            raise ContextScopeError("CROSS_TENANT_WORLD_STATE_READ")
        if self.scope.family_id != scope.family_id:
            raise ContextScopeError("CROSS_FAMILY_WORLD_STATE_READ")
        if not set(self.subject_ids).issubset(set(scope.subject_ids)):
            raise ContextScopeError("WORLD_STATE_SUBJECT_READ_DENIED")
        if self.scope.purpose != scope.purpose:
            raise ContextContractError("WORLD_STATE_PURPOSE_MISMATCH")
        if self.scope.consent_version != scope.consent_version:
            raise ContextContractError("WORLD_STATE_CONSENT_VERSION_MISMATCH")
        if not scope.consent_granted:
            raise ContextContractError("CONSENT_REVOKED")


@dataclass(frozen=True, slots=True)
class UnknownState:
    """A first-class "we don't know this yet" object — never null/false.

    An Unknown is data, not the absence of data: it carries why it matters and
    what would resolve it, so a caller can act on ignorance instead of
    silently treating a missing field as "no" or "not applicable".
    """

    unknown_id: str
    scope: ContextScope
    subject_ids: tuple[str, ...]
    question: str
    why_it_matters: str
    source_refs: tuple[str, ...] = ()
    blocking_ref: str | None = None
    priority: str = "NORMAL"
    status: UnknownStatus = UnknownStatus.OPEN
    resolution_refs: tuple[str, ...] = ()
    created_at: datetime | None = None
    resolved_at: datetime | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("unknown_id", self.unknown_id),
            ("question", self.question),
            ("why_it_matters", self.why_it_matters),
        ):
            _require_text(name, value)
        if not isinstance(self.subject_ids, tuple) or not self.subject_ids:
            raise ContextContractError("subject_ids must be a non-empty tuple")
        if any(sid not in self.scope.subject_ids for sid in self.subject_ids):
            raise ContextScopeError("WORLD_STATE_SUBJECT_OUT_OF_SCOPE")
        if self.status is UnknownStatus.RESOLVED and not self.resolution_refs:
            raise ContextContractError("RESOLVED_UNKNOWN_REQUIRES_RESOLUTION_REFS")


@dataclass(frozen=True, slots=True)
class WorldStateProposal:
    """An AI-authored candidate atom that has not been admitted yet.

    A proposal can never carry `FACT`, `OBSERVATION`, `SELF_REPORT` or
    `OTHER_REPORT` — those require a real reporting actor, not a model. This
    is checked at construction, not only at promotion time, so an invalid
    proposal cannot exist even transiently.
    """

    proposal_id: str
    scope: ContextScope
    subject_ids: tuple[str, ...]
    proposed_kind: WorldStateEpistemicKind
    #: AIFAMILY-WM-004B.1 — the predicate this proposal is *about*, supplied
    #: by the caller (never invented by the model). Governance (is this
    #: predicate actually registered?) is enforced at the persistence
    #: boundary by `PredicateRegistry`, same as every other predicate in
    #: this kernel — see `predicate_registry.py`'s module docstring.
    target_predicate: str
    statement: str
    evidence_refs: tuple[str, ...]
    confidence: float
    proposed_by: str = "AI"
    requires_confirmation: bool = True
    missing_evidence: tuple[str, ...] = ()
    support_level: BeliefBand = BeliefBand.NONE
    contradiction_level: BeliefBand = BeliefBand.NONE
    uncertainty: UncertaintyBand = UncertaintyBand.HIGH

    def __post_init__(self) -> None:
        _require_text("target_predicate", self.target_predicate)
        _require_text("statement", self.statement)
        if self.proposed_kind in _NON_AI_ASSERTABLE_KINDS:
            raise ContextContractError("AI_PROPOSAL_CANNOT_TARGET_THIS_KIND")
        if not 0.0 <= self.confidence <= 1.0:
            raise ContextContractError("confidence must be within [0.0, 1.0]")
        if self.proposed_kind in _DERIVED_KINDS and not self.evidence_refs:
            raise ContextContractError("DERIVED_PROPOSAL_REQUIRES_EVIDENCE")


def promote_proposal_to_atom(
    proposal: WorldStateProposal,
    *,
    atom_id: str,
    provenance: str,
    observed_at: datetime,
    recorded_at: datetime,
    valid_from: datetime,
    valid_until: datetime | None = None,
    supersedes: str | None = None,
) -> WorldStateAtom:
    """Turn a validated AI proposal into an atom — the only legal path from
    "AI suggested this" to "this is now part of the world state".

    Never called with `attributed_actor_type=AI` and a FACT-family kind: the
    proposal's own `__post_init__` already rejected that combination, and this
    function does not accept an override, so there is no call site anywhere
    that can smuggle an AI-asserted FACT past this kernel.
    """

    is_hypothesis = proposal.proposed_kind is WorldStateEpistemicKind.HYPOTHESIS
    return WorldStateAtom(
        atom_id=atom_id,
        scope=proposal.scope,
        subject_ids=proposal.subject_ids,
        epistemic_kind=proposal.proposed_kind,
        predicate=proposal.target_predicate,
        value_ref=proposal.statement,
        asserted_by=proposal.proposed_by,
        attributed_actor_type=WorldStateActorType.AI,
        provenance=provenance,
        observed_at=observed_at,
        recorded_at=recorded_at,
        valid_from=valid_from,
        valid_until=valid_until,
        source_refs=proposal.evidence_refs,
        evidence_refs=proposal.evidence_refs,
        supersedes=supersedes,
        # AIFAMILY-WM-004B.1: belief metadata only travels onto the atom for
        # HYPOTHESIS — other AI-proposable kinds (UNKNOWN etc.) leave these
        # None rather than carrying meaningless NONE/HIGH defaults forward.
        support_level=proposal.support_level if is_hypothesis else None,
        contradiction_level=proposal.contradiction_level if is_hypothesis else None,
        uncertainty=proposal.uncertainty if is_hypothesis else None,
    )


@dataclass(frozen=True, slots=True)
class FamilyWorldStateSnapshot:
    """ "As of this moment, given current evidence and scope, this is what we
    understand about this family" — bounded, scope-checked, rebuildable.

    Deliberately holds refs and bounded atoms/unknowns, never raw transcripts,
    media, or full conversation history (see constitution §4/§9 on Memory
    separation) — this mirrors `ContextSnapshot`'s existing discipline.
    """

    snapshot_ref: str
    scope: ContextScope
    as_of: datetime
    generated_at: datetime
    atoms: tuple[WorldStateAtom, ...] = ()
    unknowns: tuple[UnknownState, ...] = ()
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text("snapshot_ref", self.snapshot_ref)
        _require_aware("as_of", self.as_of)
        _require_aware("generated_at", self.generated_at)
        for atom in self.atoms:
            atom.assert_readable_by(self.scope)
        for unknown in self.unknowns:
            if unknown.scope.tenant_id != self.scope.tenant_id:
                raise ContextScopeError("CROSS_TENANT_WORLD_STATE_READ")
            if unknown.scope.family_id != self.scope.family_id:
                raise ContextScopeError("CROSS_FAMILY_WORLD_STATE_READ")
        if not self.source_refs:
            refs: list[str] = []
            for atom in self.atoms:
                refs.extend(atom.evidence_refs)
                refs.extend(atom.source_refs)
            for unknown in self.unknowns:
                refs.extend(unknown.source_refs)
            object.__setattr__(self, "source_refs", tuple(dict.fromkeys(refs)))


__all__ = [
    "BeliefBand",
    "FamilyWorldStateSnapshot",
    "UncertaintyBand",
    "UnknownState",
    "UnknownStatus",
    "WorldStateActorType",
    "WorldStateAtom",
    "WorldStateAtomStatus",
    "WorldStateEpistemicKind",
    "WorldStateProposal",
    "promote_proposal_to_atom",
]
