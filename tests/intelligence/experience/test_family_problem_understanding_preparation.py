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
from backend.intelligence.experience.run_http import InMemoryExperienceRunLedger, RunScope
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


def _prior_draft() -> dict[str, object]:
    return {
        "understanding": {
            "lived_experience": "家长正在经历反复催促。",
            "central_tension": "开始时间与孩子节奏之间有拉扯。",
            "care_intent": "家长希望孩子减少受挫。",
        },
        "hypotheses": [
            {
                "hypothesis_id": "H1",
                "statement": "孩子可能缺乏学习动力。",
                "rationale": "开始前出现拖延。",
                "evidence": [
                    {
                        "source_type": "PARENT_TEXT",
                        "source_ref": "input:concern",
                        "observation": "写作业前难开始",
                    }
                ],
                "knowledge_refs": ["knowledge:task-transition:v1"],
                "confidence": "LOW",
                "disconfirming_evidence_needed": "了解可以顺利开始的例外。",
            }
        ],
        "unknowns": [
            {
                "unknown_id": "U1",
                "description": "是否存在顺利开始的例外",
                "why_it_matters": "可检验动力解释",
                "related_hypothesis_ids": ["H1"],
            }
        ],
        "follow_up_questions": [
            {
                "question_id": "Q1",
                "question": "什么时候更容易开始？",
                "purpose": "寻找例外",
                "answers_unknown_ids": ["U1"],
            }
        ],
        "strengths": [
            {
                "statement": "家长持续观察孩子。",
                "evidence_refs": ["input:concern"],
                "why_it_matters": "提供了理解变化的基础。",
            }
        ],
        "desired_change": {
            "statement": "减少开始前冲突。",
            "basis": "EXPLICIT",
            "observable_signs": ["催促减少"],
            "confirmation_question": "这是你期待的变化吗？",
        },
        "limitations": ["目前只有一次家长表达。"],
    }


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
    scope = RunScope("tenant:1", "family:1", ("guardian:1", "child:1"))
    ledger = InMemoryExperienceRunLedger()
    prior_replay = ledger.create_draft(
        scope=scope,
        run_id="run:initial",
        request_ref="request:initial",
        draft_payload=_prior_draft(),
        idempotency_key="create:initial",
    )
    prepared = _preparer().prepare_follow_up_from_replay(
        scope=scope,
        prior_replay=prior_replay,
        run_id="run:follow-up",
        data_class="SYNTHETIC",
        context_snapshot_ref="context:follow-up",
        conversation_turns=(concern, follow_up),
        knowledge_scope="family_growth",
    )

    assert prepared.request.payload["prior_run_id"] == "run:initial"
    assert prepared.request.payload["prior_draft"] == _prior_draft()
    assert prepared.eval_spec.requires_revision is True
    assert prepared.eval_spec.prior_hypothesis_statements == ("孩子可能缺乏学习动力。",)


def test_follow_up_rejects_cross_family_prior_replay() -> None:
    concern = _turn("CONCERN", "input:concern", "孩子写作业前总是很难开始。")
    follow_up = _turn("FOLLOW_UP", "input:follow-up", "有时可以开始。")
    scope = RunScope("tenant:1", "family:1", ("guardian:1", "child:1"))
    other_scope = RunScope("tenant:1", "family:2", ("guardian:2", "child:2"))
    replay = InMemoryExperienceRunLedger().create_draft(
        scope=scope,
        run_id="run:initial",
        request_ref="request:initial",
        draft_payload=_prior_draft(),
        idempotency_key="create:initial",
    )

    try:
        _preparer().prepare_follow_up_from_replay(
            scope=other_scope,
            prior_replay=replay,
            run_id="run:follow-up",
            data_class="SYNTHETIC",
            context_snapshot_ref="context:follow-up",
            conversation_turns=(concern, follow_up),
            knowledge_scope="family_growth",
        )
    except ValueError as exc:
        assert "scope mismatch" in str(exc)
    else:
        raise AssertionError("cross-family prior replay must fail closed")


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
