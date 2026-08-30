---
id: EXPERIENCE-WEB-STUDIO-001
title: Web Experience Studio 体验工作台契约 V1
type: specification
status: draft
version: 0.1
owner: project-manager
created: 2026-08-30
updated: 2026-08-30
canonical: false
supersedes: null
superseded_by: null
---

# Web Experience Studio 体验工作台契约 V1

> 本文件冻结 Web-only 体验工作台的边界、状态和可注入接口，不代表 Web 前端已经存在或可用。
> 当前仓库没有 `frontend/web`；`frontend/mobile` 是 Expo/React Native 移动端工程，虽然配置了
> Expo Web 输出，也不能作为 Web 产品实现的替代物。本契约不允许修改移动端来绕过该缺口。

## 1. 目标与本 Sprint 的最小纵向切片

Experience Studio 是家长在 Web 上提交一次家庭表达并查看 AI 理解草案的工作台。首个切片只
支持“文本 + 图片引用 → Model Gateway → DRAFT 体验结果 → 人工确认入口”，不包含真实供应商、
领域事实写入、订单、成长评分或家庭排名。

```text
输入区（文本、图片引用、用途、语言、同意状态）
  → 可注入 ExperienceApiClient
  → Web API / Model Gateway（唯一模型边界）
  → DRAFT 结果卡（输出、provenance、限制、状态）
  → 家庭确认 / 改写 / 拒绝 / 请求人工
```

成功路径与拒绝路径必须同等可演示：

| 路径 | UI 结果 | 允许的副作用 |
|---|---|---|
| 成功 | 显示 `DRAFT`、模型尝试引用、证据/限制和“等待确认” | 只记录体验信号或反馈 |
| 缺少同意 | 显示可理解的拒绝原因和重新授权入口 | 不调用模型、不保留媒体 |
| 未准入供应商 | 显示暂不可用/转人工 | 不伪装为 AI 成功 |
| 超时或网络错误 | 显示重试、稍后回来、请求人工 | 幂等重试，不重复生成记录 |
| 用户拒绝/改写 | 保留用户选择为反馈信号 | 不把草案升级为事实 |

## 2. 页面边界（Web-only）

页面由四个可独立测试的区域组成，命名不绑定 React、Vue 或其他框架：

1. **ExpressionInput**：文本输入、图片引用添加/移除、用途和 locale 展示；提交前阻断空输入、
   非法媒体引用、缺少 consent 或跨 scope 引用。
2. **RunStatus**：`idle`、`validating`、`running`、`partial`、`success`、`refused`、`timeout`、
   `retrying`、`human_review`、`deleted` 十种状态；状态文案不能把 DRAFT 写成事实。
3. **DraftResult**：展示结构化输出、`provenance_ref`、`model_attempt_ref`、`context_snapshot_ref`、
   限制/置信信息和“需要人工确认”标记；原始儿童媒体只显示受保护的引用，不显示供应商对象。
4. **DecisionActions**：确认草案、改写、拒绝、请求人工、重新生成；这些动作调用明确的 client
   方法，不能通过组件内部直接写 Family/Journey/Service/Commerce。

组件应是纯视图 + 状态转换，不在组件中读取供应商密钥、不导入 Model Gateway、不拼接供应商
   请求。真实路由接入前使用同一接口的 sandbox/fake client，禁止挂载“合成数据生产路由”。

## 3. API client seam（框架无关）

Web 工程建立后，需提供以下可注入接口；命名可适配所选框架，但字段语义必须保持不变：

```text
ExperienceApiClient
  createDraft(input: CreateDraftInput, idempotencyKey: string)
    -> Promise<ExperienceDraft | ExperienceError>
  decide(input: DraftDecisionInput, idempotencyKey: string)
    -> Promise<DecisionReceipt | ExperienceError>
  submitFeedback(input: FeedbackInput, idempotencyKey: string)
    -> Promise<FeedbackReceipt | ExperienceError>
  requestHuman(input: HumanReviewInput, idempotencyKey: string)
    -> Promise<HumanReviewReceipt | ExperienceError>
  deleteRun(runId: string, idempotencyKey: string)
    -> Promise<DeletionReceipt | ExperienceError>
```

`CreateDraftInput` 最小字段：`run_id`、`use_case`、`prompt_version`、`schema_version`、
`data_class`、`context_snapshot_ref`、`payload`、`input_refs`、`media_inputs`、`scope`。
图片必须携带 `media_type=IMAGE`、`uri`、`mime_type` 和 `sha256`；前端只提交引用和元数据，
不把供应商格式泄漏到业务组件。

`ExperienceDraft` 最小字段：`run_id`、`status=DRAFT`、`output`、`provenance`、
`requires_human_confirmation=true`、`media_inputs`、`correlation_id`。`provenance` 至少包括
`model_attempt_ref`、`context_snapshot_ref`、`prompt_version`、`schema_version`、`captured_at`。

## 4. 与后端契约的映射

| Web 概念 | 后端唯一来源 | 约束 |
|---|---|---|
| 生成草案 | `MultimodalExperienceCommand` / `MultimodalExperienceService` | 必须经 `backend/intelligence/model_gateway` |
| 媒体输入 | `MediaInput` | 当前图片可进入 OpenAI-compatible adapter；音频/视频未准入时必须拒绝 |
| 草案状态 | `ModelDraft` | `may_mutate_business_state=false`，不能自动成为 Fact |
| 体验事件/推荐/反馈 | `ExperienceEvent` / `RecommendationDecision` / `FeedbackSignal` | 通过 Experience Gateway 幂等追加 |
| 人工确认 | Human Gate / Named Action | Web 只发起请求，不自行批准领域事实 |
| 删除 | `deletion_ref` 及其派生证明 | 删除后页面进入 `deleted`，不可从缓存恢复媒体 |

## 5. Sandbox fixture seam

fixture 只能作为 client 的测试替身，必须明确标注 `SYNTHETIC_TEST`，并与生产路由物理隔离。
至少覆盖：

- `successDraft`：返回合法 DRAFT、完整 provenance 和图片引用；
- `consentRefused`：返回稳定错误码 `CONSENT_REQUIRED`；
- `providerNotAdmitted`：返回 `PROVIDER_NOT_ADMITTED`；
- `timeoutThenRetry`：首次超时，使用同一幂等键重试得到同一结果；
- `humanReview`：请求人工后进入 `human_review`，不得自动批准；
- `deleted`：删除成功后，所有结果读取返回 `MEDIA_DELETED`。

fixture 不得硬编码“AI 文案”来冒充模型能力；它只用于状态机、错误语义、权限、同意、幂等和
可访问性测试。真实模型效果必须由 Model Gateway sandbox 评测提供。

## 6. Web 验收与 Definition of Done

Web 工程落地后，首个 Sprint 必须同时满足：

1. 页面在桌面 Web 浏览器可打开，且不依赖 `frontend/mobile` 的路由、主题或组件；
2. 文本 + 图片引用成功生成一次 DRAFT，并展示 provenance、限制和人工确认状态；
3. 缺 consent、跨 scope、未准入供应商、超时、重试、拒绝、请求人工和删除均有可见状态；
4. 相同 idempotency key 不产生重复运行/反馈；
5. 前端单元/组件测试使用可注入 fake client，不调用外部网络；
6. 浏览器级测试只验证 Web UI 与 client seam，不把 fixture 结果宣称为模型质量；
7. 无任何移动端文件改动，无任何供应商 SDK 或密钥进入前端构建产物；
8. 通过后端对应的 `tests/intelligence/experience` 与 `tests/intelligence/model_gateway` 套件。

## 7. 当前阻塞与下一步

当前唯一阻塞是缺少独立 Web 工程及其技术基线（构建工具、路由、测试运行器、设计系统和部署
入口）。在 PM 选定并登记 Web 技术栈前，不应创建 `frontend/web` 的临时框架或复制移动端。

下一步由 Web Agent 在一个独立变更中完成：

1. 选定并登记 Web 技术基线（另行 ADR，不能在组件 PR 中隐式决定）；
2. 按本契约实现 `ExperienceApiClient` 类型、fake client 和状态机；
3. 实现 ExpressionInput → RunStatus → DraftResult → DecisionActions 的最小纵向切片；
4. 补齐组件、client seam、拒绝/重试/删除和浏览器可访问性测试；
5. 与后端 `MultimodalExperienceService` 及 Experience Gateway 做 sandbox 集成验收。
