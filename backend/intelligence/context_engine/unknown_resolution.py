"""Unknown Resolution Evidence Gate (AIFAMILY-WM-004C.1).

Closes a real gap: `PostgresUnknownRepository.resolve()` previously only
checked that `resolution_refs` was non-empty and not a subset of the
Unknown's own `blocking_refs` — it never checked that those refs pointed to
anything real. A caller could resolve an Unknown with an arbitrary string
that had never been through any Truth/Observation adapter, letting "I don't
know" silently become "I now know" without any actual new information ever
entering the World State. That is the exact failure mode this kernel exists
to prevent.

From this module forward, `UnknownState.resolution_refs` means *only*:

    an existing, durable WorldStateAtom.atom_id

External information (an assessment result, a family's spoken answer, a
device observation) must first be projected into a `WorldStateAtom` by a
governed Observation/Truth adapter — this module never accepts a raw
string as evidence, only an `atom_id` it can look up and verify.

`resolve_unknown()` is the only path that may transition an Unknown from
OPEN to RESOLVED; `PostgresUnknownRepository.mark_resolved()` (the
persistence primitive it calls) is deliberately policy-free and must never
be called directly with unvalidated refs from application code.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from .contracts import ContextContractError, ContextScope
from .world_state import UnknownState, WorldStateActorType, WorldStateAtom, WorldStateEpistemicKind


class _UnknownReaderWriter(Protocol):
    """Structural interface, not `PostgresUnknownRepository` — code under
    `backend/intelligence/` must not import a concrete Repository symbol
    (`tests/architecture/test_ai_runtime_isolation.py`), even one that is
    this same package's own persistence adapter rather than a business
    domain's. Any object satisfying this shape (in practice,
    `PostgresUnknownRepository`, supplied by the caller) works."""

    async def get(self, unknown_id: str, *, scope: ContextScope) -> UnknownState | None: ...

    async def mark_resolved(
        self,
        unknown_id: str,
        *,
        scope: ContextScope,
        resolution_refs: tuple[str, ...],
        resolved_at: datetime,
    ) -> UnknownState: ...


class _WorldStateReader(Protocol):
    """Structural interface for `PostgresWorldStateRepository.get_atom` —
    see `_UnknownReaderWriter` for why this is a `Protocol`, not an import
    of the concrete repository type."""

    async def get_atom(self, atom_id: str, *, scope: ContextScope) -> WorldStateAtom | None: ...


#: Epistemic kinds a real family member/professional/device can assert and
#: that therefore may serve as resolution evidence — deliberately excludes
#: HYPOTHESIS and UNKNOWN (never resolved by more unresolved cognition) and
#: is further narrowed by the `attributed_actor_type != AI` check below,
#: which is what actually rules out PERSPECTIVE atoms the AI authored.
_ELIGIBLE_EVIDENCE_KINDS = frozenset(
    {
        WorldStateEpistemicKind.FACT,
        WorldStateEpistemicKind.OBSERVATION,
        WorldStateEpistemicKind.SELF_REPORT,
        WorldStateEpistemicKind.OTHER_REPORT,
        WorldStateEpistemicKind.PERSPECTIVE,
    }
)


async def resolve_unknown(
    *,
    unknown_repository: _UnknownReaderWriter,
    world_state_repository: _WorldStateReader,
    unknown_id: str,
    scope: ContextScope,
    resolution_atom_ids: Sequence[str],
    resolved_at: datetime,
) -> UnknownState:
    """Validate every resolution atom against the durable World State
    before ever calling the repository's state-changing primitive.

    Order matters: the Unknown itself is read first (its `blocking_refs`
    and `target_predicate` are needed to validate the evidence against),
    then every atom is fetched and validated *before* any write happens —
    a partially-valid resolution is rejected wholesale, never partially
    applied.
    """

    if not resolution_atom_ids:
        raise ContextContractError("RESOLVED_UNKNOWN_REQUIRES_RESOLUTION_REFS")

    unknown = await unknown_repository.get(unknown_id, scope=scope)
    if unknown is None:
        raise ContextContractError(f"UNKNOWN_NOT_FOUND:{unknown_id}")

    target_predicate_addressed = False
    for atom_id in resolution_atom_ids:
        # 3.1 must really exist as a durable row.
        atom = await world_state_repository.get_atom(atom_id, scope=scope)
        if atom is None:
            raise ContextContractError(f"UNKNOWN_RESOLUTION_EVIDENCE_NOT_FOUND:{atom_id}")

        # 3.2 tenant/family/purpose/consent — get_atom's own scope check
        # (`_assert_row_readable_by`) already fails closed on cross-tenant/
        # cross-family/purpose-mismatch/consent-mismatch before returning,
        # so reaching this line means the atom is legitimately in scope.

        # 3.3 must be genuinely new — known only after the Unknown existed.
        if unknown.created_at is not None and atom.recorded_at <= unknown.created_at:
            raise ContextContractError(f"UNKNOWN_RESOLUTION_EVIDENCE_NOT_NEW:{atom_id}")

        # 3.4 AI cannot resolve its own (or anyone else's) Unknown.
        if atom.attributed_actor_type is WorldStateActorType.AI:
            raise ContextContractError(f"AI_CANNOT_RESOLVE_UNKNOWN:{atom_id}")

        # 3.5 only real accounts of the world are eligible evidence kinds.
        if atom.epistemic_kind not in _ELIGIBLE_EVIDENCE_KINDS:
            raise ContextContractError(
                f"UNKNOWN_RESOLUTION_EVIDENCE_KIND_NOT_ELIGIBLE:{atom_id}:{atom.epistemic_kind.value}"
            )

        if unknown.target_predicate is not None and atom.predicate == unknown.target_predicate:
            target_predicate_addressed = True

    # 3.6 at least one atom must actually address what was asked.
    if unknown.target_predicate is not None and not target_predicate_addressed:
        raise ContextContractError("UNKNOWN_RESOLUTION_TARGET_NOT_ADDRESSED")

    return await unknown_repository.mark_resolved(
        unknown_id,
        scope=scope,
        resolution_refs=tuple(resolution_atom_ids),
        resolved_at=resolved_at,
    )


__all__ = ["resolve_unknown"]
