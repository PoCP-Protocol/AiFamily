"""Ports (interfaces) the application layer depends on — implemented by
`infrastructure/`. Domain code never imports SQLAlchemy/FastAPI directly;
it depends on these Protocols instead, per the four-layer rule in
`architecture/FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md` section 3.
"""
from __future__ import annotations

from typing import Protocol

from ..domain.ai_run import AiRunRecord
from ..domain.entities import AssessmentSession, GrowthHypothesisEvidence
from ..domain.value_objects import AssessmentTool


class AssessmentRepositoryPort(Protocol):
    """Mirrors the query/mutation surface of `FamilyRepository` as used by
    `AssessmentService` (assessment.service.ts) and
    `GrowthHypothesisService` (growth-hypothesis.service.ts). Every method
    here corresponds 1:1 to a query/mutation block in those two files.
    """

    async def assert_tenant_family_scope(self, tenant_id: str, family_id: str, actor_id: str) -> None: ...

    async def assert_subject_consent(self, family_id: str, subject_person_id: str, purpose: str) -> None: ...

    async def load_active_tool(self, tool_ref: str) -> AssessmentTool | None: ...

    async def load_tool_version(self, tool_ref: str, version_no: int) -> AssessmentTool: ...

    async def load_assessable_subjects(self, family_id: str) -> list[dict]: ...

    async def load_recent_sessions(self, tenant_id: str, family_id: str, limit: int = 10) -> list[AssessmentSession]: ...

    async def load_session(self, family_id: str, session_id: str) -> AssessmentSession: ...

    async def load_session_for_update(self, family_id: str, tenant_id: str, session_id: str) -> AssessmentSession: ...

    async def find_in_progress_session(
        self, tenant_id: str, family_id: str, subject_person_id: str, tool_ref: str, tool_version: int
    ) -> str | None: ...

    async def insert_session(
        self, tenant_id: str, family_id: str, subject_person_id: str, tool_ref: str, tool_version: int, started_by: str
    ) -> str: ...

    async def upsert_response(
        self, session_id: str, item_ref: str, response_type: str, response_value: str | bool, actor_id: str
    ) -> None: ...

    async def mark_session_submitted(self, session_id: str) -> None: ...

    async def insert_assessment_evidence(self, family_id: str, session_id: str, payload: dict) -> str: ...

    async def tenant_allows_page(self, tenant_id: str, page_id: str) -> bool: ...

    # --- idempotency / audit / outbox, ported from lockOperation/loadOperationReplay/persistOperation/auditAndEmit ---

    async def lock_operation(self, tenant_id: str, family_id: str, action: str, idempotency_key: str) -> None: ...

    async def load_operation_replay(
        self, tenant_id: str, family_id: str, action: str, idempotency_key: str, request_hash: str
    ) -> dict | None: ...

    async def persist_operation(
        self,
        tenant_id: str,
        family_id: str,
        session_id: str,
        actor_id: str,
        action: str,
        request_hash: str,
        receipt: dict,
        correlation_id: str,
        idempotency_key: str,
    ) -> None: ...

    async def write_audit_and_outbox(
        self,
        family_id: str,
        actor_id: str,
        session_id: str,
        action: str,
        event_name: str,
        receipt: dict,
        correlation_id: str,
        idempotency_key: str,
        source: str,
    ) -> None: ...

    # --- growth hypothesis / UI-03 ---

    async def load_hypothesis_evidence(
        self, family_id: str, tenant_id: str, session_id: str | None = None
    ) -> GrowthHypothesisEvidence | None: ...

    async def load_or_create_growth_intent(
        self,
        family_id: str,
        subject_person_id: str,
        need_type: str,
        goal_text: str,
        required_capability_keys: list[str],
        confirmed_by: str,
        source_ref: str,
        evidence_refs: list[str],
    ) -> dict: ...

    async def lock_hypothesis_decision(self, tenant_id: str, family_id: str, hypothesis_ref: str) -> None: ...

    async def load_hypothesis_decision_replay(
        self, tenant_id: str, family_id: str, decision_type: str, idempotency_key: str
    ) -> dict | None: ...

    async def persist_hypothesis_decision(
        self,
        tenant_id: str,
        family_id: str,
        session_id: str,
        hypothesis_ref: str,
        decision_type: str,
        actor_id: str,
        intent_id: str | None,
        idempotency_key: str,
        request_hash: str,
        receipt: dict,
        correlation_id: str,
    ) -> None: ...


class AssessmentInterpretationPort(Protocol):
    """Boundary to the AI Runtime process — the assessment domain never calls
    a model provider directly. Mirrors `createFamilyEducationAssessmentModelRuntime()
    .assessUi02ResponseSet(input, 'DEEP_AI_INTERPRETATION')` in
    growth-hypothesis.service.ts. Returns only a draft; may not mutate
    canonical state (see migration plan section 6).
    """

    async def interpret(
        self, family_id: str, evidence: GrowthHypothesisEvidence, service_depth: str = "DEEP_AI_INTERPRETATION"
    ) -> dict: ...


class AiRunLedgerPort(Protocol):
    """Records the "AI Run" step of the migration plan's AI Runtime call
    chain (section 6) — a durable, append-only trace of one AI Runtime call
    (deterministic fallback or live gateway), independent of the interpretation
    draft's own content. Implementations MUST NOT raise on the caller's
    behalf for a failed write becoming a failed interpretation: see
    `infrastructure/ai_run_ledger.py` module docstring for the fail-open
    rationale for ledger writes specifically (distinct from this domain's
    general fail-closed posture on AI *content* boundary violations).
    """

    async def record(self, run: AiRunRecord) -> None: ...
