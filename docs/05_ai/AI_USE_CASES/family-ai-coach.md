---
id: AI-USE-CASE-001
title: Family AI Coach — 苏格拉底式引导对话
type: ai-use-case
status: current
version: 1.0
owner: project-owner
created: 2026-09-03
updated: 2026-09-03
canonical: true
---

# Family AI Coach — 苏格拉底式引导对话

## 做什么

家长针对一个已捕获的 `family_need` 发一条消息，AI Coach 用苏格拉底式提问方式回复：
先反映对家长处境的理解，再提一个具体的、能推进家长自己思考的问题。**不直接给解决方案，
不做诊断，不评判**。回复内容(`reflection`/`guiding_question`)100%由真实大模型生成，
本仓库只写系统提示词、调用代码、JSON schema 结构校验——没有任何 if-elif/关键词匹配/
模板拼接来生成具体文字内容。

代码位置：
- `backend/intelligence/experience/family_ai_coach.py`（通用生成式调用，不依赖任何业务域）
- `backend/domains/family_need/application/ai_coach.py`（family_need 域组装真实上下文）
- `backend/apps/family_api/ai_coach_wiring.py`（provider 注册与环境切换）
- `backend/domains/family_need/api/routes.py` 的 `POST /families/{family_id}/needs/{need_id}/ai-coach/messages`

## allowed_tools

无。这是纯对话能力，不调用任何工具、不查询任何外部系统、不触发任何业务动作。

## context_policy

只读 `family_need` 域的真实数据：当前 need 的 `statement`/`desired_outcome`/
`category`/`emotional_gate`，以及（可选）已存在的 `NeedProfile.intervention_tier`/
`urgency` 和已匹配的 `SolutionDraft.components`。**不编造**任何家庭没有提供的内容——
`build_family_context` 在 need 不存在时抛 `FamilyNeedNotFoundError`，绝不用占位数据顶替。

`data_class` 取自该 need 本身在捕获时记录的分类（`NeedContext.data_class`），而不是
由调用方任意选择——见 `ai_coach.py` 中 family_need `DataClass` 到 Model Gateway
`DataClass` 的显式映射表。

## human_gate

`NONE`。这不是"AI 建议要变成业务状态变更的具体动作"的场景（那类场景走
Human Gate，例如 FGCN 教师分派建议需要家长审批才落地）。AI Coach 的回复本身**就是**
展示给家长看的 Perspective，家长看了以后怎么想、怎么做完全是家长自己的事，回复不产生
任何业务状态变更，因此不需要走 Human Gate 审批流程。

## may_mutate_business_state

`false`。由 `ModelGateway`/`ModelDraft.may_mutate_business_state`（无 setter 的
property，恒为 False）结构性保证，AI Coach 路由本身也不写任何 `family_need` 聚合——
只读 need/profile/draft，不写。

## 治理边界标注

响应体的 `boundary` 字段固定标注 `AI_PERSPECTIVE_NOT_FAMILY_FACT_GUIDANCE_NOT_ANSWER`，
延续本域其它端点（`FAMILY_EXPRESSION_NOT_AI_DIAGNOSIS`/`NEED_PROFILE_NOT_FAMILY_SCORE`等）
已有的 boundary 字段惯例。

## Provider 与 §16 合规状态

- dev/test：`fake-deterministic`（确定性 in-process，不是第三方处理者，第16条不适用）。
- 生产/真实模型验证：`deepseek-coach`（真实 DeepSeek Chat Completions，OpenAI 兼容协议）。
  该 provider **没有**完成《儿童个人信息网络保护规定》第16条要求的安全评估与委托协议，
  `sub_delegates=None`（未确定），因此在 registry 中只被授权 `OPERATIONAL_TEXT` 数据类别、
  仅在 `internal_livecheck` 环境下可调用——`FAMILY_PRIVATE_TEXT`/`MINOR_PERSONAL_DATA`
  对这个 provider 永远被 `admit()` 拒绝，这是设计如此，不是待修的缺口。真实家庭对话数据
  要接入 DeepSeek，前提是法务完成第16条评估并把 `deepseek-coach` 记录更新为
  `sub_delegates=False` + 补齐 `security_assessment_ref`/`processing_agreement_ref`。

## AI_NATIVE_PRINCIPLES 五问自检

| # | 判据 | 自检结论 |
|---|---|---|
| 1 | AI 是否主路径 | 是。关掉 AI，"引导式对话"这个能力直接不存在——没有规则/人工兜底版本，家长收到的就是模型生成的内容。 |
| 2 | 数据结构是否为 AI 理解而设计 | 部分是。复用了 `family_need` 已有的证据/语义结构（statement/desired_outcome/intervention_tier），AI Coach 本身没有新增持久化模型——上下文来自已有的 AI 原生数据结构。 |
| 3 | 是否生成式优先 | 是，且是本用例的核心红线：`guiding_question`/`reflection` 的具体文字内容 100% 由模型生成；本仓库代码只有 prompt + 调用 + schema 校验，没有任何 if-elif/关键词匹配生成文字内容。 |
| 4 | 是否越用越准 | 否，暂不满足。当前没有反馈闭环把家长的后续互动沉淀为下一次回复更准的证据——这是已知差距，留给后续迭代（例如接入 memory_adapter 或 engagement 反馈），本次不虚报为已具备。 |
| 5 | AI 权限边界是否显式建模 | 是。`may_mutate_business_state=false` 结构性保证；`allowed_tools=无`；`human_gate=NONE` 有明确理由（Perspective非Action）；provider 准入受 registry 治理，`deepseek-coach` 的数据类别/环境限制显式声明在代码与本文档中。 |

判据4尚未满足，因此本用例目前属于"核心域 AI 原生能力的第一版"，不是完整版——
后续要做真正的学习闭环才能补齐判据4。

## 验收证据

- 单元/契约测试（FakeProvider）：`tests/domains/family_need/test_ai_coach_route.py` ——
  验证 schema 校验 fail-closed、上下文确实来自真实 need 数据、provenance 完整。
- 真实模型验证（gated）：`tests/intelligence/experience/test_family_ai_coach_real_model.py`
  ——`AI_COACH_MODEL_API_KEY`/`AI_COACH_MODEL_BASE_URL` 未设置时自动 skip；设置后对
  DeepSeek 发起真实调用，断言返回是结构合理的真实疑问句而非固定文案。
