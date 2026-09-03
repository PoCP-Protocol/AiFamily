from backend.intelligence.experience.family_problem_understanding_contract import (
    FamilyConversationTurn,
)
from backend.intelligence.experience.family_problem_understanding_knowledge import (
    FamilyUnderstandingKnowledgeRetriever,
)
from backend.intelligence.experience.family_problem_understanding_preparation import (
    FamilyProblemUnderstandingPreparation,
    FamilyProblemUnderstandingPreparer,
)
from backend.intelligence.knowledge.contracts import KnowledgeClaim, KnowledgeSource
from backend.intelligence.knowledge.registry import KnowledgeRegistry
from backend.intelligence.model_gateway.contracts import MediaInput
from backend.packages.contracts.evidence import Provenance


def _turn(kind: str, input_ref: str, text: str) -> FamilyConversationTurn:
    return FamilyConversationTurn(
        input_ref=input_ref,
        kind=kind,
        text=text,
        created_at="2026-09-03T12:00:00+08:00",
    )


def _preparer() -> FamilyProblemUnderstandingPreparer:
    source = KnowledgeSource(
        source_id="source:parenting-review",
        title="Parenting review",
        license_ref="license:reviewed",
        owner="knowledge-team",
        scope="shared",
        verified=True,
    )
    claim = KnowledgeClaim(
        claim_id="knowledge:task-transition:v1",
        text="学习任务开始困难可能与活动切换、控制感或任务难度有关。",
        source_id=source.source_id,
        provenance=Provenance(level="E6", source_ref=source.source_id),
        scope="family_growth",
        status="PUBLISHED",
        allowed_purposes=("family_problem_understanding",),
        metadata={
            "version": "1.0",
            "chunk_ref": "chunk:task-transition",
            "applicability": "家庭学习任务开始阶段",
            "limitations": ("不能据单次表达判断孩子能力",),
            "keywords": ("作业", "开始", "切换", "选择"),
        },
    )
    registry = KnowledgeRegistry(sources=(source,), claims=(claim,))
    return FamilyProblemUnderstandingPreparer(
        FamilyUnderstandingKnowledgeRetriever(registry, minimum_relevance=0.02)
    )


def test_preparation_uses_exact_same_evidence_for_generation_and_evaluation() -> None:
    concern = _turn("CONCERN", "input:concern", "孩子写作业前总是很难开始。")
    image = MediaInput(
        media_type="IMAGE",
        uri="media:authorized:desk",
        mime_type="image/jpeg",
        sha256="a" * 64,
    )
    prepared = _preparer().prepare(
        run_id="run:initial",
        data_class="SYNTHETIC",
        context_snapshot_ref="context:initial",
        conversation_turns=(concern,),
        knowledge_scope="family_growth",
        media_inputs=(image,),
        expected_signal_terms=(frozenset({"切换", "转换"}),),
        parent_felt_understood=0.8,
    )

    assert prepared.request.input_refs == ("input:concern", "media:authorized:desk")
    assert prepared.eval_spec.allowed_evidence_refs == frozenset(
        {"input:concern", "media:authorized:desk"}
    )
    assert prepared.eval_spec.allowed_knowledge_refs == frozenset({"knowledge:task-transition:v1"})
    assert prepared.request.payload["reviewed_knowledge"][0]["knowledge_ref"] == (
        "knowledge:task-transition:v1"
    )
    assert prepared.knowledge_selection.trace.selected_claim_ids == (
        "knowledge:task-transition:v1",
    )


def test_follow_up_preparation_requires_and_scores_real_hypothesis_revision() -> None:
    concern = _turn("CONCERN", "input:concern", "孩子写作业前总是很难开始。")
    follow_up = _turn(
        "FOLLOW_UP",
        "input:follow-up",
        "周末让他自己选先做哪科时通常能开始。",
    )
    prepared = _preparer().prepare(
        run_id="run:follow-up",
        data_class="SYNTHETIC",
        context_snapshot_ref="context:follow-up",
        conversation_turns=(concern, follow_up),
        knowledge_scope="family_growth",
        prior_run_id="run:initial",
        prior_hypothesis_statements=("孩子可能缺乏学习动力。",),
    )

    assert prepared.request.payload["prior_run_id"] == "run:initial"
    assert prepared.eval_spec.requires_revision is True
    assert prepared.eval_spec.prior_hypothesis_statements == ("孩子可能缺乏学习动力。",)


def test_preparation_invariant_rejects_mismatched_evaluation_refs() -> None:
    concern = _turn("CONCERN", "input:concern", "孩子写作业前总是很难开始。")
    prepared = _preparer().prepare(
        run_id="run:initial",
        data_class="SYNTHETIC",
        context_snapshot_ref="context:initial",
        conversation_turns=(concern,),
        knowledge_scope="family_growth",
    )

    try:
        FamilyProblemUnderstandingPreparation(
            request=prepared.request,
            knowledge_selection=prepared.knowledge_selection,
            eval_spec=prepared.eval_spec.__class__(
                allowed_evidence_refs=frozenset({"input:invented"}),
                allowed_knowledge_refs=prepared.eval_spec.allowed_knowledge_refs,
            ),
        )
    except ValueError as exc:
        assert "evidence refs must match" in str(exc)
    else:
        raise AssertionError("mismatched evaluation refs must fail closed")
