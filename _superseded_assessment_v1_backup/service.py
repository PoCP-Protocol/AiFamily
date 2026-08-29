"""Application service for the first Assessment vertical slice.

This is explicitly a non-production, process-local implementation for dev/test.
The repository protocol is the replacement seam for a future SQLAlchemy adapter.
No model-provider SDK is used: the deterministic generator produces only a
Hypothesis. A human confirmation creates a GrowthIntent, never a score, rank,
diagnosis, or canonical Fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from backend.platform.audit import AuditEvent, AuditRecorder


class AssessmentRepository(Protocol):
    """Persistence port; replace with a SQLAlchemy implementation later."""

    sessions: dict[str, dict[str, Any]]
    hypotheses: dict[str, dict[str, Any]]
    intents: dict[str, dict[str, Any]]


@dataclass
class InMemoryAssessmentRepository:
    """Non-production process-local repository for dev/test only."""

    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    hypotheses: dict[str, dict[str, Any]] = field(default_factory=dict)
    intents: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class AssessmentService:
    repository: AssessmentRepository = field(default_factory=InMemoryAssessmentRepository)
    audit: AuditRecorder = field(default_factory=AuditRecorder)

    def _audit(
        self,
        actor_id: str,
        family_id: str,
        action: str,
        resource: str,
        resource_id: str,
        after: dict[str, Any],
    ) -> None:
        self.audit.record(
            AuditEvent(
                actor_id=actor_id,
                tenant_id=family_id,
                action=action,
                resource_type=resource,
                resource_id=resource_id,
                reason="assessment vertical slice mutation",
                correlation_id=str(uuid4()),
                after=after,
            )
        )

    def start(
        self, actor_id: str, family_id: str, subject_person_id: str, tool_ref: str | None
    ) -> dict[str, Any]:
        session = {
            "session_id": str(uuid4()),
            "family_id": family_id,
            "subject_person_id": subject_person_id,
            "tool_ref": tool_ref or "UI02_FAMILY_ASSESSMENT_V1",
            "tool_version": 1,
            "status": "IN_PROGRESS",
            "responses": {},
            "row_version": 1,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self.repository.sessions[session["session_id"]] = session
        self._audit(
            actor_id,
            family_id,
            "assessment.session_started",
            "AssessmentSession",
            session["session_id"],
            session,
        )
        return session

    def response(
        self,
        actor_id: str,
        family_id: str,
        session_id: str,
        item_ref: str,
        response_type: str,
        response_value: str | bool,
    ) -> dict[str, Any]:
        session = self._session(family_id, session_id)
        session["responses"][item_ref] = {
            "response_type": response_type,
            "response_value": response_value,
        }
        session["row_version"] += 1
        self._audit(
            actor_id,
            family_id,
            "assessment.response_saved",
            "AssessmentSession",
            session_id,
            session,
        )
        return session

    def submit(self, actor_id: str, family_id: str, session_id: str) -> dict[str, Any]:
        session = self._session(family_id, session_id)
        session["status"] = "SUBMITTED"
        session["row_version"] += 1
        session["submitted_at"] = datetime.now(UTC).isoformat()
        self._audit(
            actor_id,
            family_id,
            "assessment.session_submitted",
            "AssessmentSession",
            session_id,
            session,
        )
        return session

    def generate_hypothesis(self, actor_id: str, family_id: str, session_id: str) -> dict[str, Any]:
        session = self._session(family_id, session_id)
        if session["status"] != "SUBMITTED":
            raise ValueError("assessment session must be submitted")
        hypothesis = {
            "hypothesis_ref": str(uuid4()),
            "assessment_session_id": session_id,
            "family_id": family_id,
            "kind": "Hypothesis",
            "status": "PROPOSED",
            "subject_person_id": session["subject_person_id"],
            "subject_display_name": "家庭成员",
            "focus_ref": session["responses"]
            .get("FOCUS", {})
            .get("response_value", "PARENT_CHILD_COMMUNICATION"),
            "statement": "家庭可以从一次可观察的沟通实验开始。",
            "evidence_refs": list(session["responses"]),
            "canonical_fact": False,
            "assessment_response_id": f"responses:{session_id}",
            "assessment_evidence_id": f"evidence:{session_id}",
            "tool_version": session["tool_version"],
            "assessment_submitted_at": session.get("submitted_at"),
        }
        self.repository.hypotheses[hypothesis["hypothesis_ref"]] = hypothesis
        self._audit(
            actor_id,
            family_id,
            "assessment.hypothesis_generated",
            "GrowthHypothesis",
            hypothesis["hypothesis_ref"],
            hypothesis,
        )
        return hypothesis

    def decide(
        self,
        actor_id: str,
        family_id: str,
        session_id: str,
        hypothesis_ref: str,
        decision_type: str,
    ) -> dict[str, Any]:
        hypothesis = self.repository.hypotheses.get(hypothesis_ref)
        if (
            not hypothesis
            or hypothesis["family_id"] != family_id
            or hypothesis["assessment_session_id"] != session_id
        ):
            raise KeyError("hypothesis not found in family")
        hypothesis["status"] = "CONFIRMED" if decision_type == "CONFIRM" else "DISMISSED"
        result: dict[str, Any] = {"hypothesis": hypothesis, "growth_intent": None}
        if decision_type == "CONFIRM":
            intent = {
                "growth_intent_id": str(uuid4()),
                "family_id": family_id,
                "source_hypothesis_ref": hypothesis_ref,
                "kind": "GrowthIntent",
                "status": "PROPOSED",
                "canonical_fact": False,
            }
            self.repository.intents[intent["growth_intent_id"]] = intent
            result["growth_intent"] = intent
        self._audit(
            actor_id,
            family_id,
            "assessment.hypothesis_decided",
            "GrowthHypothesis",
            hypothesis_ref,
            result,
        )
        return result

    def _session(self, family_id: str, session_id: str) -> dict[str, Any]:
        session = self.repository.sessions.get(session_id)
        if not session or session["family_id"] != family_id:
            raise KeyError("assessment session not found in family")
        return session
