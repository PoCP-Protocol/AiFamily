from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.experience.family_problem_understanding_contract import (
    FamilyConversationTurn,
    build_family_problem_understanding_request,
)
from backend.intelligence.experience.family_problem_understanding_knowledge import (
    FamilyUnderstandingKnowledgeRetriever,
    lexical_relevance,
)
from backend.intelligence.knowledge.contracts import KnowledgeClaim, KnowledgeSource
from backend.intelligence.knowledge.registry import KnowledgeRegistry
from backend.packages.contracts.evidence import Provenance


def _turn(text: str = "孩子每天从玩耍切换到写作业时很难开始。") -> FamilyConversationTurn:
    return FamilyConversationTurn(
        input_ref="input:concern",
        kind="CONCERN",
        text=text,
        created_at="2026-09-03T10:00:00+08:00",
    )


def _source(source_id: str = "source:reviewed-parenting") -> KnowledgeSource:
    return KnowledgeSource(
        source_id=source_id,
        title="Reviewed parenting evidence",
        license_ref="license:reviewed",
        owner="knowledge-team",
        scope="shared",
        verified=True,
    )


def _claim(
    claim_id: str,
    text: str,
    *,
    status: str = "PUBLISHED",
    purpose: str = "family_problem_understanding",
    scope: str = "family_growth",
    metadata: dict[str, object] | None = None,
    expires_at=None,
) -> KnowledgeClaim:
    return KnowledgeClaim(
        claim_id=claim_id,
        text=text,
        source_id="source:reviewed-parenting",
        provenance=Provenance(level="E6", source_ref="source:reviewed-parenting"),
        scope=scope,
        status=status,
        allowed_purposes=(purpose,),
        expires_at=expires_at,
        metadata=metadata
        or {
            "version": "1.0",
            "chunk_ref": f"chunk:{claim_id}",
            "applicability": "家庭学习任务开始与活动转换",
            "limitations": ("不能仅凭一次表达判断孩子能力",),
            "keywords": ("切换", "写作业", "开始"),
        },
    )


def _registry(*claims: KnowledgeClaim) -> KnowledgeRegistry:
    return KnowledgeRegistry(sources=(_source(),), claims=claims)


def test_retrieves_relevant_published_claim_and_builds_model_ready_excerpt() -> None:
    relevant = _claim(
        "knowledge:task-transition:v1",
        "任务开始困难可能与活动转换、选择感和任务难度有关。",
    )
    unrelated = _claim(
        "knowledge:meal-routine:v1",
        "共同进餐的稳定节奏有助于家庭交流。",
        metadata={
            "version": "1.0",
            "chunk_ref": "chunk:meal-routine",
            "applicability": "家庭共同进餐",
            "limitations": ("不适用于学习任务分析",),
            "keywords": ("进餐", "饮食"),
        },
    )
    selection = FamilyUnderstandingKnowledgeRetriever(
        _registry(relevant, unrelated), minimum_relevance=0.05
    ).retrieve(conversation_turns=(_turn(),), scope="family_growth")

    assert selection.trace.candidate_count == 2
    assert selection.trace.selected_claim_ids == ("knowledge:task-transition:v1",)
    assert selection.trace.rejected_claim_ids == ("knowledge:meal-routine:v1",)
    assert selection.excerpts[0].source_ref == "source:reviewed-parenting"
    assert selection.excerpts[0].limitations == ("不能仅凭一次表达判断孩子能力",)

    request = build_family_problem_understanding_request(
        run_id="run:knowledge-grounded",
        data_class="SYNTHETIC",
        context_snapshot_ref="context:knowledge-grounded",
        conversation_turns=(_turn(),),
        reviewed_knowledge=selection.excerpts,
    )
    assert request.payload["reviewed_knowledge"][0]["knowledge_ref"] == (
        "knowledge:task-transition:v1"
    )


def test_registry_and_retriever_filter_wrong_purpose_scope_expiry_and_review_metadata() -> None:
    expired = _claim(
        "knowledge:expired",
        "写作业任务转换。",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    wrong_purpose = _claim(
        "knowledge:service-only",
        "写作业任务转换。",
        purpose="service_product_design",
    )
    wrong_scope = _claim(
        "knowledge:other-scope",
        "写作业任务转换。",
        scope="other",
    )
    missing_boundaries = _claim(
        "knowledge:no-boundaries",
        "写作业任务转换。",
        metadata={"version": "1.0"},
    )
    selection = FamilyUnderstandingKnowledgeRetriever(
        _registry(expired, wrong_purpose, wrong_scope, missing_boundaries),
        minimum_relevance=0.0,
    ).retrieve(conversation_turns=(_turn(),), scope="family_growth")

    assert selection.excerpts == ()
    assert selection.trace.candidate_count == 1
    assert selection.trace.rejected_claim_ids == ("knowledge:no-boundaries",)


def test_max_excerpts_is_deterministic_and_trace_keeps_rejected_candidates() -> None:
    first = _claim("knowledge:a", "写作业开始与活动切换。")
    second = _claim("knowledge:b", "写作业开始与活动切换。")
    selection = FamilyUnderstandingKnowledgeRetriever(
        _registry(second, first), minimum_relevance=0.0, max_excerpts=1
    ).retrieve(conversation_turns=(_turn(),), scope="family_growth")

    assert selection.trace.selected_claim_ids == ("knowledge:a",)
    assert selection.trace.rejected_claim_ids == ("knowledge:b",)


def test_invalid_injected_relevance_score_fails_closed() -> None:
    retriever = FamilyUnderstandingKnowledgeRetriever(
        _registry(_claim("knowledge:a", "写作业开始与活动切换。")),
        relevance_scorer=lambda _query, _claim: 1.2,
    )
    with pytest.raises(ValueError, match="invalid relevance score"):
        retriever.retrieve(conversation_turns=(_turn(),), scope="family_growth")


def test_lexical_relevance_prefers_matching_family_context() -> None:
    matching = _claim("knowledge:matching", "活动切换可能影响写作业开始。")
    unrelated = _claim(
        "knowledge:unrelated",
        "家庭共同进餐节奏。",
        metadata={
            "version": "1.0",
            "chunk_ref": "chunk:unrelated",
            "applicability": "共同进餐",
            "limitations": ("不用于学习问题",),
        },
    )
    assert lexical_relevance(_turn().text, matching) > lexical_relevance(_turn().text, unrelated)
