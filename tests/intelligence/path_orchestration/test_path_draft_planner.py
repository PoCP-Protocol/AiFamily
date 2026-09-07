import pytest

from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.path_orchestration.contracts import (
    CapabilityCandidate,
    FamilyPathContext,
    PathDraftEvidence,
    PathDraftScopeError,
    PathFeedbackSignal,
)
from backend.intelligence.path_orchestration.planner import ContextDrivenPathDraftPlanner


class ContextPort:
    def __init__(self, context: FamilyPathContext):
        self.context = context

    async def read(self, *, scope, need_id):
        assert need_id == self.context.need_id
        return self.context


class MismatchedContextPort(ContextPort):
    async def read(self, *, scope, need_id):
        return self.context


class CandidatePort:
    def __init__(self, candidates):
        self.candidates = tuple(candidates)

    async def list_candidates(self, *, scope, context):
        return self.candidates


def scope(*, family_id: str = "family-a", subject_id: str = "child-a") -> ContextScope:
    return ContextScope(
        tenant_id="tenant-1",
        region_id="CN",
        family_id=family_id,
        subject_ids=(subject_id,),
        purpose="growth_tracking",
        consent_version="consent-v1",
        consent_granted=True,
        data_class=DataClass.MINOR_PERSONAL_DATA,
        locale="zh-CN",
        deletion_ref="deletion-1",
        correlation_id="corr-1",
        causation_id="cause-1",
    )


def evidence(ref: str) -> PathDraftEvidence:
    return PathDraftEvidence(ref, "family_need", "v1", "guardian-confirmed context")


def context(
    *, family_id="family-a", subject_id="child-a", tags=(), unknowns=(), feedback_signals=()
):
    return FamilyPathContext(
        tenant_id="tenant-1",
        family_id=family_id,
        need_id=f"need-{family_id}",
        need_statement="家庭希望获得更适合当前情境的支持",
        subject_ids=(subject_id,),
        context_snapshot_ref=f"snapshot-{family_id}",
        evidence=(evidence(f"need-evidence-{family_id}"),),
        fit_tags=frozenset(tags),
        unknowns=tuple(unknowns),
        feedback_refs=(f"feedback-{family_id}",),
        feedback_signals=tuple(feedback_signals),
    )


def candidate(ref: str, tag: str) -> CapabilityCandidate:
    return CapabilityCandidate(
        capability_ref=ref,
        title=ref,
        description=f"支持 {tag}",
        fit_tags=frozenset({tag}),
        evidence=(evidence(f"knowledge-{ref}"),),
    )


@pytest.mark.asyncio
async def test_different_family_contexts_choose_different_candidate_sequences():
    candidates = (
        candidate("capability:study-start", "study_start"),
        candidate("capability:repair-dialogue", "repair_dialogue"),
    )
    planner_a = ContextDrivenPathDraftPlanner(
        ContextPort(context(tags=("study_start",))), CandidatePort(candidates)
    )
    planner_b = ContextDrivenPathDraftPlanner(
        ContextPort(context(family_id="family-b", subject_id="child-b", tags=("repair_dialogue",))),
        CandidatePort(candidates),
    )

    draft_a = await planner_a.draft(scope=scope(), need_id="need-family-a")
    draft_b = await planner_b.draft(
        scope=scope(family_id="family-b", subject_id="child-b"), need_id="need-family-b"
    )

    assert [node.capability_ref for node in draft_a.nodes] == ["capability:study-start"]
    assert [node.capability_ref for node in draft_b.nodes] == ["capability:repair-dialogue"]
    assert draft_a.may_mutate_business_state is False
    assert draft_a.feedback_refs == ("feedback-family-a",)
    assert "candidate_evidence:knowledge-capability:study-start" in draft_a.selected_reasons[
        "capability:study-start"
    ]


@pytest.mark.asyncio
async def test_unknown_context_returns_clarification_without_selecting_action():
    planner = ContextDrivenPathDraftPlanner(
        ContextPort(context(tags=(), unknowns=("冲突通常发生在什么时候？",))),
        CandidatePort((candidate("capability:study-start", "study_start"),)),
    )

    draft = await planner.draft(scope=scope(), need_id="need-family-a")

    assert draft.nodes == ()
    assert draft.clarifying_questions == (
        "冲突通常发生在什么时候？",
        "这件事最希望先看到哪一种变化？",
    )
    assert draft.status == "DRAFT"


@pytest.mark.asyncio
async def test_cross_family_context_is_rejected_before_draft_creation():
    planner = ContextDrivenPathDraftPlanner(
        ContextPort(context(family_id="family-b", subject_id="child-b", tags=("study_start",))),
        CandidatePort((candidate("capability:study-start", "study_start"),)),
    )

    with pytest.raises(PathDraftScopeError, match="scope mismatch"):
        await planner.draft(scope=scope(), need_id="need-family-b")


@pytest.mark.asyncio
async def test_context_port_cannot_return_a_different_need_in_the_same_family():
    planner = ContextDrivenPathDraftPlanner(
        MismatchedContextPort(context(tags=("study_start",))),
        CandidatePort((candidate("capability:study-start", "study_start"),)),
    )

    with pytest.raises(PathDraftScopeError, match="need mismatch"):
        await planner.draft(scope=scope(), need_id="need-family-a-other")


@pytest.mark.asyncio
async def test_guardian_rejection_changes_the_next_draft():
    candidates = (
        candidate("capability:study-start", "study_start"),
        candidate("capability:repair-dialogue", "repair_dialogue"),
    )
    feedback = PathFeedbackSignal(
        feedback_ref="feedback-family-a-2",
        decision="REJECT",
        reason="先修复关系，不从任务设计开始。",
        excluded_capability_refs=("capability:study-start",),
    )
    planner = ContextDrivenPathDraftPlanner(
        ContextPort(
            context(
                tags=("study_start", "repair_dialogue"),
                feedback_signals=(feedback,),
            )
        ),
        CandidatePort(candidates),
    )

    draft = await planner.draft(scope=scope(), need_id="need-family-a")

    assert [node.capability_ref for node in draft.nodes] == ["capability:repair-dialogue"]
    assert draft.feedback_signals == (feedback,)
