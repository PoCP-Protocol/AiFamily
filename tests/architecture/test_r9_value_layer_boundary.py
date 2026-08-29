"""R9 —— 打分红线的**类名维度**，闭合一个实测出来的判据漏洞。

## 这个洞是什么

`tests/architecture/test_compliance_constraints.py::test_no_scoring_or_ranking_fields_anywhere`
是真 AST 检查，不是摆设。但它的判据（同文件 L140-146）是**字段名同时命中主体词与打分词**：

    has_subject = any(token in lowered for token in SUBJECT_TOKENS)   # family/child/parent/...
    scoring_hit = next((t for t in SCORING_TOKENS if t in lowered), None)
    if has_subject and scoring_hit: violation

于是（实测，2026-08-29）：

* `family_value_score`   → 被拒收              ✔
* `emotional_value_score` → **完全通过**（字段名里没有主体词） ✘
* `class FamilyValueScore` 的字段是 `emotional` / `action` / `growth` / `economic`
  → **整个模型一条都不会被咬** ✘

判据是**字段名形状**，不是语义上下文。主体是由**类**承载的，而原判据从不看类名。

这与 ADR-0014 §Context 记录的另一处同类失效是同一种病：那里
`assessment.decide()` 靠一个叫 `actor_id` 的 `str` 参数骗过了"人类 actor 形状参数"启发式。
**两处都是"判据看名字，不看类型/上下文"。**

## 为什么现在补

ADR-0015 采纳 Family Growth Intelligence OS 时，四层价值
（Emotional → Action → Growth → Economic）要进领域模型。
按最自然的方式建模就会写出 `class FamilyValueScore` 或 `emotional_value_score`
—— **恰好从上面这个洞里走过去**，测试全绿，然后成为既成事实。
而 R9 原文是「AiFamily **不计算、不存储、不暴露**家庭总分与家庭排行」，
其 FELS 继承语义把 `legacy_profile.family_score` 判为 **RETIRE / 永不入 Family**。

ADR-0015 §1(a) 的裁决是：**任何挂在家庭/个人主体上的对象，不得含任何评分、等级、
百分位、排名、进度百分比字段，无论字段名是否包含主体词。**
本文件是该裁决的执行者；§5.1 要求它与 `Value Architecture` 同批落地。

**注意**：本文件**不重复**既有的字段名维度检查（那属 `test_compliance_constraints.py`，
是 R10「各一份」纪律的适用对象——同一判据不该有两个实现）。
本文件只加原判据结构上看不到的两条：类名自身，与类名 × 字段名的组合。
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_DIR = "backend"

# 与 test_compliance_constraints.py 保持同一词表。有意重复常量而非 import：
# 那个文件正被并发会话修改，跨文件 import 会让两个测试的失败原因纠缠在一起。
# 词表漂移的风险由 test_scoring_token_vocabularies_stay_aligned 兜住（见文末）。
SUBJECT_TOKENS: frozenset[str] = frozenset(
    {"family", "child", "parent", "guardian", "student", "member"}
)

SCORING_TOKENS: frozenset[str] = frozenset(
    {"score", "rank", "ranking", "grade", "percentile", "leaderboard", "progress_pct"}
)

# 每条豁免必须写明理由 —— 无理由的豁免是红线腐蚀的方式（沿用
# test_compliance_constraints.py 的 FIELD_TOKEN_EXEMPTIONS 手法与措辞纪律）。
FIELD_EXEMPTIONS: dict[str, str] = {
    "membership_upgraded_at": "'upgrade' 的子串，不是学业等级",
    "membership_downgraded_at": "'downgrade' 的子串，不是学业等级",
}

CLASS_EXEMPTIONS: dict[str, str] = {}
"""类名豁免。**当前为空，且应当保持为空。**

一个类名同时含主体词与打分词，几乎不可能有正当用途 —— 它字面上就是
"给家庭/孩子打分的东西"。若将来要往这里加一行，请先确认它不是在为 R9 开口子；
按宪章第 3 节，削弱 R9 需要走修宪程序，而不是往豁免表里加一行。
"""


def _iter_backend_models(repo_root: Path):
    """Yield (rel_path, ClassDef) for non-test Python files under backend/."""
    backend = repo_root / BACKEND_DIR
    if not backend.exists():  # pragma: no cover
        return
    for path in sorted(backend.rglob("*.py")):
        parts = path.parts
        if "__pycache__" in parts or "tests" in parts:
            # 测试夹具里出现 status="APPROVED" 这类字面量是正常的；
            # 本检查只关心生产模型的字段形状。
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - another test's problem
            continue
        rel = path.relative_to(repo_root).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                yield rel, node


def _annotated_fields(class_node: ast.ClassDef) -> list[tuple[str, int]]:
    return [
        (stmt.target.id, stmt.lineno)
        for stmt in class_node.body
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
    ]


def _hit(text: str, tokens: frozenset[str]) -> str | None:
    lowered = text.lower()
    return next((t for t in sorted(tokens) if t in lowered), None)


def test_no_class_names_a_subject_score(repo_root: Path) -> None:
    """ADR-0015 §1(a) —— 类名不得同时表达"主体"与"打分"。

    这条捕获 `class FamilyValueScore` 这一形态：它的字段可以叫 `emotional` /
    `action` / `growth`，一个打分词都不含，因此字段名维度的检查永远不会响。
    主体是由类承载的，所以判据必须看类名。
    """
    violations: list[str] = []
    for rel, node in _iter_backend_models(repo_root):
        if node.name in CLASS_EXEMPTIONS:
            continue
        subject = _hit(node.name, SUBJECT_TOKENS)
        scoring = _hit(node.name, SCORING_TOKENS)
        if subject and scoring:
            violations.append(
                f"{rel}:{node.lineno} class {node.name!r} names a subject "
                f"({subject!r}) and a scoring concept ({scoring!r})"
            )

    assert not violations, (
        "R9 violation —— 类名本身就是「给家庭/个人打分的东西」。\n  "
        + "\n  ".join(violations)
        + "\n\nR9: AiFamily 不计算、不存储、不暴露家庭总分与家庭排行。"
        "\n四层价值在家庭侧只能表达为方向与状态转移（Emotional: from→to、"
        "Action: next_action_ref、Growth: changed_dimension_ref），"
        "唯有 Economic 可量化且量化对象是时间/金钱/试错次数而非家庭 —— ADR-0015 §1(a)(b)。"
        "\n群体级度量（Family Value Realization）属 Product Intelligence 侧，"
        "永不写回家庭对象 —— ADR-0015 §1(c)。"
    )


def test_no_scoring_fields_on_subject_shaped_models(repo_root: Path) -> None:
    """ADR-0015 §1(a) —— 主体形状的类，其任何字段不得命中打分词。

    这条捕获 `class FamilyProfile` 里一个叫 `emotional_value_score` 的字段：
    字段名有打分词但没有主体词，所以字段名维度的检查不响；主体信息在类名里。
    """
    violations: list[str] = []
    for rel, node in _iter_backend_models(repo_root):
        subject = _hit(node.name, SUBJECT_TOKENS)
        if not subject:
            continue
        for field_name, lineno in _annotated_fields(node):
            if field_name in FIELD_EXEMPTIONS:
                continue
            scoring = _hit(field_name, SCORING_TOKENS)
            if scoring:
                violations.append(
                    f"{rel}:{lineno} {node.name}.{field_name} scores a subject-shaped "
                    f"model (class matched {subject!r}, field matched {scoring!r})"
                )

    assert not violations, (
        "R9 violation —— 主体形状的模型带了打分字段。\n  "
        + "\n  ".join(violations)
        + "\n\n若该字段确实无害，把它加入 FIELD_EXEMPTIONS **并写明理由**；"
        "无理由的豁免是红线腐蚀的方式。"
    )


def test_scoring_token_vocabularies_stay_aligned(repo_root: Path) -> None:
    """本文件的词表必须与 `test_compliance_constraints.py` 的保持一致。

    两份词表是有意重复的常量（见文件顶部说明：跨文件 import 会让两个测试的失败原因
    纠缠在一起，而那个文件正被并发会话修改）。但"有意重复"必须配一个防漂移检查，
    否则就是 R14 伤疤的形状 —— 源仓库 `FPAI_PROVIDER_REGISTRY.yaml` 声明 3 个 provider
    而生成的快照只有 2 个，正是两份该同步的东西悄悄分叉。

    本检查读取那个文件的 AST 取其词表字面量，任一方新增 token 而另一方未跟上即失败。
    """
    target = repo_root / "tests" / "architecture" / "test_compliance_constraints.py"
    if not target.exists():  # pragma: no cover
        return

    tree = ast.parse(target.read_text(encoding="utf-8"))
    found: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        name = node.target.id
        if name not in {"SUBJECT_TOKENS", "SCORING_TOKENS"} or node.value is None:
            continue
        literals = {
            elt.value
            for elt in ast.walk(node.value)
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
        }
        found[name] = literals

    assert found.get("SUBJECT_TOKENS") == set(SUBJECT_TOKENS), (
        "SUBJECT_TOKENS drifted between test_compliance_constraints.py and this file: "
        f"{found.get('SUBJECT_TOKENS')} != {set(SUBJECT_TOKENS)}. "
        "Update both, or the class-name dimension will stop covering a subject the "
        "field-name dimension still covers (or vice versa)."
    )
    assert found.get("SCORING_TOKENS") == set(SCORING_TOKENS), (
        "SCORING_TOKENS drifted between test_compliance_constraints.py and this file: "
        f"{found.get('SCORING_TOKENS')} != {set(SCORING_TOKENS)}."
    )
