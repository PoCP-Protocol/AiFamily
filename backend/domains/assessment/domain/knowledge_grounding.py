"""构建时固化的知识库 grounding —— 只读,运行时零依赖知识库源。

`CONSTRUCT_KNOWLEDGE_MAP` 是唯一的人工维护映射:construct_ref(须与
Assessment AI 解读适配器实际使用的 construct 白名单一致——本仓库该适配器
处于 BLOCKED 状态,见 governance/MIGRATION_MANIFEST.yaml
assessment_ai_interpretation_adapter 条目,故此刻本映射暂无消费方)
→ 知识库卡片 id 列表。空列表是诚实状态(如 SCHOOL_FAMILY_COLLABORATION 目前
无对应知识卡),不是缺失,不得为了"看起来都有依据"而硬凑映射。

`assessment_construct_grounding.json` 是从 family-ai 仓库的
`20_知识_knowledge/byresearch/export_by_id.py` 构建时生成并原样迁入的**静态
快照**——生成该 JSON 的知识库源(43 张理论/构念/方法卡 + byresearch 治理工具)
本身尚未迁入 AiFamily(见 governance/MIGRATION_MANIFEST.yaml，未登记，需要
独立的 disposition 决策)。本模块运行时只 `json.load` 这个文件,不 import
knowledge 库的任何代码,不跨目录读取——这个解耦设计使得知识库源暂缺不影响
本模块本身可运行,但意味着**当前无法在本仓库内重新生成这个 JSON**，只能
在知识库源迁入后于原仓库重新生成再复制过来。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

CONSTRUCT_KNOWLEDGE_MAP: dict[str, list[str]] = {
    # 情绪教练(核心) + 自我分化(解释"为什么家长学了话术还是会被冲突带情绪") + 对应方法卡。
    "PARENT_CHILD_COMMUNICATION": [
        "TH-001",
        "CN-001",
        "CN-002",
        "MD-001",
        "TH-005",
        "CN-006",
        "MD-005",
    ],
    # 成长型思维/努力归因(核心) + 家长自身教养效能感(家长支持作业时的信心也是变量)
    # + SDT胜任感/自主性。
    "HOMEWORK_PROCESS": [
        "TH-006",
        "CN-007",
        "MD-006",
        "TH-004",
        "CN-005",
        "MD-004",
        "TH-007",
        "CN-008",
    ],
    # 2026-08-29 填补:此前一直留空(知识库无对应卡片),现有TH-010家长媒体调节理论
    # (Nathanson 1999 + Fam et al. 2023 meta分析)。
    "DEVICE_USE_CONTEXT": ["TH-010", "CN-011", "MD-010"],
    # 2026-08-29 Batch 1 admission(governance/CONSTRUCT_ADMISSION_REGISTRY.yaml)新增三条。
    # EMOTION_REGULATION_SUPPORT直接对应TH-001情绪教练(Gottman)。
    "EMOTION_REGULATION_SUPPORT": ["TH-001", "CN-001", "CN-002", "MD-001"],
    # PARENT_CAPACITY对应TH-004家长教养自我效能感 + TH-005自我分化(两条独立理论支撑)。
    "PARENT_CAPACITY": ["TH-004", "CN-005", "MD-004", "TH-005", "CN-006"],
    # SCHOOL_FAMILY_COLLABORATION知识库无对应理论卡(本质是客观协调事实非心理推断),
    # 如实留空,不臆造。
    "SCHOOL_FAMILY_COLLABORATION": [],
    # 2026-08-29 Batch 2 admission。以下两条knowledge_backing在审核记录里标注为weak——
    # 是概念上相邻/部分相关，不是直接对应，映射本身也如实反映这一点(卡片数少)。
    # LEARNING_STRATEGY_METACOGNITION(孩子认知层:计划/复盘/纠错)与TH-006成长型思维/
    # 努力归因部分相关。
    "LEARNING_STRATEGY_METACOGNITION": ["TH-006", "CN-007"],
    # SELF_REGULATION_SUPPORT(家庭对日常任务的支持行为)与TH-007自我决定理论的
    # 胜任感/自主性支持逻辑相邻(家庭提供恰当支持而非包办或放任)。
    "SELF_REGULATION_SUPPORT": ["TH-007", "CN-008"],
}

# The assessment tool speaks in family-facing dimensions while the compiled
# knowledge snapshot speaks in admitted construct refs. Keeping this mapping
# here makes the seam explicit and testable; the result projection never asks
# the mobile client to infer a theory from a focus label.
FOCUS_TO_CONSTRUCT: dict[str, str] = {
    "LEARNING_HABITS": "HOMEWORK_PROCESS",
    "EMOTION_REGULATION": "EMOTION_REGULATION_SUPPORT",
    "PARENT_CHILD_COMMUNICATION": "PARENT_CHILD_COMMUNICATION",
    "DEVICE_USE_CONTEXT": "DEVICE_USE_CONTEXT",
    "SELF_REGULATION": "SELF_REGULATION_SUPPORT",
}

_GROUNDING_FILE = Path(__file__).with_name("assessment_construct_grounding.json")


@lru_cache(maxsize=1)
def _load_grounding_data() -> dict:
    """找不到/解析失败 → 空 dict(FAIL SAFE:宁可无 grounding,不可编造)。"""
    try:
        return json.loads(_GROUNDING_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def grounding_prompt_block(construct_refs: set[str]) -> str:
    """给一组合法 construct_ref,拼出可直接插入 system prompt 的"已验证理论依据"文本块。

    没有任何匹配内容时返回空字符串(调用方据此决定是否插入该区块),
    不返回"暂无相关理论"这类看起来像内容但没信息量的占位句。
    """
    data = _load_grounding_data()
    lines: list[str] = []
    for ref in sorted(construct_refs):
        cards = data.get(ref) or {}
        if not cards:
            continue
        lines.append(f"[{ref}]")
        for card_id, node in cards.items():
            claim = node.get("core_claim") or node.get("summary") or ""
            if not claim:
                continue
            lines.append(f"  - {card_id} ({node.get('evidence_grade', 'E0')}): {claim}")
    return "\n".join(lines)


def grounded_card_ids(construct_ref: str) -> list[str]:
    """给一个 construct_ref,返回它在 assessment_construct_grounding.json 里
    实际有内容的卡片 id 列表 —— 供输出层校验 `grounding_source` 字段引用的 id
    确实来自这条映射,而不是模型自己编的 id。
    """
    data = _load_grounding_data()
    return list((data.get(construct_ref) or {}).keys())


def family_facing_grounding(focus_ref: str) -> dict:
    """Return a bounded knowledge reference for the family result projection.

    The compiled JSON is a reviewed snapshot, not a live retrieval service.
    This function therefore returns only stable card metadata that a parent
    can understand: the construct seam, card references, evidence grade, a
    concise claim, and the mechanism/boundary. Missing or malformed data is an
    honest unavailable state; it never creates a made-up citation.
    """
    construct_ref = FOCUS_TO_CONSTRUCT.get(focus_ref)
    if construct_ref is None:
        return {
            "status": "UNAVAILABLE",
            "construct_ref": None,
            "card_refs": [],
            "evidence_grade": None,
            "core_claim": None,
            "mechanism": None,
            "boundary": "KNOWLEDGE_REFERENCE_NOT_FAMILY_FACT",
        }

    data = _load_grounding_data()
    cards = data.get(construct_ref) or {}
    valid_cards = [
        (card_ref, card)
        for card_ref in CONSTRUCT_KNOWLEDGE_MAP.get(construct_ref, [])
        if isinstance((card := cards.get(card_ref)), dict)
        and (card.get("core_claim") or card.get("summary"))
    ]
    if not valid_cards:
        return {
            "status": "UNAVAILABLE",
            "construct_ref": construct_ref,
            "card_refs": [],
            "evidence_grade": None,
            "core_claim": None,
            "mechanism": None,
            "boundary": "KNOWLEDGE_REFERENCE_NOT_FAMILY_FACT",
        }

    primary_ref, primary = valid_cards[0]
    return {
        "status": "GROUNDED",
        "construct_ref": construct_ref,
        "card_refs": [card_ref for card_ref, _ in valid_cards],
        "primary_card_ref": primary_ref,
        "title": primary.get("title"),
        "evidence_grade": primary.get("evidence_grade", "E0"),
        "core_claim": primary.get("core_claim") or primary.get("summary"),
        "mechanism": primary.get("mechanism"),
        "boundary": primary.get(
            "boundary", "KNOWLEDGE_REFERENCE_NOT_FAMILY_FACT"
        ),
    }
