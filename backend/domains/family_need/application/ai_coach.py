"""family_need-side composition for the AI Coach capability.

This module owns exactly the part that must live in the domain: reading real
`FamilyNeed` (and, when present, `NeedProfile` / `SolutionDraft`) data through
the repository port and shaping it into the `family_context` payload the
generic coach in `backend.intelligence.experience.family_ai_coach` sends to
the model. It never fabricates a statement or outcome the family did not
provide, and it never imports a provider adapter directly (R7: all model
access goes through `ModelGateway`).
"""

from __future__ import annotations

import hashlib

from backend.domains.journey.application.outcome_loop import (
    ActionFactStatus,
    GrowthOutcomeLoop,
    OutcomeLoopSnapshot,
)
from backend.intelligence.experience.family_ai_coach import (
    CoachMemoryStore,
    CoachPerspective,
    coach_reply,
)
from backend.intelligence.model_gateway.gateway import ModelGateway

from ..application.ports import FamilyNeedRepositoryPort
from ..domain.errors import FamilyNeedNotFoundError
from ..domain.value_objects import DataClass as FamilyNeedDataClass

# family_need's DataClass and the Model Gateway's DataClass are deliberately
# separate vocabularies (one is the domain's PIPL classification of a need
# record, the other is the gateway's §16 admission classification), so the
# mapping is explicit rather than assumed string-identical. `PUBLIC` and
# `INTERNAL` need content map to `OPERATIONAL_TEXT` because neither carries a
# family or minor subject; `FAMILY_PRIVATE`/`SENSITIVE_PERSONAL_DATA` map to
# `FAMILY_PRIVATE_TEXT`; `MINOR_PERSONAL_DATA` maps 1:1 because PIPL 第28条
# treats it as its own coarse category (see `contracts.py`'s own docstring).
_GATEWAY_DATA_CLASS_BY_FAMILY_NEED_DATA_CLASS: dict[FamilyNeedDataClass, str] = {
    FamilyNeedDataClass.PUBLIC: "OPERATIONAL_TEXT",
    FamilyNeedDataClass.INTERNAL: "OPERATIONAL_TEXT",
    FamilyNeedDataClass.FAMILY_PRIVATE: "FAMILY_PRIVATE_TEXT",
    FamilyNeedDataClass.SENSITIVE_PERSONAL_DATA: "FAMILY_PRIVATE_TEXT",
    FamilyNeedDataClass.MINOR_PERSONAL_DATA: "MINOR_PERSONAL_DATA",
}


def _context_snapshot_ref(*, need_id: str, need_version: int, profile_id: str | None) -> str:
    """A deterministic, honest reference to the real data fed to the model.

    Not a fabricated identifier: it is derived from the actual need id/version
    (and profile id, when one exists) so the same underlying data always
    produces the same ref, and the ref can be used later to look the data back
    up for an audit — the same intent as `ContextBroker.snapshot_ref` without
    pulling in the full context-engine machinery this capability does not need.
    """

    identity = f"{need_id}:{need_version}:{profile_id or ''}"
    digest = hashlib.sha256(identity.encode()).hexdigest()[:32]
    return f"family-ai-coach-context:{digest}"


def summarize_growth_journey_for_coach(snapshot: OutcomeLoopSnapshot, *, limit: int = 5) -> str:
    """Turn the family's real journey action facts into a short Chinese
    summary for the coach's `family_context` — plain fact statements only
    (task_id prefix + status + day_number), never a fabricated feeling or
    interpretation.

    Recognised `task_id` prefixes (as actually written by
    `backend.domains.family_need.application.fulfillment`, see
    `test_need_fulfillment_e2e.py`):

    * ``course-completion:<course_id>`` — the family completed a course.
    * ``booking-service-record:<record_id>`` — a real-person service session
      was delivered.
    * ``family-confirmed-outcome:<fulfillment_ref>`` — the family itself
      confirmed whether a fulfilment actually helped.

    Returns `""` when the snapshot has no actions yet — a brand-new family
    with no history is not an error, it is simply nothing to summarize.
    """

    if not snapshot.actions:
        return ""
    recent = sorted(snapshot.actions, key=lambda action: action.recorded_at, reverse=True)[:limit]
    lines: list[str] = []
    for action in reversed(recent):
        completed = action.status is ActionFactStatus.COMPLETED
        if action.task_id.startswith("course-completion:"):
            course_id = action.task_id.split(":", 1)[1]
            verb = "完成过" if completed else f"参与过（状态：{action.status.value}）"
            lines.append(f"这个家庭{verb}课程《{course_id}》（第{action.day_number}天）。")
        elif action.task_id.startswith("booking-service-record:"):
            record_id = action.task_id.split(":", 1)[1]
            verb = (
                "完成过一次真人服务预约"
                if completed
                else f"有一次真人服务预约（状态：{action.status.value}）"
            )
            lines.append(f"这个家庭{verb}（记录：{record_id}，第{action.day_number}天）。")
        elif action.task_id.startswith("family-confirmed-outcome:"):
            ref = action.task_id.split(":", 1)[1]
            lines.append(
                f"这个家庭对一次服务/课程结果做过确认（关联：{ref}，第{action.day_number}天）。"
            )
        else:
            lines.append(
                f"这个家庭有一条成长记录：{action.task_id}（状态：{action.status.value}，"
                f"第{action.day_number}天）。"
            )
    return " ".join(lines)


async def build_family_context(
    repository: FamilyNeedRepositoryPort,
    *,
    tenant_id: str,
    family_id: str,
    need_id: str,
) -> tuple[dict, str, str, str, tuple[str, ...]]:
    """Assemble a real, non-fabricated context payload for one family need.

    Returns `(family_context, context_snapshot_ref, data_class,
    consent_version, subject_person_ids)`. `data_class` is the need's own
    recorded classification (`context.data_class` on the `NeedContext` the
    family/system already assigned when the need was captured) — the coach
    must send the model exactly the classification the data actually
    carries, never a value chosen for admission convenience.
    `consent_version`/`subject_person_ids` are the need's own recorded
    values, threaded through so the coach's cross-turn memory (see
    `request_coach_perspective`) is written under the same consent scope
    the family actually gave, never a hardcoded default. Raises
    `FamilyNeedNotFoundError` if the need does not exist or is out of scope
    — the coach must never run against invented data.
    """

    need = await repository.get_need(tenant_id=tenant_id, family_id=family_id, need_id=need_id)
    if need is None:
        raise FamilyNeedNotFoundError("family_need_not_found")

    context: dict = {
        "need_statement": need.statement,
        "desired_outcome": need.desired_outcome,
        "category": need.category.value,
        "emotional_gate": need.emotional_gate.value,
    }

    # There is no generic "list profiles/drafts for need_id" repository
    # method, so profile/solution-draft enrichment is an explicit opt-in step
    # (see `enrich_family_context_with_profile` /
    # `enrich_family_context_with_solution_draft`) rather than a lookup
    # attempted here and silently skipped on failure.
    snapshot_ref = _context_snapshot_ref(
        need_id=need.need_id, need_version=need.version, profile_id=None
    )
    gateway_data_class = _GATEWAY_DATA_CLASS_BY_FAMILY_NEED_DATA_CLASS[need.context.data_class]
    return (
        context,
        snapshot_ref,
        gateway_data_class,
        need.context.consent_version,
        need.context.subject_person_ids,
    )


async def enrich_family_context_with_profile(
    context: dict,
    repository: FamilyNeedRepositoryPort,
    *,
    tenant_id: str,
    family_id: str,
    profile_id: str,
) -> dict:
    """Optionally add `intervention_tier` when the caller already has a profile_id.

    Kept as an explicit opt-in step (rather than an implicit lookup inside
    `build_family_context`) because the need-only path is the common case and
    a profile does not exist for every need — the HTTP layer decides whether
    it has a `profile_id` to pass.
    """

    profile = await repository.get_profile(
        tenant_id=tenant_id, family_id=family_id, profile_id=profile_id
    )
    if profile is None:
        return context
    enriched = dict(context)
    enriched["intervention_tier"] = profile.intervention_tier.value
    enriched["urgency"] = profile.urgency.value
    return enriched


async def enrich_family_context_with_solution_draft(
    context: dict,
    repository: FamilyNeedRepositoryPort,
    *,
    tenant_id: str,
    family_id: str,
    draft_id: str,
) -> dict:
    """Optionally add matched supply component titles when a draft exists.

    Only component identifiers actually resolved by the domain are surfaced;
    nothing here invents a course/service title.
    """

    draft = await repository.get_solution_draft(
        tenant_id=tenant_id, family_id=family_id, draft_id=draft_id
    )
    if draft is None:
        return context
    enriched = dict(context)
    enriched["matched_components"] = [
        {"component_id": item.component_id, "shape": item.shape.value} for item in draft.components
    ]
    return enriched


def enrich_family_context_with_growth_journey(
    context: dict, outcome_loop: GrowthOutcomeLoop, *, tenant_id: str, family_id: str
) -> dict:
    """Add `growth_journey_summary` from the family's *real* journey history
    (`GrowthOutcomeLoop.snapshot`) — the Maven-style "the advocate remembers
    this family" piece: the coach sees what actually happened before, not
    just this conversation's own turns (`family_ai_coach.py`'s per-need
    memory already covers the latter).

    An empty summary (brand-new family, nothing recorded yet) still sets the
    key to `""` rather than omitting it, so a caller inspecting
    `family_context` never has to guess whether journey enrichment ran.
    """

    snapshot = outcome_loop.snapshot(tenant_id=tenant_id, family_id=family_id)
    enriched = dict(context)
    enriched["growth_journey_summary"] = summarize_growth_journey_for_coach(snapshot)
    return enriched


async def request_coach_perspective(
    gateway: ModelGateway,
    repository: FamilyNeedRepositoryPort,
    *,
    provider_id: str,
    tenant_id: str,
    family_id: str,
    need_id: str,
    parent_message: str,
    profile_id: str | None = None,
    draft_id: str | None = None,
    request_id: str | None = None,
    outcome_loop: GrowthOutcomeLoop | None = None,
    memory_store: CoachMemoryStore | None = None,
) -> CoachPerspective:
    """The one call the HTTP route needs: real context in, governed draft out.

    `outcome_loop` is optional so the minimal signature (no journey wiring)
    still works for callers/tests that do not care about growth-journey
    continuity; when supplied, the family's real action-fact history is
    folded into `family_context` before the model call (see
    `enrich_family_context_with_growth_journey`).

    `memory_store` is optional cross-turn conversation memory (see
    `coach_reply`'s own docstring): when supplied, this need's own recorded
    `consent_version`/`subject_person_ids` are threaded through so the turn
    is written under the family's real consent scope, never a hardcoded
    default — omitting `memory_store` keeps the previous single-turn
    behaviour unchanged.
    """

    (
        context,
        context_snapshot_ref,
        data_class,
        consent_version,
        subject_person_ids,
    ) = await build_family_context(
        repository, tenant_id=tenant_id, family_id=family_id, need_id=need_id
    )
    if profile_id is not None:
        context = await enrich_family_context_with_profile(
            context, repository, tenant_id=tenant_id, family_id=family_id, profile_id=profile_id
        )
    if draft_id is not None:
        context = await enrich_family_context_with_solution_draft(
            context, repository, tenant_id=tenant_id, family_id=family_id, draft_id=draft_id
        )
    if outcome_loop is not None:
        context = enrich_family_context_with_growth_journey(
            context, outcome_loop, tenant_id=tenant_id, family_id=family_id
        )

    return await coach_reply(
        gateway,
        provider_id=provider_id,
        family_context=context,
        parent_message=parent_message,
        tenant_id=tenant_id,
        family_id=family_id,
        context_snapshot_ref=context_snapshot_ref,
        data_class=data_class,
        request_id=request_id,
        memory_store=memory_store,
        need_id=need_id,
        subject_ids=subject_person_ids,
        consent_version=consent_version,
    )
