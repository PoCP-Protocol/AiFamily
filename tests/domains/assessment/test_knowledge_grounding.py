from backend.domains.assessment.domain.knowledge_grounding import (
    family_facing_grounding,
)


def test_each_family_assessment_focus_has_a_reviewed_grounding_seam() -> None:
    expected = {
        "LEARNING_HABITS",
        "EMOTION_REGULATION",
        "PARENT_CHILD_COMMUNICATION",
        "DEVICE_USE_CONTEXT",
        "SELF_REGULATION",
    }

    for focus_ref in expected:
        grounding = family_facing_grounding(focus_ref)
        assert grounding["status"] == "GROUNDED"
        assert grounding["construct_ref"]
        assert grounding["card_refs"]
        assert grounding["core_claim"]
        assert grounding["boundary"]


def test_unknown_focus_does_not_receive_a_made_up_citation() -> None:
    grounding = family_facing_grounding("UNKNOWN_FOCUS")

    assert grounding == {
        "status": "UNAVAILABLE",
        "construct_ref": None,
        "card_refs": [],
        "evidence_grade": None,
        "core_claim": None,
        "mechanism": None,
        "boundary": "KNOWLEDGE_REFERENCE_NOT_FAMILY_FACT",
    }
