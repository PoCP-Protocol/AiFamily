---
id: ADR-0028
title: Freeze the experience loop contracts before vertical implementation
status: PROPOSED
date: 2026-08-30
owners: [chief-architect, ai-runtime]
---

# ADR-0028：先冻结体验闭环契约，再接入业务纵向切片

## Context

Family 的核心蓝图要求“先情绪价值、再成长价值、最后经济价值”，并以教育入口进入
N0-N8 家庭需求闭环。类抖音的内容发现、游戏化的小行动、海底捞式补救和贝壳式 FGCN
协作如果没有统一事件、推荐解释和反馈边界，容易出现跨租户推荐、把跳过误当失败、或
让 AI 直接写成长/订单事实的问题。

## Decision

在 Sprint 0 先冻结三个只读/追加式契约：

1. `ExperienceEvent`：记录入口、展示、选择、行动和服务意向等交互事实，并绑定 N0-N8
   节点；禁止家庭分数、排名和权威事实字段。
2. `RecommendationDecision`：记录候选集、策略版本、选中项、拒绝原因和可解释溯源；
   只能输出 `PROPOSED` 等建议状态，不能直接创建 Growth/Journey/Service/Commerce 事实。
3. `FeedbackSignal`：记录完成、改写、跳过、暂停、投诉、降低频率、清空推荐和请求人工；
   投诉/人工请求必须进入人工队列，不能自动关闭。

三个契约共享必填 scope：`global_id`、`tenant_id`、`region_id`、`family_id`、
`subject_ids`、`purpose`、`consent_version`、`data_class`、四类 locale、`provenance`、
`deletion_ref`、`correlation_id` 和 `causation_id`。幂等键按租户隔离；任何跨租户、跨家庭、
跨主体或用途不一致的 join 必须拒绝。未成年数据不得用于自动 `marketing`/`upsell`/`sales`。

体验支持 `text`、`voice`、`image`、`audio`、`video`、`interactive_card` 六种 modality，
并用 `input`、`output`、`transcription`、`ocr`、`playback` 标注边界操作。媒体引用和转写/OCR
派生物各自携带 provenance/deletion_ref；缺同意、过期播放或跨租户/家庭/主体挂载均 fail-closed。

上下文记忆另有 `MemoryRef`：`child`、`guardian`、`family_relationship` 三种
`memory_scope`，以及 M0（单轮）至 M3（经复核长期）的四级保留范围。每条记忆必须有
显式用途、同意、过期时间、provenance 和 deletion cascade；读取越权、用途不匹配、过期
或未成年人商业用途均拒绝。

法咪莉校长的 `experience_curator` 仅作为 PLANNED profile 进入注册表设计，不在本 ADR 中
新增运行时 Agent 或模型供应商接入；实际模型调用仍只能经 `model_gateway`，输出需过安全、
溯源、人工/家庭闸门。

## Consequences

- 前后端可以并行开发 UI-03 → UI-05 → UI-09，而不复制业务事实表。
- 推荐/反馈事件可以进入区域 Cell、评估集和删除索引，且保留解释链。
- 需要由 Lead 后续把契约接入 ExperienceApplication、Principal 路由和 Named Action；
  当前交付只证明契约和拒绝测试通过，不得宣称生产能力。

## Rejected alternatives

- 用停留时长、连续打卡、消费金额合成家庭价值分：违反“家是港湾”和非比较游戏化边界。
- 由 AI 直接确认需求、分派资源、验收质量或开通交易：违反 R8/R9 和领域事实归属。
- 让测试环境删除人工闸门或商业闸门：违反环境功能等价要求。

## Evidence

- `docs/08_experience/EXPERIENCE_CLOSED_LOOP_CONTRACTS_V1.md`
- `backend/intelligence/experience/contracts.py`
- `backend/intelligence/experience/memory_adapter.py`
- `tests/intelligence/experience/test_contracts.py`
- `tests/intelligence/experience/test_memory_adapter.py`
