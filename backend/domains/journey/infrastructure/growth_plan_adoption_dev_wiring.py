"""Dev/test-only composition for the growth-plan adoption vertical slice.

No production adapter exists yet for either
`GrowthPlanDraftReader` (a durable store of AI-generated, human-validated
growth-plan drafts) or `AdoptedGrowthPlanRepository` (durable, idempotent
adoption records). This module exists so the route is actually callable in
dev/test — matching the posture used elsewhere in this composition root
(e.g. `family_need`, `course_content`): the same route, errors and Named
Action gate as production, with a synthetic identity/storage seam that must
never be reachable outside dev/test.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from backend.platform.audit import AuditEvent, AuditRecorder

from ..api.growth_plan_adoption_routes import GrowthPlanAuthenticationError
from ..application.growth_plan_adoption import (
    AdoptedGrowthPlan,
    AdoptedGrowthPlanRepository,
    GrowthPlanActor,
    GrowthPlanAdoptionService,
    GrowthPlanDraftReader,
    GuardianGrowthPlanPolicy,
    ValidatedGrowthPlanDraft,
)
from ..domain.errors import JourneyConflictError


@dataclass
class InMemoryGrowthPlanDraftStore(GrowthPlanDraftReader):
    """Holds validated drafts keyed by (tenant, family); dev/test seeds it."""

    drafts: dict[tuple[str, str], ValidatedGrowthPlanDraft]

    def __init__(
        self,
        intent_source: Callable[[str, str], dict[str, Any] | None] | None = None,
    ) -> None:
        self.drafts = {}
        self._intent_source = intent_source

    def put(self, draft: ValidatedGrowthPlanDraft) -> None:
        self.drafts[(draft.tenant_id, draft.family_id)] = draft

    async def load_validated_draft(
        self, *, tenant_id: str, family_id: str, draft_ref: str, version: int
    ) -> ValidatedGrowthPlanDraft | None:
        draft = self.drafts.get((tenant_id, family_id))
        if draft is not None:
            if draft.draft_ref != draft_ref or draft.version != version:
                return None
            return draft
        if self._intent_source is None:
            return None
        projected = _draft_from_confirmed_intent(
            self._intent_source(tenant_id, family_id),
            tenant_id=tenant_id,
            family_id=family_id,
        )
        if projected is None or projected.draft_ref != draft_ref or projected.version != version:
            return None
        return projected

    async def load_latest_validated_draft(
        self, *, tenant_id: str, family_id: str
    ) -> ValidatedGrowthPlanDraft | None:
        draft = self.drafts.get((tenant_id, family_id))
        if draft is not None:
            return draft
        if self._intent_source is None:
            return None
        intent = self._intent_source(tenant_id, family_id)
        return _draft_from_confirmed_intent(intent, tenant_id=tenant_id, family_id=family_id)


@dataclass
class InMemoryAdoptedGrowthPlanRepository(AdoptedGrowthPlanRepository):
    """Idempotent, family-scoped, process-local adoption store.

    R6 requires the AuditEvent produced by the same write path that changes
    authoritative state to actually be recorded, not merely constructed. This
    adapter has no database transaction to piggy-back on, so it keeps its own
    `AuditRecorder` buffer and appends to it inside `adopt_once` -- the single
    write path -- so "plan stored" and "audit event recorded" cannot diverge.
    A replayed (idempotent) call intentionally does NOT record a second event:
    no new state was written, so R6 has nothing new to attest to.
    """

    current: dict[tuple[str, str], AdoptedGrowthPlan]
    receipts: dict[str, tuple[str, AdoptedGrowthPlan]]
    audit_recorder: AuditRecorder

    def __init__(self, audit_recorder: AuditRecorder | None = None) -> None:
        self.current = {}
        self.receipts = {}
        self.audit_recorder = audit_recorder if audit_recorder is not None else AuditRecorder()

    async def get_current(self, *, tenant_id: str, family_id: str) -> AdoptedGrowthPlan | None:
        return self.current.get((tenant_id, family_id))

    async def adopt_once(
        self,
        *,
        plan: AdoptedGrowthPlan,
        idempotency_key: str,
        request_fingerprint: str,
        audit_event: AuditEvent,
    ) -> tuple[AdoptedGrowthPlan, bool, bool]:
        receipt = self.receipts.get(idempotency_key)
        if receipt is not None:
            stored_fingerprint, stored_plan = receipt
            if stored_fingerprint != request_fingerprint:
                raise JourneyConflictError("idempotency_conflict")
            return stored_plan, False, True
        key = (plan.tenant_id, plan.family_id)
        existing = self.current.get(key)
        if existing is not None and existing.draft_ref != plan.draft_ref:
            raise JourneyConflictError("active_growth_plan_already_exists")
        stored = existing or plan
        self.current[key] = stored
        self.receipts[idempotency_key] = (request_fingerprint, stored)
        if existing is None:
            self.audit_recorder.record(audit_event)
        return stored, existing is None, False


def build_dev_growth_plan_adoption_service(
    draft_store: InMemoryGrowthPlanDraftStore,
    repository: InMemoryAdoptedGrowthPlanRepository,
) -> GrowthPlanAdoptionService:
    return GrowthPlanAdoptionService(
        draft_reader=draft_store,
        repository=repository,
        policy=GuardianGrowthPlanPolicy(),
    )


def _draft_from_confirmed_intent(
    intent: dict[str, Any] | None, *, tenant_id: str, family_id: str
) -> ValidatedGrowthPlanDraft | None:
    """Project the confirmed assessment intent into a reviewable dev draft.

    This is deliberately a deterministic development adapter. It proves the
    cross-domain seam (UI-03 Guardian decision -> UI-04 draft readback) without
    claiming that an AI runtime or durable growth-plan draft store exists.
    """
    if not intent or intent.get("status") != "OPEN":
        return None
    intent_id = str(intent.get("intent_id", ""))
    subject_ref = str(intent.get("subject_person_id", ""))
    guardian_ref = str(intent.get("confirmed_by", ""))
    if not intent_id or not subject_ref or not guardian_ref:
        return None
    title = str(intent.get("title") or "从一个双方都能接受的步骤开始")
    goal_text = str(intent.get("goal_text") or intent.get("description") or title)
    output: dict[str, Any] = {
        "result_status": "PLAN_DRAFT",
        "title": title,
        "family_goal": {
            "statement": goal_text,
            "observable_signs": [
                "成人能说清今晚要尝试的一个步骤",
                "孩子可以表达同意、暂停或不同意",
            ],
            "evidence_refs": [f"growth-intent:{intent_id}"],
        },
        "why_this_plan": (
            "先把目标缩小到一次可观察、可拒绝、可复盘的家庭行动；是否继续由家长和孩子共同决定。"
        ),
        "duration": {"days": 7, "rationale": "先用一周观察行动是否适合你们，而不是预设长期效果。"},
        "stages": [
            {
                "stage_id": "START_SMALL",
                "title": "先选一个小步骤",
                "purpose": "把今晚的困扰变成双方都能接受的下一步。",
                "practices": [
                    {
                        "practice_id": "P1",
                        "description": "成人先说出目标，再邀请孩子选择、暂停或拒绝这一步。",
                        "actor": "FAMILY",
                        "cadence": "今晚一次",
                        "effort": "5分钟",
                        "stop_condition": "任何一方不愿继续",
                        "repair_option": "停下来，改为明天再谈或寻求人工支持。",
                    }
                ],
                "child_participation_mode": "ASSENT_REQUIRED",
                "signals": [
                    {"signal_type": "OUTCOME", "description": "双方完成或共同修改了一个下一步"},
                    {
                        "signal_type": "PROTECTION",
                        "description": "孩子能表达不同意见且没有受到惩罚",
                    },
                    {"signal_type": "STOP", "description": "出现不安全、恐惧或明确拒绝时立即停止"},
                ],
                "reflection_question": "这一步让谁更容易开口了？谁还需要被听见？",
                "evidence_refs": [f"growth-intent:{intent_id}"],
                "knowledge_refs": ["AF-SUPPORT-01:mechanism-hypothesis"],
            },
            {
                "stage_id": "REFLECT_AND_ADJUST",
                "title": "一起回看",
                "purpose": "只记录真实发生的行动和感受，不把一次完成写成效果。",
                "practices": [
                    {
                        "practice_id": "P2",
                        "description": "成人和孩子分别说一句：哪里有帮助、哪里需要调整。",
                        "actor": "FAMILY",
                        "cadence": "本周一次",
                        "effort": "10分钟",
                        "stop_condition": "回看引发压力或争执升级",
                        "repair_option": "结束回看，保留不同意见，必要时转人工。",
                    }
                ],
                "child_participation_mode": "OPTIONAL",
                "signals": [
                    {
                        "signal_type": "OUTCOME",
                        "description": "家庭记录下一次愿意继续、修改或暂停的选择",
                    },
                    {"signal_type": "PROTECTION", "description": "退出和拒绝没有带来权益损失"},
                ],
                "reflection_question": "下次要继续、改小，还是先暂停？",
                "evidence_refs": [f"growth-intent:{intent_id}"],
                "knowledge_refs": ["AF-SUPPORT-01:repair-boundary"],
            },
        ],
        "adjustable_choices": [
            {
                "choice_id": "pace",
                "question": "这周更适合怎样开始？",
                "options": ["今晚试一次", "先观察两天", "暂时不安排"],
                "target_stage_ids": ["START_SMALL"],
            }
        ],
        "unknowns_to_watch": [
            "孩子是否愿意表达不同意见",
            "行动后是否减少冲突而不是增加沉默",
            "成人是否把建议当成必须完成的要求",
        ],
        "review_rhythm": {"frequency": "一周", "questions": ["继续、修改还是暂停？"]},
        "limitations": ["这是基于已确认方向生成的开发环境 Draft，不是诊断、事实或长期效果证明。"],
    }
    encoded = json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    draft_ref = f"dev-growth-draft:{intent_id}"
    now = datetime.now(UTC)
    return ValidatedGrowthPlanDraft(
        draft_ref=draft_ref,
        version=1,
        tenant_id=tenant_id,
        family_id=family_id,
        subject_refs=(guardian_ref, subject_ref),
        status="VALIDATED_DRAFT",
        model_run_ref=f"dev-deterministic:{intent_id}",
        provenance_ref=f"dev-provenance:{intent_id}",
        validation_receipt_ref=f"dev-human-gate:{intent_id}",
        validated_by="dev-human-gate",
        validated_at=now,
        content_sha256=digest,
        output=output,
    )


def build_dev_actor_resolver(
    identity_lookup: Any,
) -> Any:
    """Build a `resolve_actor` callable from the shared dev bearer-token identity.

    `identity_lookup` is `dev_wiring._identity`: it turns a bearer token into
    `{account_id, family_id}` using the same synthetic session state every
    other dev-wired domain uses, so a token minted by `dev_auth` resolves to
    the same family here as it does for Assessment/Journey/FamilyNeed.
    """

    async def resolve_actor(authorization: str | None, family_id: str) -> GrowthPlanActor:
        try:
            identity = identity_lookup(authorization)
        except Exception as error:  # noqa: BLE001 - re-raised as the router's own auth error
            raise GrowthPlanAuthenticationError() from error
        account_id = identity["account_id"]
        resolved_family_id = identity["family_id"]
        return GrowthPlanActor(
            actor_id=account_id,
            tenant_id=resolved_family_id,
            family_id=resolved_family_id,
            membership_ref=f"dev-membership:{account_id}",
            consent_ref=f"dev-consent:{account_id}",
            actor_type="GUARDIAN",
        )

    return resolve_actor


__all__ = [
    "InMemoryAdoptedGrowthPlanRepository",
    "InMemoryGrowthPlanDraftStore",
    "build_dev_actor_resolver",
    "build_dev_growth_plan_adoption_service",
]
