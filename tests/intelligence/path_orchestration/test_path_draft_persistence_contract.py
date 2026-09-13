"""Contract-level proofs for path draft idempotence and the persistence seam.

These tests intentionally do not exercise a real database.  They prove two
separate things that the ADR-0158 conversation asked to keep distinct:

1. ``_draft_id`` is a deterministic pure function of the draft's identity
   inputs (computation idempotence) — this needs no persistence at all.
2. The ``PathDraftPersistencePort`` Protocol shape is self-consistent and can
   be honored by a minimal in-memory stand-in (contract idempotence) — this
   is the seam codex will later back with a real adapter.
"""

from __future__ import annotations

import pytest

from backend.intelligence.path_orchestration.contracts import (
    CapabilityCandidate,
    FamilyPathContext,
    PathDraft,
    PathDraftEvidence,
    PathDraftPersistencePort,
)
from backend.intelligence.path_orchestration.planner import _draft_id


def _evidence(ref: str) -> PathDraftEvidence:
    return PathDraftEvidence(ref, "family_need", "v1", "guardian-confirmed context")


def _context(*, context_snapshot_ref: str = "snapshot-1") -> FamilyPathContext:
    return FamilyPathContext(
        tenant_id="tenant-1",
        family_id="family-a",
        need_id="need-family-a",
        need_statement="家庭希望获得更适合当前情境的支持",
        subject_ids=("child-a",),
        context_snapshot_ref=context_snapshot_ref,
        evidence=(_evidence("need-evidence-family-a"),),
        fit_tags=frozenset({"study_start"}),
    )


def _candidate(ref: str = "capability:study-start") -> CapabilityCandidate:
    return CapabilityCandidate(
        capability_ref=ref,
        title=ref,
        description="支持 study_start",
        fit_tags=frozenset({"study_start"}),
        evidence=(_evidence(f"knowledge-{ref}"),),
    )


# ---------------------------------------------------------------------------
# 1. Computation idempotence: _draft_id needs no persistence port to prove.
# ---------------------------------------------------------------------------


def test_draft_id_is_deterministic_for_identical_inputs():
    context = _context()
    selected = (_candidate(),)

    first = _draft_id(context, selected)
    second = _draft_id(context, selected)

    assert first == second


def test_draft_id_changes_when_context_snapshot_ref_changes():
    selected = (_candidate(),)

    id_at_snapshot_one = _draft_id(_context(context_snapshot_ref="snapshot-1"), selected)
    id_at_snapshot_two = _draft_id(_context(context_snapshot_ref="snapshot-2"), selected)

    assert id_at_snapshot_one != id_at_snapshot_two


def test_draft_id_changes_when_selected_candidates_change():
    context = _context()

    id_with_one_candidate = _draft_id(context, (_candidate("capability:study-start"),))
    id_with_other_candidate = _draft_id(context, (_candidate("capability:repair-dialogue"),))

    assert id_with_one_candidate != id_with_other_candidate


def test_draft_id_is_stable_regardless_of_call_order_or_process():
    """Simulates two independent computations (e.g. two request handlers)
    arriving at the same draft_id without coordinating — the property a
    persistence port's get_or_create can then rely on as its lookup key."""
    context = _context()
    selected = (_candidate(),)

    computed_by_handler_one = _draft_id(context, selected)
    computed_by_handler_two = _draft_id(_context(), (_candidate(),))  # fresh objects, same values

    assert computed_by_handler_one == computed_by_handler_two


# ---------------------------------------------------------------------------
# 2. Contract self-consistency: a minimal in-memory stand-in for the port.
# ---------------------------------------------------------------------------


class InMemoryPathDraftPersistence:
    """Minimal stand-in proving PathDraftPersistencePort's shape is honorable.

    Not the production adapter — no durability, no concurrency control.  It
    only exists to prove the Protocol's method signatures and idempotence
    contract can be satisfied by *some* implementation.
    """

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str, str, str], PathDraft] = {}

    def _key(self, draft: PathDraft) -> tuple[str, str, str, str]:
        return (draft.tenant_id, draft.family_id, draft.need_id, draft.draft_id)

    async def get_or_create(self, draft: PathDraft) -> PathDraft:
        key = self._key(draft)
        existing = self._by_key.get(key)
        if existing is not None:
            return existing
        self._by_key[key] = draft
        return draft

    async def get_latest(
        self, *, tenant_id: str, family_id: str, need_id: str
    ) -> PathDraft | None:
        matches = [
            draft
            for draft in self._by_key.values()
            if draft.tenant_id == tenant_id
            and draft.family_id == family_id
            and draft.need_id == need_id
        ]
        if not matches:
            return None
        return max(matches, key=lambda draft: draft.generated_at)

    async def get_versions(
        self, *, tenant_id: str, family_id: str, need_id: str
    ) -> tuple[PathDraft, ...]:
        matches = tuple(
            draft
            for draft in self._by_key.values()
            if draft.tenant_id == tenant_id
            and draft.family_id == family_id
            and draft.need_id == need_id
        )
        return tuple(sorted(matches, key=lambda draft: draft.generated_at))


def _draft(context: FamilyPathContext, selected: tuple[CapabilityCandidate, ...]) -> PathDraft:
    draft_id = _draft_id(context, selected)
    reasons = {candidate.capability_ref: ("context_fit:study_start",) for candidate in selected}
    return PathDraft(
        draft_id=draft_id,
        version=1,
        tenant_id=context.tenant_id,
        family_id=context.family_id,
        need_id=context.need_id,
        context_snapshot_ref=context.context_snapshot_ref,
        nodes=selected,
        selected_reasons=reasons,
        clarifying_questions=(),
        feedback_refs=context.feedback_refs,
        feedback_signals=context.feedback_signals,
    )


def test_port_shape_is_a_runtime_checkable_protocol_satisfied_by_the_stub():
    stub = InMemoryPathDraftPersistence()
    assert isinstance(stub, PathDraftPersistencePort)


@pytest.mark.asyncio
async def test_get_or_create_returns_the_original_persisted_draft_on_repeat_calls():
    stub = InMemoryPathDraftPersistence()
    context = _context()
    draft = _draft(context, (_candidate(),))

    first_write = await stub.get_or_create(draft)
    # A second call with an equal-by-value but distinct draft object simulates
    # a second request recomputing the same draft independently.
    recomputed = _draft(context, (_candidate(),))
    second_write = await stub.get_or_create(recomputed)

    assert first_write is second_write
    assert first_write.draft_id == second_write.draft_id
    assert first_write.generated_at == second_write.generated_at
    versions = await stub.get_versions(
        tenant_id=context.tenant_id, family_id=context.family_id, need_id=context.need_id
    )
    assert len(versions) == 1


@pytest.mark.asyncio
async def test_new_context_snapshot_creates_a_new_version_without_overwriting_the_prior_one():
    stub = InMemoryPathDraftPersistence()
    first_context = _context(context_snapshot_ref="snapshot-1")
    second_context = _context(context_snapshot_ref="snapshot-2")

    first_draft = await stub.get_or_create(_draft(first_context, (_candidate(),)))
    second_draft = await stub.get_or_create(_draft(second_context, (_candidate(),)))

    assert first_draft.draft_id != second_draft.draft_id
    versions = await stub.get_versions(
        tenant_id=first_context.tenant_id,
        family_id=first_context.family_id,
        need_id=first_context.need_id,
    )
    assert len(versions) == 2
    assert first_draft in versions
    assert second_draft in versions


@pytest.mark.asyncio
async def test_get_latest_returns_none_when_no_draft_has_been_persisted():
    stub = InMemoryPathDraftPersistence()

    latest = await stub.get_latest(
        tenant_id="tenant-1", family_id="family-a", need_id="need-family-a"
    )

    assert latest is None
