---
id: RESEARCH-MANUS-BOLE-MULTIMODAL-001
title: Manus / Bole.ai 多模态体验对标与 AiFamily 可迁移工程方法
type: research
status: draft
version: 1.0
owner: ai-platform
created: 2026-08-30
updated: 2026-08-30
canonical: false
evidence_class: RESEARCH_ONLY
---

# Manus / Bole.ai 多模态体验对标与 AiFamily 可迁移工程方法

## 0. 结论先行

AiFamily 不复制某一家产品的界面或供应商调用，而是只吸收已经能被证据支持的工程模式：

1. **Manus 可核验的模式**：异步任务、可暂停等待用户确认、结构化输出、文件附件、项目/技能/连接器、Webhook 事件和可恢复的任务生命周期。
2. **Bole.ai 可核验的本地资产**：外部数据先进入 adapter boundary；保留 source lineage；E1 数据只能作为场景、风格和评估候选；Manus 视觉能力迁移框架把输入登记、渲染、OCR、视觉信号、冲突门和审计报告串成证据链。
3. **暂不能核验的内容**：Bole.ai 是否包含 Manus 的具体内部实现、模型、提示词或生产架构。当前没有可公开访问的一手技术资料，因此不能把“Bole.ai 有 Manus 成果”当作事实写入 AiFamily。
4. **AiFamily 当前切片**：Web UI 只做“文本 + 图片 → 结构化体验草稿 → 人工确认/反馈/回放”，全部模型调用经 `backend/intelligence/model_gateway`；音频、视频和短剧只先做契约与异步作业边界，不在本切片伪装成已生产能力。

本文是研究证据与迁移决策，不是当前系统真相；任何能力进入生产前仍需 ADR、注册表、测试和合规 Gate。

## 1. 证据分层

| 层级 | 内容 | 当前处理 |
|---|---|---|
| A：公开一手证据 | Manus 官方产品页与 API 文档 | 可用于抽取公开的接口/生命周期模式，不推断其内部实现 |
| B：本地历史证据 | `family-ai` 中的 Bole adapter、场景库、数据审计、Manus 视觉迁移框架 | 仅作为迁移参考；保留 lineage，不能直接成为 AiFamily 事实 |
| C：用户提供线索 | “之前项目学习 Manus”“Bole.ai 可能有 Manus 成果” | 作为待核验假设，需补原始仓库、授权或一手链接 |
| D：设计假设 | Planner/Runner/Observer、artifact workspace、checkpoint 等 agent 工程模式 | 先做小切片和评估，不能先当作已存在代码 |

## 2. 对标结果

### 2.1 Manus：可直接核验的公开能力

Manus 官方 API 文档明确描述了以下可迁移模式：

| 观察到的能力 | 一手证据 | AiFamily 的迁移解释 |
|---|---|---|
| 异步 task 与状态轮询 | [Task Lifecycle](https://open.manus.ai/docs/v2/task-lifecycle.md) | Experience Run 要有 `QUEUED/RUNNING/WAITING/SUCCEEDED/FAILED/CANCELLED`，不能把长任务伪装成同步 HTTP |
| 等待用户输入或动作确认 | [Task Lifecycle](https://open.manus.ai/docs/v2/task-lifecycle.md) | 高影响动作进入 Human Gate；`WAITING` 是一等状态，恢复必须带 event id 和确认输入 |
| JSON Schema 结构化输出 | [Structured Output](https://open.manus.ai/docs/v2/structured-output.md) | Model Gateway 强制 `output_schema`，模型输出只能成为 `DRAFT`，不能直写领域事实 |
| 文件先上传再以 file id 引用 | [file.upload](https://open.manus.ai/docs/v2/file.upload.md) | Web 上传只登记受控 media/artifact ref；原始 bytes 不进入 attempt ledger；衍生 OCR/转录要有独立 provenance |
| Webhook 推送任务事件 | [Webhooks Overview](https://open.manus.ai/docs/v2/webhooks-overview.md) | 体验运行采用事件驱动通知，同时保留轮询兜底；事件必须幂等和可重放 |
| Projects、Skills、Connectors、Agents | [Manus API docs index](https://open.manus.ai/docs/llms.txt) | AiFamily 将 Skill/Tool/Agent 做成注册表和权限边界，不让自由文本决定可用工具 |
| Web 应用与多种生成工具 | [Manus Web App](https://manus.im) | 只借鉴“对话式生成 + 可交付 artifact”的产品形态；不复制平台 UI，也不把网页生成能力误认为家庭教育能力 |

上述是接口层可观察事实，不等于 Manus 的私有内部实现。尤其 Planner、浏览器操作、反思循环等，只能作为工程假设，须通过我们自己的实现和评估证明。

### 2.2 Bole.ai：本地可核验的迁移资产

本地历史仓库中已经存在 Bole 相关的 adapter 和审计材料，说明可迁移的重点不是“把数据搬过来”，而是“把边界和数据处理方法搬过来”：

| 本地证据 | 可迁移做法 | AiFamily 约束 |
|---|---|---|
| `integrations/sources/bole-ai/adapter.ts` | Raw DTO → Canonical candidate；保留 `source_lineage` | 不直接写 Ontology、Family 或成长事实 |
| `BOLE_DISTILLATION_DATA_PORT_AUDIT` | 外部数据只进入 integration source area；业务表空数据也如实记录 | 外部数据必须经过授权、脱敏、验证和人工批准 |
| `BOLE_DERIVED_SCENARIO_BANK` | 痛点是场景分类，不是儿童/家庭标签；风格样本不是真理 | E1 只能做 scenario/style/eval 候选，不能作为效果证明 |
| `FAMILY_MANUS_VISUAL_CAPABILITY_TRANSFER_FRAMEWORK` | 输入登记 → PPT/图片渲染 → OCR/视觉信号 → crosswalk → 冲突/Human Gate → 审计报告 | 不从局部序号推断全局 UI，不把视觉识别写成家庭事实 |
| `apps/mobile/lib/_core/manus-runtime.ts` | iframe 与宿主间使用显式消息协议，初始化和安全区域事件可观测 | AiFamily 目标已收敛为 Web UI；只借鉴协议和可观测性，不迁入 Mobile 业务代码 |

历史仓库中没有找到能证明“Bole.ai 内部实现源自 Manus”的公开技术文档。需要项目负责人提供原始仓库、导出包、授权证明或一手链接后，才能新增更高证据等级。

### 2.3 其他平台：只比较能力类别，不先做未经核验的品牌结论

当前阶段先用能力矩阵而不是品牌排名：

| 能力类别 | AiFamily 是否需要 | 首个切片的取舍 |
|---|---|---|
| 多模态输入（文本/图片） | 是 | 先经 Model Gateway 做结构化草稿 |
| 音频/视频理解与生成 | 是 | 先定义 `MediaInput`、Artifact、异步 Job、权利和质量契约；供应商审批后再启用 |
| 长任务与断点恢复 | 是 | 先实现内部 Run 状态机、attempt ledger、replay；不依赖某一家平台的黑盒状态 |
| 工具/技能编排 | 是 | Skill/Tool Registry + allow-list；家庭数据场景默认无外部 effect |
| 浏览器/电脑操作 | 以后可能需要 | 仅在明确业务价值、权限和人审边界后立项；不是首个家庭体验切片 |
| Artifact 工作区 | 是 | 统一媒体引用、版本、权利、来源和删除级联 |
| 评估和反馈学习 | 是 | 先做离线 golden set、人工评分和反馈事件；禁止把点击率当作教育效果 |

## 3. AiFamily 迁移后的目标链路

```text
Web Experience Studio
  → Experience Run Command
  → Context Snapshot + Media Registry
  → Model Gateway（唯一供应商边界）
  → Schema Validation + AiProvenance
  → ModelDraft（DRAFT only）
  → RecommendationDecision（PROPOSED）
  → Human Review / Feedback / Replay
  → Evaluation Projection → IPD/PDM/PLM 版本决策
```

### 3.1 运行边界

- `backend/intelligence/experience` 只编排体验契约、运行状态、媒体引用、反馈和回放，不导入领域仓储。
- `backend/intelligence/model_gateway` 负责 provider admission、凭据、超时、attempt、schema validation 和 provenance。
- Provider registry 没有合规批准时，调用必须 fail closed；候选供应商声明不等于可调用供应商。
- AI 输出只能是 `ModelDraft` / `RecommendationDecision(PROPOSED)`；转成家庭计划、服务推荐或其他事实必须经过领域 Named Action、授权、Human Gate、审计和 Outbox。
- 音频和视频不能因为契约枚举存在就声称“已支持”；必须同时具备供应商能力、数据处理协议、删除承诺、质量评估和回滚方案。

### 3.2 首个 Web 纵向切片

**输入**：家长在 Web Experience Studio 输入一段家庭场景文字，并上传一张图片。

**处理**：生成 `StructuredRequest`，携带 `MediaInput(IMAGE)`、`context_snapshot_ref`、`data_class`、`output_schema`，经 Model Gateway 调用已批准的多模态 provider；开发/测试使用 FakeProvider，不把合成数据挂到生产路由。

**输出**：一个包含 `situation_summary`、`observable_signals`、`candidate_next_steps`、`risk_flags`、`needs_human_gate` 的 `ModelDraft`，初始状态固定为 `DRAFT`；随后由体验层发布 `RecommendationDecision(PROPOSED)`，等待家长反馈。

**回放**：保存 request id、attempt id、media hash、schema/prompt 版本、模型 provenance 和反馈事件；回放不重新发送家庭原始媒体，只能使用受控引用且先过权限和删除策略。

## 4. 敏捷交付切片（Web-only）

| 切片 | 时间盒 | 可交付物 | 验收标准 |
|---|---:|---|---|
| S0 合同与证据 | 2 天 | MediaInput、Experience Run 状态、Artifact/Deletion/Provenance 关系、对标证据登记 | 架构测试通过；无未登记 provider；Bole 数据仍隔离 |
| S1 文本+图片草稿 | 4 天 | Web Studio 最小页面、Model Gateway image input、结构化草稿、FakeProvider 测试 | 正常、超时、无 provider、非法 JSON、跨 scope、无 consent 均有可重复结果 |
| S2 体验闭环 | 4 天 | PROPOSED recommendation、接受/拒绝/暂停/请求人工、时间线和反馈 | 幂等；反馈不能跨 tenant/family/subject；AI 不写事实 |
| S3 Durable Run | 4 天 | `QUEUED/RUNNING/WAITING/SUCCEEDED/FAILED/CANCELLED`、checkpoint、事件通知和 replay | 进程重启后状态可恢复；重复 webhook 不重复副作用；WAITING 必须显式恢复 |
| S4 评估与门禁 | 3 天 | golden set、人工评分、schema/safety/grounding/latency/cost 指标、发布 Gate | 未达到阈值不发布；评估结果不伪装成教育效果证明 |
| S5 音频/视频预研 | 4 天 | 供应商能力/合规清单、异步渲染 Job 契约、权利和删除测试 | 只完成 research/contract；没有批准就不打开生产路由 |

## 5. “拿来主义”的使用规则

可以直接采用：状态机、事件模型、结构化输出、文件引用、Webhook/轮询、Skill/Tool 注册、attempt ledger、人工确认和 artifact 版本思路。

不能直接采用：供应商密钥、第三方默认数据处理条款、未授权的 Bole/AiSoul 原始样本、Manus 私有 prompt/模型推断、把平台演示数据当成家庭教育效果、把任何外部 agent 的成功状态当成 AiFamily 业务事实。

## 6. 下一步实现清单

1. 将 `MediaInput` 纳入 Model Gateway 公共导出，并补齐 Web Experience Run 的最小应用服务。
2. 用 FakeProvider 完成 S1 contract tests，再由治理登记驱动真实 provider 的 internal livecheck；未批准前不接收真实家庭/未成年人数据。
3. 在 Web UI 中实现“生成草稿—查看 provenance—提交反馈—回放 attempt”四个动作；不实现 Mobile 页面。
4. 将 Bole 场景库仅作为评估候选导入管道，不将其写入 Family 主数据或知识事实。
5. 每个切片完成后运行 `uv run pytest tests/architecture -v`、相关领域/网关测试和 `uv run ruff check .`，再由 ADR/注册表决定是否晋级。

**RESEARCH_ONLY / NOT_CANONICAL**
