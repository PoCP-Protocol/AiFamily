"""Assessment domain: the first local UI-02 -> UI-03 vertical slice."""

from backend.domains.assessment.service import AssessmentService, InMemoryAssessmentRepository

__all__ = ["AssessmentService", "InMemoryAssessmentRepository"]