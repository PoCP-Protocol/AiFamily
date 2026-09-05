from __future__ import annotations

import pytest

from backend.intelligence.experience.contracts import DeletionRef, ExperienceScope
from backend.intelligence.intervention.action_bridge import (
    to_pending_named_action,
    to_tool_call_result,
)
from backend.intelligence.intervention.blueprint_matching import (
    BlueprintMatchingError,
    ServiceBlueprintMatcher,
)
from backend.intelligence.tool_runtime.action_outbox import ToolActionOutboxEnvelope


def _scope(data_class: str = "OPERATIONAL_TEXT") -> ExperienceScope:
    return ExperienceScope(
        global_id="global-blueprint",
        tenant_id="tenant-blueprint",
        region_id="CN",
        family_id="family-blueprint",
        subject_ids=("child-blueprint",),
        purpose="growth_support",
        consent_version="consent.v1",
        consent_granted=True,
        data_class=data_class,  # type: ignore[arg-type]
        locale="zh-CN",
        content_locale="zh-CN",
        model_locale="zh-CN",
        policy_locale="zh-CN",
        deletion_ref=DeletionRef("delete-blueprint", "blueprint.v1"),
        correlation_id="corr-blueprint",
        causation_id="cause-blueprint",
    )


def _blueprints():
    return [
        {
            "blueprint_ref": "blueprint:conversation.v2",
            "status": "PUBLISHED",
            "primary_contradiction_ref": "H1",
            "action_refs": ["action:listen", "action:reflect"],
        },
        {
            "blueprint_ref": "blueprint:draft",
            "status": "DRAFT",
            "primary_contradiction_ref": "H1",
            "action_refs": ["action:unsafe"],
        },
    ]


def test_only_published_blueprints_match_and_remain_drafts() -> None:
    matches = ServiceBlueprintMatcher().match(
        scope=_scope(),
        primary_contradiction_refs=("H1",),
        evidence_refs=("evidence:001",),
        blueprints=_blueprints(),
    )
    assert len(matches) == 1
    recommendation = matches[0]
    assert recommendation.blueprint_ref == "blueprint:conversation.v2"
    assert recommendation.status == "DRAFT"
    assert recommendation.fit_confidence == 1.0
    assert recommendation.human_gate_required is False


def test_minor_data_is_marked_for_human_gate() -> None:
    matches = ServiceBlueprintMatcher().match(
        scope=_scope("MINOR_PERSONAL_DATA"),
        primary_contradiction_refs=("H1",),
        evidence_refs=("evidence:001",),
        blueprints=_blueprints(),
    )
    assert matches[0].human_gate_required is True


def test_blueprint_recommendation_becomes_pending_named_action_only() -> None:
    recommendation = ServiceBlueprintMatcher().match(
        scope=_scope(),
        primary_contradiction_refs=("H1",),
        evidence_refs=("evidence:001",),
        blueprints=_blueprints(),
    )[0]
    pending = to_pending_named_action(
        recommendation,
        tenant_id="tenant-blueprint",
        family_id="family-blueprint",
        subject_ids=("child-blueprint",),
        purpose="growth_support",
        consent_version="consent.v1",
        correlation_id="corr-blueprint",
        provenance_ref="prov:blueprint",
    )
    assert pending.action_name == "PROPOSE_SERVICE_BLUEPRINT"
    assert pending.scope.family_id == "family-blueprint"
    assert pending.action_arguments["recommendation_status"] == "DRAFT"


def test_blueprint_recommendation_can_enter_tool_outbox_as_pending_result() -> None:
    recommendation = ServiceBlueprintMatcher().match(
        scope=_scope(),
        primary_contradiction_refs=("H1",),
        evidence_refs=("evidence:001",),
        blueprints=_blueprints(),
    )[0]
    result = to_tool_call_result(
        recommendation,
        call_id="call-blueprint-001",
        tool_id="tool-blueprint",
        agent_id="parent-advisor",
        use_case="growth_support",
        tenant_id="tenant-blueprint",
        family_id="family-blueprint",
        subject_ids=("child-blueprint",),
        consent_version="consent.v1",
        correlation_id="corr-blueprint",
        provenance_ref="prov:blueprint",
    )
    assert result.status == "PENDING_HUMAN_CONFIRMATION"
    assert result.pending_action.action_name == "PROPOSE_SERVICE_BLUEPRINT"
    assert result.may_mutate_business_state is False
    envelope = ToolActionOutboxEnvelope.from_result(result, use_case="growth_support")
    assert envelope.status == "PENDING_HUMAN_CONFIRMATION"
    assert envelope.action_name == "PROPOSE_SERVICE_BLUEPRINT"


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"primary_contradiction_refs": ()}, "PRIMARY_CONTRADICTION_REQUIRED"),
        ({"evidence_refs": ()}, "BLUEPRINT_EVIDENCE_REQUIRED"),
        (
            {"blueprints": [{"status": "PUBLISHED", "action_refs": ["action:x"]}]},
            "BLUEPRINT_REF_REQUIRED",
        ),
    ],
)
def test_matching_fails_closed(kwargs, error) -> None:
    values = {
        "scope": _scope(),
        "primary_contradiction_refs": ("H1",),
        "evidence_refs": ("evidence:001",),
        "blueprints": _blueprints(),
    }
    values.update(kwargs)
    with pytest.raises(BlueprintMatchingError, match=error):
        ServiceBlueprintMatcher().match(**values)
