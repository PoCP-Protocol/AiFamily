from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.schema_registry import (
    SchemaAlreadyRegistered,
    SchemaDefinition,
    SchemaNotFound,
    SchemaRegistry,
    SchemaValidationError,
)


def _schema(*, status: str = "PUBLISHED", effective_at: datetime | None = None) -> SchemaDefinition:
    return SchemaDefinition(
        schema_ref="growth_perspective_v1",
        version="v1",
        use_case="assessment_interpretation",
        agent_id="parent_advisor",
        object_type="Perspective",
        required_fields=("summary", "evidence_refs", "limitations"),
        evidence_refs_non_empty=True,
        forbidden_fields=frozenset({"diagnosis", "family_total_score", "family_ranking"}),
        enum_constraints={"boundary": ("hypothesis_not_fact",)},
        boundary_labels=("hypothesis_not_fact", "recommendation_not_decision"),
        human_gate_rule="REVIEW_REQUIRED",
        json_schema={
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "evidence_refs": {"type": "array", "minItems": 1},
                "limitations": {"type": "string"},
                "boundary": {"type": "string"},
            },
            "additionalProperties": False,
        },
        status=status,  # type: ignore[arg-type]
        effective_at=effective_at if effective_at is not None else datetime.now(UTC),
        reviewer="reviewer" if status == "PUBLISHED" else None,
        change_reason="reviewed" if status in {"REVIEW", "RETIRED"} else "",
    )


def test_schema_registry_resolves_only_effective_bound_version() -> None:
    now = datetime.now(UTC)
    registry = SchemaRegistry(definitions=(_schema(effective_at=now - timedelta(minutes=1)),))
    resolved = registry.resolve(
        use_case="assessment_interpretation", agent_id="parent_advisor"
    )
    assert resolved.object_type == "Perspective"
    assert registry.find(use_case="assessment_interpretation", agent_id="wrong") is None
    with pytest.raises(SchemaNotFound):
        registry.resolve(
            use_case="assessment_interpretation",
            agent_id="parent_advisor",
            at=now - timedelta(days=1),
        )


def test_schema_validation_enforces_required_evidence_enum_and_forbidden_fields() -> None:
    definition = _schema()
    registry = SchemaRegistry(definitions=(definition,))
    valid = {
        "summary": "A bounded perspective.",
        "evidence_refs": ["evidence:1"],
        "limitations": "Not a diagnosis.",
        "boundary": "hypothesis_not_fact",
    }
    assert registry.validate(
        valid,
        use_case="assessment_interpretation",
        agent_id="parent_advisor",
    ) == valid
    for invalid, code in (
        ({**valid, "diagnosis": "yes"}, "FORBIDDEN_FIELD"),
        ({**valid, "evidence_refs": []}, "EVIDENCE_REFS_REQUIRED"),
        ({**valid, "boundary": "fact"}, "ENUM_VALUE_INVALID"),
        ({"summary": "x", "evidence_refs": ["evidence:1"]}, "REQUIRED_FIELD_MISSING"),
    ):
        with pytest.raises(SchemaValidationError, match=code):
            registry.validate(
                invalid,
                use_case="assessment_interpretation",
                agent_id="parent_advisor",
            )


def test_schema_versions_are_not_overwritten_and_human_gate_is_explicit() -> None:
    registry = SchemaRegistry(definitions=(_schema(),))
    with pytest.raises(SchemaAlreadyRegistered):
        registry.register(_schema())
    assert registry.get("growth_perspective_v1", "v1").requires_human_gate  # type: ignore[union-attr]


def test_allowed_fields_can_tighten_a_schema_without_mutating_the_version() -> None:
    definition = _schema()
    definition = replace(
        definition,
        allowed_fields=frozenset({"summary", "evidence_refs", "limitations", "boundary"}),
    )
    registry = SchemaRegistry(definitions=(definition,))
    with pytest.raises(SchemaValidationError, match="UNDECLARED_FIELD"):
        registry.validate(
            {
                "summary": "x",
                "evidence_refs": ["evidence:1"],
                "limitations": "x",
                "boundary": "hypothesis_not_fact",
                "unexpected": "x",
            },
            "assessment_interpretation",
            "parent_advisor",
        )
