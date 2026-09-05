from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.experience.contracts import (
    DeletionRef,
    ExperienceContractError,
    ExperienceProvenance,
    ExperienceScope,
    MemoryLevel,
    MemoryScope,
    ProvenanceKind,
    ScopeMismatchError,
)
from backend.intelligence.experience.memory_adapter import (
    InMemoryMemoryAdapter,
    MemoryCandidate,
    MemoryCandidateStatus,
    MemoryDeletionProof,
)


def _scope(
    *,
    tenant_id: str = "tenant-a",
    family_id: str = "family-a",
    subjects: tuple[str, ...] = ("child-a",),
    purpose: str = "growth_support",
) -> ExperienceScope:
    return ExperienceScope(
        global_id=f"global-{tenant_id}-{family_id}",
        tenant_id=tenant_id,
        region_id="CN",
        family_id=family_id,
        subject_ids=subjects,
        purpose=purpose,
        consent_version="consent.v1",
        consent_granted=True,
        data_class="MINOR_PERSONAL_DATA",  # type: ignore[arg-type]
        locale="zh-CN",
        content_locale="zh-CN",
        model_locale="zh-CN",
        policy_locale="zh-CN",
        deletion_ref=DeletionRef("del-memory", "memory.v1"),
        correlation_id="corr-memory",
        causation_id="cause-memory",
    )


def _candidate(
    *,
    candidate_id: str = "candidate-001",
    scope: ExperienceScope | None = None,
    memory_scope: MemoryScope = MemoryScope.CHILD,
    expires_at: datetime | None = None,
    derived_memory_ids: tuple[str, ...] = (),
    proposed_at: datetime | None = None,
) -> MemoryCandidate:
    proposed_at = proposed_at or datetime.now(UTC)
    return MemoryCandidate(
        candidate_id=candidate_id,
        scope=scope or _scope(),
        memory_scope=memory_scope,
        level=MemoryLevel.M1_SESSION,
        source_ref="event:voice-001",
        provenance=ExperienceProvenance(
            provenance_ref="prov-memory",
            source_refs=("event:voice-001",),
            kind=ProvenanceKind.USER,
            policy_version="memory-policy.v1",
        ),
        expires_at=expires_at or (proposed_at + timedelta(days=1)),
        proposed_at=proposed_at,
        derived_memory_ids=derived_memory_ids,
    )


def test_confirm_retrieve_and_confirm_again_are_idempotent() -> None:
    adapter = InMemoryMemoryAdapter()
    candidate = adapter.propose(_candidate(derived_memory_ids=("memory:derived-001",)))

    first = adapter.confirm(
        candidate.candidate_id,
        candidate.scope,
        consent_granted=True,
        confirmed_by="guardian-a",
    )
    second = adapter.confirm(
        candidate.candidate_id,
        candidate.scope,
        consent_granted=True,
        confirmed_by="guardian-a",
    )
    retrieved = adapter.retrieve(
        first.memory_id,
        candidate.scope,
        purpose="growth_support",
    )

    assert first == second == retrieved
    assert adapter._candidates[("tenant-a", candidate.candidate_id)].status is (
        MemoryCandidateStatus.CONFIRMED
    )


@pytest.mark.parametrize(
    ("memory_scope", "subjects"),
    [
        (MemoryScope.CHILD, ("child-a",)),
        (MemoryScope.GUARDIAN, ("guardian-a",)),
        (MemoryScope.FAMILY_RELATIONSHIP, ("child-a", "guardian-a")),
    ],
)
def test_all_memory_scopes_require_explicit_confirmation(
    memory_scope: MemoryScope,
    subjects: tuple[str, ...],
) -> None:
    adapter = InMemoryMemoryAdapter()
    scope = _scope(subjects=subjects)
    proposed = adapter.propose(
        _candidate(
            candidate_id="candidate-scope",
            scope=scope,
            memory_scope=memory_scope,
        )
    )
    memory = adapter.confirm(
        "candidate-scope",
        proposed.scope,
        consent_granted=True,
        confirmed_by="guardian-a",
    )

    assert memory.memory_scope is memory_scope
    assert memory.subject_ids == subjects


def test_retract_pending_candidate_and_reject_confirmation_without_consent() -> None:
    adapter = InMemoryMemoryAdapter()
    candidate = adapter.propose(_candidate())
    with pytest.raises(ExperienceContractError, match="MEMORY_CONSENT_REQUIRED"):
        adapter.confirm(
            candidate.candidate_id,
            candidate.scope,
            consent_granted=False,
            confirmed_by="guardian-a",
        )

    retracted = adapter.retract_candidate(
        candidate.candidate_id,
        candidate.scope,
        reason="family_did_not_opt_in",
    )
    assert retracted.status is MemoryCandidateStatus.RETRACTED
    with pytest.raises(ExperienceContractError, match="CANDIDATE_RETRACTED"):
        adapter.confirm(
            candidate.candidate_id,
            candidate.scope,
            consent_granted=True,
            confirmed_by="guardian-a",
        )


def test_cross_tenant_candidate_and_memory_retrieval_are_rejected() -> None:
    adapter = InMemoryMemoryAdapter()
    candidate = adapter.propose(_candidate())
    with pytest.raises(ScopeMismatchError, match="CROSS_TENANT_MEMORY_SCOPE"):
        adapter.confirm(
            candidate.candidate_id,
            _scope(tenant_id="tenant-b", family_id="family-b"),
            consent_granted=True,
            confirmed_by="guardian-b",
        )
    memory = adapter.confirm(
        candidate.candidate_id,
        candidate.scope,
        consent_granted=True,
        confirmed_by="guardian-a",
    )
    with pytest.raises(ScopeMismatchError, match="CROSS_TENANT_MEMORY_READ"):
        adapter.retrieve(
            memory.memory_id,
            _scope(tenant_id="tenant-b", family_id="family-b"),
            purpose="growth_support",
        )


def test_expired_memory_is_rejected_by_retrieve() -> None:
    adapter = InMemoryMemoryAdapter()
    proposed_at = datetime.now(UTC) - timedelta(days=2)
    candidate = adapter.propose(
        _candidate(
            candidate_id="candidate-expired",
            proposed_at=proposed_at,
            expires_at=proposed_at + timedelta(days=1),
        )
    )
    memory = adapter.confirm(
        candidate.candidate_id,
        candidate.scope,
        consent_granted=True,
        confirmed_by="guardian-a",
    )
    with pytest.raises(ExperienceContractError, match="MEMORY_EXPIRED"):
        adapter.retrieve(
            memory.memory_id,
            candidate.scope,
            purpose="growth_support",
            moment=datetime.now(UTC),
        )


def test_delete_returns_cascade_proof_and_replay_is_idempotent() -> None:
    adapter = InMemoryMemoryAdapter()
    scope = _scope()
    candidate = adapter.propose(
        _candidate(
            candidate_id="candidate-delete",
            scope=scope,
            derived_memory_ids=("memory:transcript-001", "memory:ocr-001"),
        )
    )
    memory = adapter.confirm(
        candidate.candidate_id,
        scope,
        consent_granted=True,
        confirmed_by="guardian-a",
    )

    first = adapter.delete(memory.memory_id, scope, requested_by="guardian-a")
    replay = adapter.delete(memory.memory_id, scope, requested_by="guardian-a")
    proof = adapter.get_deletion_proof(first.proof_id, scope)

    assert isinstance(first, MemoryDeletionProof)
    assert first == replay == proof
    assert first.deleted_memory_ids == (
        memory.memory_id,
        "memory:transcript-001",
        "memory:ocr-001",
    )
    with pytest.raises(ExperienceContractError, match="MEMORY_NOT_FOUND|ALREADY_DELETED"):
        adapter.retrieve(memory.memory_id, scope, purpose="growth_support")


def test_delete_proof_cannot_be_read_by_another_tenant() -> None:
    adapter = InMemoryMemoryAdapter()
    scope = _scope()
    candidate = adapter.propose(_candidate(candidate_id="candidate-proof", scope=scope))
    memory = adapter.confirm(
        candidate.candidate_id,
        scope,
        consent_granted=True,
        confirmed_by="guardian-a",
    )
    proof = adapter.delete(memory.memory_id, scope, requested_by="guardian-a")
    with pytest.raises(ScopeMismatchError, match="CROSS_TENANT_MEMORY_DELETE_PROOF"):
        adapter.get_deletion_proof(
            proof.proof_id,
            _scope(tenant_id="tenant-b", family_id="family-b"),
        )


def test_each_confirmed_memory_gets_an_independent_deletion_proof() -> None:
    adapter = InMemoryMemoryAdapter()
    scope = _scope()
    first_candidate = adapter.propose(_candidate(candidate_id="candidate-one", scope=scope))
    second_candidate = adapter.propose(_candidate(candidate_id="candidate-two", scope=scope))
    first_memory = adapter.confirm(
        first_candidate.candidate_id,
        scope,
        consent_granted=True,
        confirmed_by="guardian-a",
    )
    second_memory = adapter.confirm(
        second_candidate.candidate_id,
        scope,
        consent_granted=True,
        confirmed_by="guardian-a",
    )

    first_proof = adapter.delete(first_memory.memory_id, scope, requested_by="guardian-a")
    second_proof = adapter.delete(second_memory.memory_id, scope, requested_by="guardian-a")

    assert first_proof.proof_id != second_proof.proof_id
    assert first_memory.memory_id in first_proof.deleted_memory_ids
    assert second_memory.memory_id in second_proof.deleted_memory_ids
