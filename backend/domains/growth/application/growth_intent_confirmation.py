"""Canonical Growth input validated from an Assessment confirmation receipt."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Protocol
from uuid import UUID

from backend.domains.assessment.domain.value_objects import GROWTH_INTENT_BOUNDARY

SOURCE_TYPE = "ASSESSMENT_HYPOTHESIS"
ACTION_NAME = "GROWTH_CONFIRM_INTENT"


class GrowthConfirmationValidationError(ValueError):
    """The caller-provided validated binding is structurally invalid."""


class GrowthConfirmationConflictError(RuntimeError):
    """A durable intent or idempotency record conflicts with this binding."""


class ConfirmationCommandLike(Protocol):
    tenant_id: str
    family_id: str
    actor_id: str
    subject_person_id: str
    signal_ref: str
    signal_version: int
    scope_ref: str
    reviewed_draft_ref: str
    draft_version: int
    provenance_ref: str
    human_gate_receipt_ref: str
    need_type: str
    goal_text: str
    required_capability_keys: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    correlation_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class ValidatedConfirmationBinding:
    """Immutable Growth input after Assessment's same-UoW policy checks."""

    tenant_id: str
    family_id: str
    actor_id: str
    subject_person_id: str
    signal_ref: str
    signal_version: int
    scope_ref: str
    reviewed_draft_ref: str
    draft_version: int
    provenance_ref: str
    human_gate_receipt_ref: str
    need_type: str
    goal_text: str
    required_capability_keys: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    correlation_id: str
    idempotency_key: str
    source_type: str = SOURCE_TYPE
    boundary: str = GROWTH_INTENT_BOUNDARY

    @classmethod
    def from_command(cls, command: ConfirmationCommandLike) -> ValidatedConfirmationBinding:
        binding = cls(
            tenant_id=command.tenant_id,
            family_id=command.family_id,
            actor_id=command.actor_id,
            subject_person_id=command.subject_person_id,
            signal_ref=command.signal_ref,
            signal_version=command.signal_version,
            scope_ref=command.scope_ref,
            reviewed_draft_ref=command.reviewed_draft_ref,
            draft_version=command.draft_version,
            provenance_ref=command.provenance_ref,
            human_gate_receipt_ref=command.human_gate_receipt_ref,
            need_type=command.need_type,
            goal_text=command.goal_text,
            required_capability_keys=tuple(command.required_capability_keys),
            evidence_refs=tuple(command.evidence_refs),
            correlation_id=command.correlation_id,
            idempotency_key=command.idempotency_key,
        )
        binding.validate()
        return binding

    def validate(self) -> None:
        required = {
            "tenant_id": self.tenant_id,
            "family_id": self.family_id,
            "actor_id": self.actor_id,
            "subject_person_id": self.subject_person_id,
            "signal_ref": self.signal_ref,
            "scope_ref": self.scope_ref,
            "reviewed_draft_ref": self.reviewed_draft_ref,
            "provenance_ref": self.provenance_ref,
            "human_gate_receipt_ref": self.human_gate_receipt_ref,
            "need_type": self.need_type,
            "goal_text": self.goal_text,
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
        }
        if any(not value.strip() for value in required.values()):
            raise GrowthConfirmationValidationError("confirmation_required_reference_missing")
        if self.signal_version < 1 or self.draft_version < 1:
            raise GrowthConfirmationValidationError("confirmation_version_invalid")
        if not self.required_capability_keys or not all(
            value.strip() for value in self.required_capability_keys
        ):
            raise GrowthConfirmationValidationError("confirmation_capability_reference_missing")
        if not self.evidence_refs or not all(value.strip() for value in self.evidence_refs):
            raise GrowthConfirmationValidationError("confirmation_evidence_reference_missing")
        expected_scope = f"family://{self.tenant_id}/{self.family_id}/assessment"
        if self.scope_ref != expected_scope:
            raise GrowthConfirmationValidationError("confirmation_scope_mismatch")
        if self.source_type != SOURCE_TYPE or self.boundary != GROWTH_INTENT_BOUNDARY:
            raise GrowthConfirmationValidationError("confirmation_boundary_invalid")
        for field_name, value in (
            ("tenant_id", self.tenant_id),
            ("family_id", self.family_id),
            ("actor_id", self.actor_id),
            ("subject_person_id", self.subject_person_id),
            *(("evidence_ref", value) for value in self.evidence_refs),
        ):
            try:
                UUID(value)
            except ValueError as error:
                raise GrowthConfirmationValidationError(
                    f"confirmation_{field_name}_invalid"
                ) from error

    def request_hash(self) -> str:
        payload = asdict(self)
        payload.pop("correlation_id")
        payload.pop("idempotency_key")
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    def receipt_binding(self) -> dict[str, object]:
        """Full immutable binding persisted in receipt, Audit, and Outbox."""

        return {
            "tenant_id": self.tenant_id,
            "family_id": self.family_id,
            "actor_id": self.actor_id,
            "scope_ref": self.scope_ref,
            "signal_ref": self.signal_ref,
            "signal_version": self.signal_version,
            "reviewed_draft_ref": self.reviewed_draft_ref,
            "draft_version": self.draft_version,
            "provenance_ref": self.provenance_ref,
            "human_gate_receipt_ref": self.human_gate_receipt_ref,
            "subject_person_id": self.subject_person_id,
            "need_type": self.need_type,
            "goal_text": self.goal_text,
            "required_capability_keys": list(self.required_capability_keys),
            "evidence_refs": list(self.evidence_refs),
            "source_type": self.source_type,
            "boundary": self.boundary,
        }


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


__all__ = [
    "ACTION_NAME",
    "SOURCE_TYPE",
    "GrowthConfirmationConflictError",
    "GrowthConfirmationValidationError",
    "ValidatedConfirmationBinding",
]
