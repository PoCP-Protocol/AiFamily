"""In-memory fake repository — the test double the current test suite runs
against (per `architecture/FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md`
section 9 "FakeProvider" requirement). Mirrors the same invariants the real
repository must hold: idempotency-key replay, advisory-lock semantics
(approximated with a plain dict — no real cross-request concurrency
guarantee, that only comes from the real Postgres advisory lock),
tenant/family scope checks, and the same error codes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from backend.platform.audit import AuditActionKind, AuditEvent

from ..domain.entities import AssessmentResponse, AssessmentSession, GrowthHypothesisEvidence
from ..domain.errors import (
    AssessmentConflictError,
    AssessmentForbiddenError,
    AssessmentNotFoundError,
)
from ..domain.permission_policy import FAMILY_MANAGE_ROLES
from ..domain.value_objects import AssessmentSessionStatus, AssessmentTool, AssessmentToolItem

DEFAULT_TEST_ACTOR = "actor-1"


_FOUR_POINT_OPTIONS = ["often", "sometimes", "rarely", "not_sure"]

#: The v1 seed tool used a 3-option `FOCUS` (`COMMUNICATION`/`HOMEWORK`/
#: `SCREEN_TIME`) that never matched the mobile UI-02 screen's real design
#: (`frontend/mobile/lib/family/core-growth.ts`'s five `GrowthFocusId`
#: values, plus `FAMILY_STRUCTURE`/`CHILD_GENDER` and per-dimension deep
#: questions) — every real UI-02 submission against the old tool failed with
#: `assessment_choice_not_in_tool_version` / `assessment_item_contract_mismatch`.
#: This v4 item bank was already designed and construct-admission-reviewed
#: (`tests/domains/assessment/test_family_support_needs_v{2,3,4}_item_bank.py`
#: are its content-fidelity tests) but never wired into the tool this
#: repository actually serves — the fix here is to serve it, not to shrink the
#: mobile screen down to the old 3-option form.
#:
#: Deliberately excluded, and must stay excluded until the safety gate exists
#: in code (see `test_family_support_needs_v3_item_bank.py`'s docstring):
#: `EMOTION_REGULATION_Q01` (`safety_boundary: human_gate_if_crisis_signal`)
#: and `PARENT_CAPACITY_PRESSURE` (`safety_boundary:
#: human_gate_if_parent_crisis`) — both flagged for Human Gate routing that no
#: code enforces yet. Adding them back without that gate would let a crisis
#: signal reach a family with no human in the loop.
_FAMILY_SUPPORT_NEEDS_V4_ITEMS: tuple[dict, ...] = (
    {
        "item_ref": "FOCUS",
        "response_type": "SINGLE_CHOICE",
        "required": True,
        "options": [
            "LEARNING_HABITS",
            "EMOTION_REGULATION",
            "PARENT_CHILD_COMMUNICATION",
            "DEVICE_USE_CONTEXT",
            "SELF_REGULATION",
        ],
    },
    {
        "item_ref": "FAMILY_STRUCTURE",
        "response_type": "SINGLE_CHOICE",
        "required": False,
        "options": ["TWO_PARENT", "SINGLE_PARENT", "BLENDED", "PREFER_NOT_TO_SAY"],
    },
    {
        "item_ref": "CHILD_GENDER",
        "response_type": "SINGLE_CHOICE",
        "required": False,
        "options": ["BOY", "GIRL", "SELF_DESCRIBED", "PREFER_NOT_TO_SAY"],
    },
    {
        "item_ref": "LEARNING_HABITS_Q01",
        "response_type": "SINGLE_CHOICE",
        "required": False,
        "options": _FOUR_POINT_OPTIONS,
    },
    {
        "item_ref": "LEARNING_HABITS_Q02",
        "response_type": "SINGLE_CHOICE",
        "required": False,
        "options": _FOUR_POINT_OPTIONS,
    },
    {
        "item_ref": "LEARNING_HABITS_Q03",
        "response_type": "SINGLE_CHOICE",
        "required": False,
        "options": _FOUR_POINT_OPTIONS,
    },
    {
        "item_ref": "PARENT_CHILD_COMMUNICATION_Q01",
        "response_type": "SINGLE_CHOICE",
        "required": False,
        "options": _FOUR_POINT_OPTIONS,
    },
    {
        "item_ref": "PARENT_CHILD_COMMUNICATION_Q02",
        "response_type": "SINGLE_CHOICE",
        "required": False,
        "options": _FOUR_POINT_OPTIONS,
    },
    {
        "item_ref": "PARENT_CHILD_COMMUNICATION_Q03",
        "response_type": "SINGLE_CHOICE",
        "required": False,
        "options": _FOUR_POINT_OPTIONS,
    },
    {
        "item_ref": "DEVICE_USE_CONTEXT_Q01",
        "response_type": "SINGLE_CHOICE",
        "required": False,
        "options": _FOUR_POINT_OPTIONS,
    },
    {
        "item_ref": "DEVICE_USE_CONTEXT_Q02",
        "response_type": "SINGLE_CHOICE",
        "required": False,
        "options": _FOUR_POINT_OPTIONS,
    },
    {
        "item_ref": "DEVICE_USE_CONTEXT_Q03",
        "response_type": "SINGLE_CHOICE",
        "required": False,
        "options": _FOUR_POINT_OPTIONS,
    },
    {
        "item_ref": "EMOTION_REGULATION_Q02",
        "response_type": "SINGLE_CHOICE",
        "required": False,
        "options": _FOUR_POINT_OPTIONS,
    },
    {
        "item_ref": "EMOTION_REGULATION_Q03",
        "response_type": "SINGLE_CHOICE",
        "required": False,
        "options": _FOUR_POINT_OPTIONS,
    },
    {
        "item_ref": "SCHOOL_FAMILY_FEEDBACK_LOOP",
        "response_type": "SINGLE_CHOICE",
        "required": False,
        "options": _FOUR_POINT_OPTIONS,
    },
    {
        "item_ref": "SELF_REGULATION_Q01",
        "response_type": "SINGLE_CHOICE",
        "required": False,
        "options": _FOUR_POINT_OPTIONS,
    },
    {
        "item_ref": "SELF_REGULATION_Q02",
        "response_type": "SINGLE_CHOICE",
        "required": False,
        "options": _FOUR_POINT_OPTIONS,
    },
    {
        "item_ref": "SELF_REGULATION_Q03",
        "response_type": "SINGLE_CHOICE",
        "required": False,
        "options": _FOUR_POINT_OPTIONS,
    },
)


def default_tool() -> AssessmentTool:
    """The real `FAMILY_SUPPORT_NEEDS` tool UI-02 submits against.

    v4: 18 items, matching the mobile screen's actual design and the
    construct-admission-reviewed item bank — see the module-level comment on
    `_FAMILY_SUPPORT_NEEDS_V4_ITEMS` above for what changed from the old v1
    3-option stub and what stays excluded on purpose.
    """
    return AssessmentTool(
        tool_ref="FAMILY_SUPPORT_NEEDS",
        version_no=4,
        title="家庭支持需要与服务偏好确认(含深挖题·批次2扩容)",
        purpose="了解家庭当前最需要支持的方向，并针对学习策略/元认知与自我管理支持追加观察题",
        schema_ref="family://assessment/FAMILY_SUPPORT_NEEDS/v4",
        items=[AssessmentToolItem(**item) for item in _FAMILY_SUPPORT_NEEDS_V4_ITEMS],
    )


@dataclass
class FakeAssessmentRepository:
    """Not thread-safe / not process-safe — intentional, this is a unit-test
    double, not a substitute for the real Postgres-backed repository.
    """

    families: set[str] = field(default_factory=set)
    tenant_family_bindings: set[tuple[str, str]] = field(default_factory=set)
    # (family_id, actor_id) -> a successful legacy `CreateFamily` audit exists.
    # Port of the `assertFamilyManagePermission` pass condition #1.
    create_family_audit: set[tuple[str, str]] = field(default_factory=set)
    # (family_id, person_id) -> role, for ACTIVE family_memberships rows.
    # Port of the `assertFamilyManagePermission` pass condition #2.
    family_memberships: dict[tuple[str, str], str] = field(default_factory=dict)
    consents: set[tuple[str, str, str]] = field(
        default_factory=set
    )  # (family_id, subject_person_id, purpose)
    subjects: dict[str, list[dict]] = field(
        default_factory=dict
    )  # family_id -> [{person_id, display_name, consent_granted}]
    tools: dict[tuple[str, int], AssessmentTool] = field(default_factory=dict)
    tenant_allowed_pages: dict[str, set[str]] = field(default_factory=dict)
    sessions: dict[str, AssessmentSession] = field(default_factory=dict)
    operations: dict[tuple[str, str, str, str], dict] = field(
        default_factory=dict
    )  # (tenant,family,action,key) -> {request_hash, response_body}
    audit_log: list[dict] = field(default_factory=list)
    read_audit_events: list[AuditEvent] = field(default_factory=list)
    outbox: list[dict] = field(default_factory=list)
    growth_intents: dict[str, dict] = field(default_factory=dict)  # source_ref -> intent
    hypothesis_decisions: dict[tuple[str, str, str, str], dict] = field(default_factory=dict)
    need_types: dict[str, dict] = field(default_factory=dict)  # focus_ref -> need type row

    def seed_family(self, tenant_id: str, family_id: str) -> None:
        self.families.add(family_id)
        self.tenant_family_bindings.add((tenant_id, family_id))
        self.tenant_allowed_pages.setdefault(tenant_id, set()).update({"UI-01", "UI-02", "UI-03"})
        # Keyed off the tool's own `version_no`, not a hardcoded `1` — a
        # session created against `default_tool()` records that tool's real
        # `version_no` (currently 4, see `default_tool()`'s docstring), and
        # `load_tool_version` looks the session up by that exact number. A
        # hardcoded key here previously left `("FAMILY_SUPPORT_NEEDS", 1)` as
        # the only registered version regardless of what `default_tool()`
        # actually returned, so every `save_response`/`submit` after v4
        # landed failed with `assessment_tool_version_not_found`.
        tool = default_tool()
        self.tools[(tool.tool_ref, tool.version_no)] = tool
        # Every existing test drives commands/queries as actor `"actor-1"`
        # without separately seeding a membership — grant it OWNER_GUARDIAN
        # here (mirrors a family always having its creator as an
        # OWNER_GUARDIAN member) so `assert_tenant_family_scope`'s newly
        # ported RBAC check doesn't regress every pre-existing test.
        # Tests exercising the "no manage permission" path use
        # `grant_family_manage_permission` / a bare actor id instead.
        self.grant_family_manage_permission(family_id, DEFAULT_TEST_ACTOR, role="OWNER_GUARDIAN")

    def grant_family_manage_permission(
        self, family_id: str, person_id: str, role: str = "OWNER_GUARDIAN"
    ) -> None:
        """Port of an ACTIVE `family_memberships` row with a manage-eligible
        role — the fake-repository equivalent of pass condition #2 in
        `assertFamilyManagePermission` (family-permission.ts).
        """
        self.family_memberships[(family_id, person_id)] = role

    def seed_create_family_audit(self, family_id: str, actor_id: str) -> None:
        """Port of a SUCCESS `CreateFamily` `audit_logs` row — the fake
        equivalent of pass condition #1 (legacy creator) in
        `assertFamilyManagePermission`.
        """
        self.create_family_audit.add((family_id, actor_id))

    def seed_subject(
        self, family_id: str, person_id: str, display_name: str, consent_granted: bool = True
    ) -> None:
        self.subjects.setdefault(family_id, []).append(
            {
                "person_id": person_id,
                "display_name": display_name,
                "consent_granted": consent_granted,
            }
        )
        if consent_granted:
            self.consents.add((family_id, person_id, "ASSESSMENT"))

    def seed_need_type(
        self,
        focus_ref: str,
        need_type_ref: str,
        title: str,
        description: str,
        capability_keys: list[str],
    ) -> None:
        self.need_types[focus_ref] = {
            "need_type_ref": need_type_ref,
            "version_no": 1,
            "title": title,
            "description": description,
            "required_capability_keys": capability_keys,
        }

    async def assert_tenant_family_scope(
        self, tenant_id: str, family_id: str, actor_id: str
    ) -> None:
        if (tenant_id, family_id) not in self.tenant_family_bindings:
            raise AssessmentForbiddenError("tenant_family_scope_denied")

        # Port of `assertFamilyManagePermission` — same two pass conditions,
        # OR'd, as the real repository's SQL. See `seed_family` for why the
        # default test actor is pre-granted.
        if (family_id, actor_id) in self.create_family_audit:
            return
        if self.family_memberships.get((family_id, actor_id)) in FAMILY_MANAGE_ROLES:
            return
        raise AssessmentForbiddenError("actor_has_family_manage_permission")

    async def assert_subject_consent(
        self, family_id: str, subject_person_id: str, purpose: str
    ) -> None:
        if (family_id, subject_person_id, purpose) not in self.consents:
            raise AssessmentForbiddenError("assessment_subject_or_consent_unavailable")

    async def load_active_tool(self, tool_ref: str) -> AssessmentTool | None:
        versions = [tool for (ref, _), tool in self.tools.items() if ref == tool_ref]
        return max(versions, key=lambda tool: tool.version_no) if versions else None

    async def load_tool_version(self, tool_ref: str, version_no: int) -> AssessmentTool:
        tool = self.tools.get((tool_ref, version_no))
        if tool is None:
            raise AssessmentNotFoundError("assessment_tool_version_not_found")
        return tool

    async def load_assessable_subjects(self, family_id: str) -> list[dict]:
        return list(self.subjects.get(family_id, []))

    async def load_recent_sessions(
        self, tenant_id: str, family_id: str, limit: int = 10
    ) -> list[AssessmentSession]:
        matches = [session for session in self.sessions.values() if session.family_id == family_id]
        matches.sort(key=lambda session: session.started_at, reverse=True)
        return matches[:limit]

    async def load_session(self, family_id: str, session_id: str) -> AssessmentSession:
        session = self.sessions.get(session_id)
        if session is None or session.family_id != family_id:
            raise AssessmentNotFoundError("assessment_session_not_found")
        return session

    async def load_session_for_update(
        self, family_id: str, tenant_id: str, session_id: str
    ) -> AssessmentSession:
        return await self.load_session(family_id, session_id)

    async def find_in_progress_session(
        self, tenant_id, family_id, subject_person_id, tool_ref, tool_version
    ) -> str | None:
        for session in self.sessions.values():
            if (
                session.family_id == family_id
                and session.subject_person_id == subject_person_id
                and session.tool_ref == tool_ref
                and session.tool_version == tool_version
                and session.status == AssessmentSessionStatus.IN_PROGRESS
            ):
                return session.assessment_session_id
        return None

    async def insert_session(
        self, tenant_id, family_id, subject_person_id, tool_ref, tool_version, started_by
    ) -> str:
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = AssessmentSession(
            assessment_session_id=session_id,
            family_id=family_id,
            subject_person_id=subject_person_id,
            tool_ref=tool_ref,
            tool_version=tool_version,
            status=AssessmentSessionStatus.IN_PROGRESS,
            started_at=datetime.now(UTC),
            submitted_at=None,
            row_version=1,
            responses=[],
        )
        return session_id

    async def upsert_response(
        self, session_id, item_ref, response_type, response_value, actor_id
    ) -> None:
        session = self.sessions[session_id]
        previous = next((r for r in session.responses if r.item_ref == item_ref), None)
        session.responses = [r for r in session.responses if r.item_ref != item_ref]
        session.responses.append(
            AssessmentResponse(
                assessment_response_id=str(uuid.uuid4()),
                item_ref=item_ref,
                response_type=response_type,
                response_value=response_value,
                revision=(previous.revision if previous else 0) + 1,
                captured_at=datetime.now(UTC),
            )
        )
        session.row_version += 1

    async def mark_session_submitted(self, session_id: str) -> None:
        session = self.sessions[session_id]
        session.status = AssessmentSessionStatus.SUBMITTED
        session.submitted_at = datetime.now(UTC)
        session.row_version += 1

    async def insert_assessment_evidence(
        self, family_id: str, session_id: str, payload: dict
    ) -> str:
        evidence_id = str(uuid.uuid4())
        self._evidence = getattr(self, "_evidence", {})
        self._evidence[evidence_id] = {
            "family_id": family_id,
            "session_id": session_id,
            "payload": payload,
        }
        self._evidence_by_session = getattr(self, "_evidence_by_session", {})
        self._evidence_by_session[session_id] = evidence_id
        return evidence_id

    async def tenant_allows_page(self, tenant_id: str, page_id: str) -> bool:
        return page_id in self.tenant_allowed_pages.get(tenant_id, set())

    async def subject_has_active_consent(
        self, family_id: str, subject_person_id: str, purpose: str
    ) -> bool:
        return (family_id, subject_person_id, purpose) in self.consents

    async def record_read_access(
        self,
        *,
        tenant_id: str,
        family_id: str,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        subject_person_id: str,
        accessed_fields: tuple[str, ...],
        access_purpose: str,
        reason: str,
        correlation_id: str,
        approval_ref: str,
    ) -> None:
        self.read_audit_events.append(
            AuditEvent(
                actor_id=actor_id,
                tenant_id=tenant_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                reason=reason,
                correlation_id=correlation_id,
                action_kind=AuditActionKind.READ,
                subject_person_id=subject_person_id,
                subject_is_minor=True,
                accessed_fields=accessed_fields,
                access_purpose=access_purpose,
                approval_ref=approval_ref,
            )
        )

    async def lock_operation(
        self, tenant_id: str, family_id: str, action: str, idempotency_key: str
    ) -> None:
        return None  # advisory-lock semantics only meaningful against real Postgres

    async def load_operation_replay(
        self, tenant_id, family_id, action, idempotency_key, request_hash
    ) -> dict | None:
        key = (tenant_id, family_id, action, idempotency_key)
        record = self.operations.get(key)
        if record is None:
            return None
        if record["request_hash"] != request_hash:
            raise AssessmentConflictError("idempotency_key_payload_mismatch")
        return record["response_body"]

    async def persist_operation(
        self,
        tenant_id,
        family_id,
        session_id,
        actor_id,
        action,
        request_hash,
        receipt,
        correlation_id,
        idempotency_key,
    ) -> None:
        self.operations[(tenant_id, family_id, action, idempotency_key)] = {
            "request_hash": request_hash,
            "response_body": receipt,
        }

    async def write_audit_and_outbox(
        self,
        family_id,
        actor_id,
        session_id,
        action,
        event_name,
        receipt,
        correlation_id,
        idempotency_key,
        source,
    ) -> None:
        self.audit_log.append(
            {
                "family_id": family_id,
                "actor_id": actor_id,
                "action": action,
                "resource_id": session_id,
                "correlation_id": correlation_id,
            }
        )
        self.outbox.append(
            {
                "aggregate_id": session_id,
                "event_name": event_name,
                "correlation_id": correlation_id,
                "payload": receipt,
            }
        )

    async def load_hypothesis_evidence(
        self, family_id, tenant_id, session_id=None
    ) -> GrowthHypothesisEvidence | None:
        candidates = [
            session
            for session in self.sessions.values()
            if session.family_id == family_id
            and session.status == AssessmentSessionStatus.SUBMITTED
            and (family_id, session.subject_person_id, "ASSESSMENT") in self.consents
            and (session_id is None or session.assessment_session_id == session_id)
        ]
        if not candidates:
            return None
        session = max(candidates, key=lambda s: s.submitted_at or datetime.min.replace(tzinfo=UTC))
        focus_response = next((r for r in session.responses if r.item_ref == "FOCUS"), None)
        if focus_response is None:
            return None
        need_type = self.need_types.get(str(focus_response.response_value))
        if need_type is None:
            return None
        evidence_id = getattr(self, "_evidence_by_session", {}).get(session.assessment_session_id)
        if evidence_id is None:
            return None
        subject = next(
            (
                s
                for s in self.subjects.get(family_id, [])
                if s["person_id"] == session.subject_person_id
            ),
            None,
        )
        return GrowthHypothesisEvidence(
            assessment_session_id=session.assessment_session_id,
            subject_person_id=session.subject_person_id,
            subject_display_name=subject["display_name"] if subject else "UNKNOWN",
            submitted_at=session.submitted_at,
            tool_ref=session.tool_ref,
            tool_version=session.tool_version,
            assessment_response_id=focus_response.assessment_response_id,
            focus_ref=str(focus_response.response_value),
            assessment_evidence_id=evidence_id,
            need_type_ref=need_type["need_type_ref"],
            need_type_version=need_type["version_no"],
            title=need_type["title"],
            description=need_type["description"],
            required_capability_keys=need_type["required_capability_keys"],
            response_set=[
                {
                    "item_ref": r.item_ref,
                    "response_type": r.response_type,
                    "response_value": r.response_value,
                }
                for r in session.responses
            ],
        )

    async def load_or_create_growth_intent(
        self,
        *,
        family_id,
        subject_person_id,
        need_type,
        goal_text,
        required_capability_keys,
        confirmed_by,
        source_ref,
        evidence_refs,
    ) -> dict:
        existing = self.growth_intents.get(source_ref)
        if existing is not None:
            return existing
        intent = {
            "intent_id": str(uuid.uuid4()),
            "family_id": family_id,
            "subject_person_id": subject_person_id,
            "confirmed_by": confirmed_by,
            "need_type": need_type,
            "title": self.need_types.get(need_type, {}).get("title", "家庭成长方向"),
            "goal_text": goal_text,
            "description": goal_text,
            "status": "OPEN",
            "required_capability_keys": required_capability_keys,
            "evidence_refs": evidence_refs,
            "boundary": "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME",
        }
        self.growth_intents[source_ref] = intent
        return intent

    async def lock_hypothesis_decision(
        self, tenant_id: str, family_id: str, hypothesis_ref: str
    ) -> None:
        return None

    async def load_hypothesis_decision_replay(
        self, tenant_id, family_id, decision_type, idempotency_key
    ) -> dict | None:
        return self.hypothesis_decisions.get((tenant_id, family_id, decision_type, idempotency_key))

    async def persist_hypothesis_decision(
        self,
        *,
        tenant_id,
        family_id,
        session_id,
        hypothesis_ref,
        decision_type,
        actor_id,
        intent_id,
        idempotency_key,
        request_hash,
        receipt,
        correlation_id,
    ) -> None:
        self.hypothesis_decisions[(tenant_id, family_id, decision_type, idempotency_key)] = {
            "request_hash": request_hash,
            "response_body": receipt,
        }
