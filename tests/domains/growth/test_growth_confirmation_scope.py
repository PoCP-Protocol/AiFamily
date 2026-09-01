from __future__ import annotations

from dataclasses import replace

import pytest

from backend.domains.growth.application.growth_intent_confirmation import (
    GrowthConfirmationValidationError,
    ValidatedConfirmationBinding,
)


def binding(scope_ref: str) -> ValidatedConfirmationBinding:
    return ValidatedConfirmationBinding(
        tenant_id="10000000-0000-4000-8000-000000000001",
        family_id="20000000-0000-4000-8000-000000000001",
        actor_id="30000000-0000-4000-8000-000000000001",
        subject_person_id="40000000-0000-4000-8000-000000000001",
        signal_ref="understanding:artifact-1",
        signal_version=1,
        scope_ref=scope_ref,
        reviewed_draft_ref="artifact-1",
        draft_version=1,
        provenance_ref="air-provenance:v1:sha256:one",
        human_gate_receipt_ref="gate-receipt-1",
        need_type="PARENT_CHILD_COMMUNICATION",
        goal_text="减少遇到困难题时的催促冲突",
        required_capability_keys=("FAMILY_COMMUNICATION",),
        evidence_refs=("50000000-0000-4000-8000-000000000001",),
        correlation_id="correlation-1",
        idempotency_key="confirm-1",
    )


@pytest.mark.parametrize("kind", ["assessment", "problem-understanding"])
def test_growth_binding_accepts_declared_understanding_scopes(kind: str) -> None:
    value = binding(
        f"family://10000000-0000-4000-8000-000000000001/"
        f"20000000-0000-4000-8000-000000000001/{kind}"
    )

    value.validate()


@pytest.mark.parametrize(
    "scope_ref",
    [
        "family://10000000-0000-4000-8000-000000000001/other/problem-understanding",
        "family://other/20000000-0000-4000-8000-000000000001/problem-understanding",
        "family://10000000-0000-4000-8000-000000000001/20000000-0000-4000-8000-000000000001/unknown",
    ],
)
def test_growth_binding_rejects_cross_family_or_unknown_scope(scope_ref: str) -> None:
    with pytest.raises(GrowthConfirmationValidationError, match="confirmation_scope_mismatch"):
        replace(binding(scope_ref), scope_ref=scope_ref).validate()
