from __future__ import annotations

import pytest

from backend.intelligence.experience.contracts import (
    DeletionRef,
    ExperienceScope,
)
from backend.intelligence.intervention.engine import (
    GrowthInterventionEngine,
    InterventionEngineError,
)


def _scope(*, data_class: str = "OPERATIONAL_TEXT") -> ExperienceScope:
    return ExperienceScope(
        global_id="global-intervention",
        tenant_id="tenant-intervention",
        region_id="CN",
        family_id="family-intervention",
        subject_ids=("child-intervention",),
        purpose="growth_support",
        consent_version="consent.v1",
        consent_granted=True,
        data_class=data_class,  # type: ignore[arg-type]
        locale="zh-CN",
        content_locale="zh-CN",
        model_locale="zh-CN",
        policy_locale="zh-CN",
        deletion_ref=DeletionRef("delete-intervention", "intervention.v1"),
        correlation_id="corr-intervention",
        causation_id="cause-intervention",
    )


def _select(**kwargs):
    values = {
        "scope": _scope(),
        "context_snapshot_ref": "context:intervention-001",
        "hypotheses": [
            {
                "hypothesis_ref": "H1",
                "is_primary_contradiction": True,
            },
            {
                "hypothesis_ref": "H2",
                "is_primary_contradiction": False,
            },
        ],
        "action_candidates": [
            {
                "action_ref": "action:conversation",
                "boundary": "recommendation_not_decision",
                "confidence": 0.62,
            },
            {
                "action_ref": "action:pause",
                "boundary": "recommendation_not_decision",
                "confidence": 0.91,
            },
        ],
        "evidence_refs": ("evidence:assessment-001",),
    }
    values.update(kwargs)
    return GrowthInterventionEngine().select(**values)


def test_selection_is_draft_evidence_bound_and_confidence_ordered() -> None:
    draft = _select()
    assert draft.status == "DRAFT"
    assert draft.primary_contradiction_refs == ("H1",)
    assert tuple(item.action_ref for item in draft.candidates) == (
        "action:pause",
        "action:conversation",
    )
    assert draft.candidates[0].primary_contradiction_ref == "H1"
    assert draft.candidates[0].evidence_refs == ("evidence:assessment-001",)
    assert draft.candidates[0].human_gate_required is False
    payload = draft.to_payload()
    assert payload["status"] == "DRAFT"
    assert "family_score" not in str(payload)
    assert "decision" not in payload["candidates"][0]


def test_minor_data_and_high_impact_are_human_gated() -> None:
    minor = _select(scope=_scope(data_class="MINOR_PERSONAL_DATA"))
    assert all(item.human_gate_required for item in minor.candidates)
    high_impact = _select(high_impact=True)
    assert all(item.human_gate_required for item in high_impact.candidates)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("evidence_refs", (), "INTERVENTION_EVIDENCE_REQUIRED"),
        ("action_candidates", (), "INTERVENTION_ACTION_CANDIDATES_REQUIRED"),
        (
            "action_candidates",
            ({"action_ref": "action:x", "boundary": "final_decision"},),
            "INTERVENTION_BOUNDARY_REQUIRED",
        ),
    ],
)
def test_invalid_inputs_fail_closed(field, value, error) -> None:
    with pytest.raises(InterventionEngineError, match=error):
        _select(**{field: value})


def test_more_than_three_primary_contradictions_is_rejected() -> None:
    hypotheses = [
        {"hypothesis_ref": f"H{index}", "is_primary_contradiction": True}
        for index in range(4)
    ]
    with pytest.raises(InterventionEngineError, match="TOO_MANY_PRIMARY_CONTRADICTIONS"):
        _select(hypotheses=hypotheses)
