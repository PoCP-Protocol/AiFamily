"""Service-level acceptance chain for the first Assessment slice."""

from backend.domains.assessment.service import AssessmentService


def test_session_response_submit_hypothesis_confirm_chain() -> None:
    service = AssessmentService()
    session = service.start("parent-a", "family-a", "child-a", "dev-tool")
    service.response("parent-a", "family-a", session["session_id"], "item-1", "TEXT", "沟通")
    submitted = service.submit("parent-a", "family-a", session["session_id"])
    hypothesis = service.generate_hypothesis("parent-a", "family-a", session["session_id"])
    result = service.decide("parent-a", "family-a", session["session_id"], hypothesis["hypothesis_ref"], "CONFIRM")

    assert submitted["status"] == "SUBMITTED"
    assert hypothesis["kind"] == "Hypothesis"
    assert hypothesis["canonical_fact"] is False
    assert result["growth_intent"]["kind"] == "GrowthIntent"
    assert result["growth_intent"]["canonical_fact"] is False
    assert len(service.audit.all_events()) == 5


def test_repository_rejects_cross_family_session_and_hypothesis() -> None:
    service = AssessmentService()
    session = service.start("parent-a", "family-a", "child-a", None)

    try:
        service.submit("parent-a", "family-b", session["session_id"])
    except KeyError:
        pass
    else:
        raise AssertionError("cross-family session access must be rejected")