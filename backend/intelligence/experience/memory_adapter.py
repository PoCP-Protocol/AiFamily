"""Pure in-memory memory-candidate adapter for Sprint 0 contract tests.

This adapter deliberately stops at the AI/runtime boundary.  It does not call a
model, write a domain aggregate, or pretend that an in-memory store is the
production deletion worker.  Its job is to prove the confirm/retract/retrieve/
delete semantics before the Family/Journey application wires a durable port.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum

from backend.intelligence.experience.contracts import (
    DeletionRef,
    ExperienceContractError,
    ExperienceProvenance,
    ExperienceScope,
    MemoryLevel,
    MemoryRef,
    MemoryScope,
    ScopeMismatchError,
)


class MemoryCandidateStatus(StrEnum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    RETRACTED = "retracted"


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    """A draft memory awaiting explicit family confirmation."""

    candidate_id: str
    scope: ExperienceScope
    memory_scope: MemoryScope
    level: MemoryLevel
    source_ref: str
    provenance: ExperienceProvenance
    expires_at: datetime
    proposed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: MemoryCandidateStatus = MemoryCandidateStatus.PROPOSED
    confirmed_memory_id: str | None = None
    derived_memory_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.source_ref:
            raise ExperienceContractError("candidate_id and source_ref are required")
        if not isinstance(self.scope, ExperienceScope):
            raise ExperienceContractError("EXPERIENCE_SCOPE_REQUIRED")
        if not isinstance(self.memory_scope, MemoryScope):
            raise ExperienceContractError("MEMORY_SCOPE_UNSUPPORTED")
        if not isinstance(self.level, MemoryLevel):
            raise ExperienceContractError("MEMORY_LEVEL_UNSUPPORTED")
        if not isinstance(self.provenance, ExperienceProvenance):
            raise ExperienceContractError("MEMORY_PROVENANCE_REQUIRED")
        if not isinstance(self.status, MemoryCandidateStatus):
            raise ExperienceContractError("MEMORY_CANDIDATE_STATUS_UNSUPPORTED")
        expected_count = {
            MemoryScope.CHILD: 1,
            MemoryScope.GUARDIAN: 1,
        }.get(self.memory_scope)
        if expected_count is not None and len(self.scope.subject_ids) != expected_count:
            raise ExperienceContractError(
                f"{self.memory_scope.value} memory requires exactly one subject"
            )
        if self.memory_scope is MemoryScope.FAMILY_RELATIONSHIP and len(self.scope.subject_ids) < 2:
            raise ExperienceContractError(
                "family_relationship memory requires at least two subjects"
            )
        if self.expires_at <= self.proposed_at:
            raise ExperienceContractError("MEMORY_CANDIDATE_EXPIRY_INVALID")
        if any(not value or value == self.candidate_id for value in self.derived_memory_ids):
            raise ExperienceContractError("derived_memory_ids must be distinct non-empty ids")
        if len(set(self.derived_memory_ids)) != len(self.derived_memory_ids):
            raise ExperienceContractError("derived_memory_ids must not contain duplicates")
        if self.status is MemoryCandidateStatus.CONFIRMED and not self.confirmed_memory_id:
            raise ExperienceContractError("confirmed candidate requires memory id")


@dataclass(frozen=True, slots=True)
class MemoryDeletionProof:
    """Proof returned after source + derived references are removed."""

    proof_id: str
    deletion_id: str
    tenant_id: str
    region_id: str
    family_id: str
    subject_ids: tuple[str, ...]
    deleted_memory_ids: tuple[str, ...]
    requested_by: str
    provenance_ref: str
    correlation_id: str
    deleted_at: datetime

    def __post_init__(self) -> None:
        if not self.proof_id or not self.deletion_id or not self.requested_by:
            raise ExperienceContractError(
                "deletion proof identity and requested_by are required"
            )
        if not self.deleted_memory_ids:
            raise ExperienceContractError("deletion proof must contain deleted ids")


def _assert_exact_scope(expected: ExperienceScope, actual: ExperienceScope) -> None:
    if expected.tenant_id != actual.tenant_id:
        raise ScopeMismatchError("CROSS_TENANT_MEMORY_SCOPE")
    if expected.region_id != actual.region_id or expected.family_id != actual.family_id:
        raise ScopeMismatchError("CROSS_FAMILY_MEMORY_SCOPE")
    if frozenset(expected.subject_ids) != frozenset(actual.subject_ids):
        raise ScopeMismatchError("CROSS_SUBJECT_MEMORY_SCOPE")
    if expected.purpose != actual.purpose:
        raise ScopeMismatchError("MEMORY_PURPOSE_MISMATCH")
    if expected.consent_version != actual.consent_version:
        raise ExperienceContractError("MEMORY_CONSENT_VERSION_MISMATCH")
    if not actual.consent_granted:
        raise ExperienceContractError("CONSENT_REQUIRED")


def _assert_memory_exact_scope(memory: MemoryRef, actual: ExperienceScope) -> None:
    if memory.tenant_id != actual.tenant_id:
        raise ScopeMismatchError("CROSS_TENANT_MEMORY_SCOPE")
    if memory.region_id != actual.region_id or memory.family_id != actual.family_id:
        raise ScopeMismatchError("CROSS_FAMILY_MEMORY_SCOPE")
    if frozenset(memory.subject_ids) != frozenset(actual.subject_ids):
        raise ScopeMismatchError("CROSS_SUBJECT_MEMORY_SCOPE")
    if memory.purpose != actual.purpose:
        raise ScopeMismatchError("MEMORY_PURPOSE_MISMATCH")
    if memory.consent_version != actual.consent_version:
        raise ExperienceContractError("MEMORY_CONSENT_VERSION_MISMATCH")
    if not actual.consent_granted:
        raise ExperienceContractError("CONSENT_REQUIRED")


class InMemoryMemoryAdapter:
    """Deterministic adapter used to exercise the memory application port."""

    def __init__(self) -> None:
        self._candidates: dict[tuple[str, str], MemoryCandidate] = {}
        self._memories: dict[tuple[str, str], MemoryRef] = {}
        self._proofs: dict[tuple[str, str], MemoryDeletionProof] = {}

    def propose(self, candidate: MemoryCandidate) -> MemoryCandidate:
        """Store a proposal idempotently within one tenant."""

        key = (candidate.scope.tenant_id, candidate.candidate_id)
        existing = self._candidates.get(key)
        if existing is None:
            self._candidates[key] = candidate
            return candidate
        if existing != candidate:
            raise ExperienceContractError("MEMORY_CANDIDATE_IDEMPOTENCY_CONFLICT")
        return existing

    def confirm(
        self,
        candidate_id: str,
        scope: ExperienceScope,
        *,
        consent_granted: bool,
        confirmed_by: str,
    ) -> MemoryRef:
        """Confirm a proposal and materialize only a runtime memory reference."""

        if not consent_granted:
            raise ExperienceContractError("MEMORY_CONSENT_REQUIRED")
        if not confirmed_by:
            raise ExperienceContractError("MEMORY_CONFIRMER_REQUIRED")
        candidate = self._find_candidate(candidate_id, scope)
        _assert_exact_scope(candidate.scope, scope)
        if candidate.status is MemoryCandidateStatus.RETRACTED:
            raise ExperienceContractError("MEMORY_CANDIDATE_RETRACTED")
        if candidate.status is MemoryCandidateStatus.CONFIRMED:
            assert candidate.confirmed_memory_id is not None
            memory = self._memories.get((scope.tenant_id, candidate.confirmed_memory_id))
            if memory is None:
                raise ExperienceContractError("MEMORY_ALREADY_DELETED")
            return memory

        memory_id = f"memory:{candidate.candidate_id}"
        memory = MemoryRef(
            memory_id=memory_id,
            memory_ref=f"memory://{memory_id}",
            tenant_id=candidate.scope.tenant_id,
            region_id=candidate.scope.region_id,
            family_id=candidate.scope.family_id,
            subject_ids=candidate.scope.subject_ids,
            memory_scope=candidate.memory_scope,
            level=candidate.level,
            purpose=candidate.scope.purpose,
            consent_version=candidate.scope.consent_version,
            consent_granted=True,
            data_class=candidate.scope.data_class,
            locale=candidate.scope.locale,
            provenance=candidate.provenance,
            deletion_ref=DeletionRef(
                deletion_id=f"{candidate.scope.deletion_ref.deletion_id}:{memory_id}",
                retention_policy=candidate.scope.deletion_ref.retention_policy,
            ),
            source_ref=candidate.source_ref,
            correlation_id=candidate.scope.correlation_id,
            causation_id=candidate.scope.causation_id,
            created_at=candidate.proposed_at,
            expires_at=candidate.expires_at,
            derived_memory_ids=candidate.derived_memory_ids,
        )
        self._memories[(scope.tenant_id, memory_id)] = memory
        self._candidates[(scope.tenant_id, candidate_id)] = replace(
            candidate,
            status=MemoryCandidateStatus.CONFIRMED,
            confirmed_memory_id=memory_id,
        )
        return memory

    def retract_candidate(
        self,
        candidate_id: str,
        scope: ExperienceScope,
        *,
        reason: str,
    ) -> MemoryCandidate:
        """Retract an unconfirmed proposal; confirmation is never implicit."""

        if not reason:
            raise ExperienceContractError("MEMORY_RETRACTION_REASON_REQUIRED")
        candidate = self._find_candidate(candidate_id, scope)
        _assert_exact_scope(candidate.scope, scope)
        if candidate.status is not MemoryCandidateStatus.PROPOSED:
            raise ExperienceContractError("MEMORY_CANDIDATE_NOT_RETRACTABLE")
        updated = replace(candidate, status=MemoryCandidateStatus.RETRACTED)
        self._candidates[(scope.tenant_id, candidate_id)] = updated
        return updated

    def retract(
        self,
        target_id: str,
        scope: ExperienceScope,
        *,
        requested_by: str,
        reason: str,
    ) -> MemoryCandidate | MemoryDeletionProof:
        """Unified user-facing retract operation for draft or confirmed memory."""

        if target_id.startswith("memory:"):
            return self.delete(target_id, scope, requested_by=requested_by)
        return self.retract_candidate(target_id, scope, reason=reason)

    def retrieve(
        self,
        memory_id: str,
        scope: ExperienceScope,
        *,
        purpose: str,
        moment: datetime | None = None,
    ) -> MemoryRef:
        """Retrieve only a currently authorized memory reference."""

        memory = self._find_memory(memory_id, scope)
        memory.assert_readable_by(scope, purpose=purpose, moment=moment)
        return memory

    def delete(
        self,
        memory_id: str,
        scope: ExperienceScope,
        *,
        requested_by: str,
    ) -> MemoryDeletionProof:
        """Delete source and derived ids and return an idempotent proof."""

        if not requested_by:
            raise ExperienceContractError("MEMORY_DELETION_ACTOR_REQUIRED")
        for proof in self._proofs.values():
            if memory_id not in proof.deleted_memory_ids:
                continue
            if proof.tenant_id != scope.tenant_id:
                raise ScopeMismatchError("CROSS_TENANT_MEMORY_DELETE")
            if proof.family_id != scope.family_id:
                raise ScopeMismatchError("CROSS_FAMILY_MEMORY_DELETE")
            return proof
        memory = self._find_memory(memory_id, scope, allow_deleted=True)
        _assert_memory_exact_scope(memory, scope)
        proof_key = (scope.tenant_id, memory.deletion_ref.deletion_id)
        existing_proof = self._proofs.get(proof_key)
        if existing_proof is not None:
            return existing_proof
        deleted_ids = memory.deletion_cascade_ids()
        for deleted_id in deleted_ids:
            self._memories.pop((scope.tenant_id, deleted_id), None)
        proof = MemoryDeletionProof(
            proof_id=f"proof:{memory.deletion_ref.deletion_id}",
            deletion_id=memory.deletion_ref.deletion_id,
            tenant_id=scope.tenant_id,
            region_id=scope.region_id,
            family_id=scope.family_id,
            subject_ids=scope.subject_ids,
            deleted_memory_ids=deleted_ids,
            requested_by=requested_by,
            provenance_ref=memory.provenance.provenance_ref,
            correlation_id=scope.correlation_id,
            deleted_at=datetime.now(UTC),
        )
        self._proofs[proof_key] = proof
        return proof

    def get_deletion_proof(
        self,
        proof_id: str,
        scope: ExperienceScope,
    ) -> MemoryDeletionProof:
        for (tenant_id, _), proof in self._proofs.items():
            if proof.proof_id != proof_id:
                continue
            if tenant_id != scope.tenant_id:
                raise ScopeMismatchError("CROSS_TENANT_MEMORY_DELETE_PROOF")
            if proof.region_id != scope.region_id or proof.family_id != scope.family_id:
                raise ScopeMismatchError("CROSS_FAMILY_MEMORY_DELETE_PROOF")
            if frozenset(proof.subject_ids) != frozenset(scope.subject_ids):
                raise ScopeMismatchError("CROSS_SUBJECT_MEMORY_DELETE_PROOF")
            return proof
        raise ExperienceContractError("MEMORY_DELETION_PROOF_NOT_FOUND")

    def _find_candidate(self, candidate_id: str, scope: ExperienceScope) -> MemoryCandidate:
        candidate = self._candidates.get((scope.tenant_id, candidate_id))
        if candidate is None:
            for (tenant_id, known_id), _known in self._candidates.items():
                if known_id == candidate_id and tenant_id != scope.tenant_id:
                    raise ScopeMismatchError("CROSS_TENANT_MEMORY_SCOPE")
            raise ExperienceContractError("MEMORY_CANDIDATE_NOT_FOUND")
        return candidate

    def _find_memory(
        self,
        memory_id: str,
        scope: ExperienceScope,
        *,
        allow_deleted: bool = False,
    ) -> MemoryRef:
        memory = self._memories.get((scope.tenant_id, memory_id))
        if memory is None:
            for (tenant_id, known_id), _known in self._memories.items():
                if known_id == memory_id and tenant_id != scope.tenant_id:
                    raise ScopeMismatchError("CROSS_TENANT_MEMORY_READ")
            if allow_deleted:
                for proof in self._proofs.values():
                    if memory_id in proof.deleted_memory_ids:
                        if proof.tenant_id != scope.tenant_id:
                            raise ScopeMismatchError("CROSS_TENANT_MEMORY_DELETE")
                        raise ExperienceContractError("MEMORY_ALREADY_DELETED")
            raise ExperienceContractError("MEMORY_NOT_FOUND")
        # MemoryRef owns the exact scope fields; adapt a tiny scope for deletion
        # without adding a mutable/domain aggregate to this adapter.
        return memory


__all__ = [
    "InMemoryMemoryAdapter",
    "MemoryCandidate",
    "MemoryCandidateStatus",
    "MemoryDeletionProof",
]
