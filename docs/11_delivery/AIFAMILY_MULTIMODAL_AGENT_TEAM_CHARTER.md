---
id: DLV-AIFAMILY-AGENT-TEAM-001
title: AiFamily 多模态 AI 体验子项目 Agent 团队章程
type: delivery-specification
status: draft
version: 1.0
owner: AG-00
created: 2026-08-30
updated: 2026-08-30
canonical: false
evidence_class: NOT_CANONICAL
---

# AiFamily 多模态 AI 体验子项目 Agent 团队章程 V1

> 本章程只约束本子项目的敏捷协作、编号、战场和交付责任，不改变系统宪章、领域边界或供应商准入决策。
> 子项目范围为 Web UI 的多模态 AI 体验；移动端、未经准入的真实家庭数据和直接供应商调用不在授权范围内。

## 1. 项目目标与成功定义

### 1.1 目标

用成熟多模态 LLM 先跑通一条可回放的 Web 纵向切片：

```text
文字/图片输入
  → 同意、权限、媒体登记
  → Model Gateway 结构化生成
  → AI 解释、节奏、反馈、叙事和难度建议
  → 用户接受/改写/跳过/暂停/人工接管
  → 真实行动事件、反馈、评估和回放
```

### 1.2 成功定义

本项目的“极致用户体验、极致游戏感、极致成就感”必须由 AI 在授权上下文内动态实现：

- AI 根据真实上下文生成个性化节奏、即时反馈、成长叙事和下一步难度；
- Web UI 让用户随时知道当前状态、可以选择、暂停、重试、回到上次位置或请求人工；
- 成就不是模型叙事或预设奖励，而是由真实 `ExperienceEvent`、`ActionOutcome` 等行动事件触发，能够回放并引用证据；
- 不以虚构积分、家庭总分、家庭排名、儿童商业画像或焦虑刺激来替代成长体验。

“模型能回答”不等于项目成功。成功必须同时具备可调用路径、失败路径、治理证据和可复现测试。

## 2. 团队编号与角色

编号只在本子项目内使用，绑定角色而非单次任务；编号永不复用。每个 Agent 必须只修改自己的战场，跨战场需求通过交付说明或由 AG-00 安排集成窗口处理。

| 编号 | 角色 | 核心职责 | 独占战场 | 不得修改 |
|---|---|---|---|---|
| **AG-00** | 总 PM / 集成负责人 | 目标、优先级、Sprint、依赖协调、集成、验收、风险和发布闸门 | `docs/11_delivery/`、集成记录、项目看板 | AG-01~04 的实现战场；不得为“过绿”改动他人测试断言 |
| **AG-01** | 产品与敏捷 PM | 市场洞察、竞品证据、IPD/PDM/PLM 切片、用户故事、验收标准、体验与商业价值假设 | `docs/01_strategy/`、`docs/02_business/`、`docs/03_product/`、本章程引用的产品交付文档 | `backend/`、Web 实现、治理 YAML；不得把未核验竞品内容写成事实 |
| **AG-02** | AI Runtime / Model Gateway | 多模态契约、Provider Adapter、Agent/Skill 编排、Run 状态、Prompt/Schema、Provenance、成本和评估 | `backend/intelligence/` 及对应 `tests/intelligence/` | 领域 Repository、Web 页面、业务事实表；不得直接 import 供应商 SDK |
| **AG-03** | Web 体验工程 | Web Experience Studio、输入/媒体状态、Run 状态、草稿查看、确认/反馈/暂停/回放、无障碍和可访问性 | 独立 Web 前端目录（若尚未建立则由 AG-00 先登记路径）及其专项测试 | `backend/intelligence/`、`backend/domains/`、治理文件；不得用硬编码假 AI 结果冒充能力 |
| **AG-04** | QA / 合规 / 评估与发布守护 | 测试策略、拒绝集、gold set、架构与合规检查、故障注入、环境 parity、发布/回滚证据 | `tests/architecture/`、专项 QA/Eval 夹具、发布检查记录 | 未授权业务实现；不得为了通过 CI 放宽规则或删除失败测试 |

### 2.1 AG-00 的最终责任

AG-00 对“是否可以标记完成”负最终责任，但不替代专业 Agent 实现。只有当代码、测试、文档、治理和回滚证据齐全时，AG-00 才能把任务标为 `DONE_WITH_EVIDENCE`；供应商生产准入仍需合规和项目负责人批准。

## 3. 角色输入、输出和依赖

| Agent | 必须输入 | 必须输出 | 主要依赖 |
|---|---|---|---|
| AG-00 | 当前基线、项目目标、各 Agent 报告、CI/测试结果 | Sprint 目标、任务卡、依赖裁决、集成记录、验收结论、风险/阻塞台账 | 全体 Agent、canonical docs、治理闸门 |
| AG-01 | 用户场景、市场/竞品证据、三区方法论、IPD/PDM/PLM 文档 | 用户故事、价值假设、场景流程、优先级、验收矩阵、产品版本边界 | AG-00 目标；AG-04 证据质量反馈 |
| AG-02 | AG-01 的验收 schema、授权上下文、Model Gateway 契约、供应商准入状态 | 可审计的结构化请求/响应、Run/Attempt、Prompt/Schema 版本、Provenance、AI 失败语义 | AG-01 schema；AG-04 评测与安全用例；平台授权/同意能力 |
| AG-03 | AG-01 用户流程和状态字典、AG-02 API/事件契约、视觉与无障碍要求 | 可运行 Web 纵向切片、状态呈现、反馈/确认/暂停/回放交互、前端测试 | AG-02 契约；AG-04 可访问性与端到端验收 |
| AG-04 | 所有 Agent 的变更、测试、gold set、拒绝矩阵、合规约束 | 实测测试输出、咬人验证、质量报告、发布 Gate、阻塞与回滚建议 | AG-00 范围；AG-02 评估指标；AG-03 可访问性路径 |

依赖原则：上游未给出可执行契约时，下游不得自行发明第二套对象；发现缺口必须提交 `BLOCKED` 报告，由 AG-00 裁决是补契约、缩小切片还是暂停任务。

## 4. 敏捷实施任务分解

### Sprint 0：团队与契约对齐

- AG-00：冻结 Web-only 范围、任务卡模板、状态机和集成窗口。
- AG-01：把市场洞察、竞品证据和真实家庭场景转成 P0 用户故事。
- AG-02：确认 text/image 首批模态，统一 `StructuredRequest`、`MediaInput`、Provenance 和错误码。
- AG-03：产出 Experience Studio 低保真交互和状态清单。
- AG-04：建立匿名/合成 gold set、拒绝集、合规检查和验收脚本。

退出条件：所有 P0 故事有输入/输出/异常/权限/测试定义；未准入 provider、无同意、越权媒体、schema 错误至少各有一条可重复拒绝测试。

### Sprint 1：文字 + 图片 Web 纵向切片

- AG-01：验收“输入—理解草稿—用户选择”的最小体验，并冻结文案与可解释性要求。
- AG-02：通过 Model Gateway 生成 DRAFT；记录 attempt、版本、媒体 hash、延迟和成本（可得时）。
- AG-03：实现输入、上传、loading、success、refused、timeout、retry、human review 和 draft 展示。
- AG-04：执行成功、失败、超时、未准入、跨租户和原始媒体不入日志测试。
- AG-00：完成纵向集成演示和退出评审。

退出条件：Web sandbox 能完成一次真实契约调用；模型不可用时有可恢复错误；AI 输出仍为 `DRAFT`，不写入 canonical Fact。

### Sprint 2：游戏化体验、成就和可恢复闭环

- AG-01：定义“节奏、反馈、叙事、难度、成就”的体验验收，不把点击量当成长效果。
- AG-02：将授权上下文和真实事件注入 AI 生成链路，提供可回放的 Run、checkpoint 和反馈输入。
- AG-03：实现接受、改写、跳过、暂停、恢复、请求人工、反馈和回放；展示证据与可调整项。
- AG-04：验证成就只能由真实行动事件触发，验证重复提交、删除、重启、回放和人工闸门。
- AG-00：裁决是否进入 Pilot，登记所有未完成能力。

退出条件：成功、拒绝、暂停、恢复、人工升级、删除、重放均有实测证据；不存在虚构积分、家庭总分、家庭排名或模型直接改事实的路径。

### Sprint 3：评估与多模态扩展准备

- AG-01：基于市场反馈更新需求优先级和产品版本假设。
- AG-02：完成模型/Prompt/Schema 版本比较、成本预算和音频/视频异步契约预研。
- AG-03：完善低带宽、替代文本、媒体权限和多语言体验。
- AG-04：生成质量、安全、延迟、成本、可访问性和环境 parity 报告。
- AG-00：以证据决定是否扩大到音频/视频；未达阈值不得打开生产路由。

### Sprint 1 当前看板（2026-08-30）

以下是本轮“文字 + 图片 → Web 草稿”的实际派工状态。状态是项目管理状态，不替代 AG-00 对代码、测试和交付证据的最终复核。

| 编号 | 当前任务 | 状态 | 下一动作 | 依赖/交付证据 |
|---|---|---|---|---|
| **AG-01** | 产品验收、体验/游戏感/成就感验收矩阵 | `IN_PROGRESS` | 固化 P0 用户故事和 Sprint 1 Review 清单 | 本章程 §1、§5、§7；等待纵向切片演示 |
| **AG-02** | Engagement / Model Gateway 多模态体验链路 | `COMPLETED` | 将完成项交 AG-00 集成复核，补齐缺证据 | Gateway/Experience 代码、定向测试和 provenance 记录 |
| **AG-03** | Web Experience Studio API/状态契约 | `READY_FOR_REVIEW` | 由 AG-04 复核 `frontend/web/` 的组件、契约和端到端测试 | 独立 Vite/React Web 已可运行；待完成市场洞察/竞品证据对象接入 |
| **AG-04** | QA、合规、gold set、拒绝集和发布 Gate | `READY_FOR_REVIEW` | 对接 Web 实现后执行端到端、拒绝和无障碍验收 | 测试矩阵、拒绝路径和环境 parity 检查 |
| **AG-00** | 集成、QA 复核、阻塞裁决和 Sprint Review | `IN_PROGRESS` | 安排 Sprint 1 Review，核对 AG-02/AG-03 实测证据 | 依赖 AG-03 交付复核和 AG-04 验收 |

#### Sprint 1 历史阻塞（已解除）

AG-03 已交付可运行的独立 Vite/React `frontend/web/`，因此“没有 Web 宿主”这一阻塞已于 2026-08-30 解除。当前仍需 AG-04 对组件、契约和端到端路径进行复核；该复核不等同于 Model Gateway 或体验契约已获生产准入。

- **解除负责人**：AG-00（登记/集成）+ AG-03（建立实现）；
- **解除证据**：`frontend/web/` 的 Vite/React 工程、组件测试和 Playwright 场景已存在；AG-00 需在 Review 中复跑命令并记录输出；
- **后续未决**：市场洞察/竞品证据对象尚未进入 `CreateDraftInput`，不应把当前 Web DRAFT 展示描述为完整市场洞察链路。

### Sprint 2 当前看板与用户故事（2026-08-30）

Sprint 2 的交付主线固定为：

```text
需求 → 市场洞察 → 竞品分析 → 体验草案 → 人工确认 → 交付反馈
```

| 编号 | Sprint 2 工作包 | 状态 | 本轮输出 | 依赖/下一动作 |
|---|---|---|---|---|
| **AG-01** | 需求证据、市场洞察、竞品分析和 IPD 用户故事 | `IN_PROGRESS` | 5 条用户故事、证据卡模板、验收矩阵 | 需要 AG-04 复核证据完整性 |
| **AG-02** | 证据引用 → AI 体验草案的 Model Gateway 链路 | `READY_FOR_DEV` | 结构化输入、provenance、DRAFT 输出和反馈事件契约 | 依赖 AG-01 的 schema；继续使用 Gateway 唯一入口 |
| **AG-03** | Web 体验草案、人工确认和交付反馈界面 | `BLOCKED` | 契约已完成；等待 `frontend/web/` 宿主实现 | 唯一阻塞解除后接入输入、草案、确认、反馈和回放 |
| **AG-04** | 需求/竞品证据 gold set、拒绝矩阵和验收检查 | `READY_FOR_REVIEW` | 来源完整性、未知项、AI 草案边界和拒绝用例 | 等待 AG-02/AG-03 实现后执行端到端验收 |
| **AG-00** | Sprint 2 集成、依赖裁决和 Review | `IN_PROGRESS` | 统一任务卡、集成窗口和阻塞台账 | 保持唯一阻塞登记；不以文档完成替代 Web 证据 |

#### Sprint 2 用户故事与验收

**S2-US1｜家长提交可追溯的真实需求**

- 作为家长，我可以在 Web 记录一个具体处境、涉及主体、期望改变和时间范围，并看到系统如何区分我的原话、系统观察和待验证假设。
- 验收：需求记录含 `tenant/family/subject/purpose/locale`、来源引用、同意状态和幂等键；缺少主体范围或同意时明确拒绝；AI 只能生成 `DemandPerspective(DRAFT)`，不得写成家庭事实。
- 证据要求：原始输入引用（脱敏）、用户确认时间、授权/同意引用、需求事件 ID；若来自访谈或客服，必须有来源类型、采集日期和去标识说明。

**S2-US2｜从需求生成有来源的市场洞察草案**

- 作为产品经理，我可以把需求证据卡交给 AI，得到问题模式、目标人群假设、场景频次线索和待验证问题，并逐条追溯到来源。
- 验收：每个结论带 `evidence_refs`、时间范围、适用范围、置信度和“事实/推断/未知”标签；无来源、过期或互相矛盾的证据必须显式标记，不得补写；输出状态固定为 `DRAFT`/`PROPOSED`。
- 证据要求：使用的用户证据卡、检索/分析时间、模型与 Prompt/Schema 版本、Context Snapshot 引用、人工复核记录；市场洞察未经过人工确认不得进入产品主数据。

**S2-US3｜基于证据做竞品能力分析，而非主观排名**

- 作为产品经理，我可以按统一维度查看竞品在场景覆盖、交互、多模态、交付和治理方面的公开证据、未知项及可借鉴做法。
- 验收：每个竞品声明至少有可访问来源、发布日期/检索日期、原文定位、来源类型和适用范围；无法核验的内容标为 `UNKNOWN`；不得生成“最好/最差”或家庭教育效果排名，不得把宣传语当作效果事实。
- 证据要求：官方文档/产品页面/公开演示/用户授权材料优先；二手评论只能作为线索并标低置信度；保留来源快照哈希或归档引用，避免链接变化导致不可复查。

**S2-US4｜由需求与市场洞察生成可审查的体验产品草案**

- 作为产品设计者，我可以选择已确认范围内的需求和市场洞察，生成一个 Web 多模态体验草案，包含目标、步骤、输入模态、反馈机制、难度调整和成就触发条件。
- 验收：草案引用需求/洞察证据，列出组件/Skill、模型版本、限制与风险；AI 输出为 `ProductDraft(DRAFT)` 或 `Recommendation(PROPOSED)`，不能直接创建 Family/Growth/Service/Commerce 事实；成就条件必须指向真实 `ExperienceEvent`/`ActionOutcome`。
- 证据要求：需求与洞察 ID、组件/Skill 版本、Model Gateway provenance、生成时间、schema 校验结果、拒绝/安全检查结果；未提供证据的体验主张标为待验证假设。

**S2-US5｜人工确认并用交付反馈驱动下一轮迭代**

- 作为产品负责人或家庭用户，我可以接受、修改、拒绝、暂停或请求人工处理体验草案，并在交付后提交可定位到版本和行动事件的反馈。
- 验收：每个决定记录 actor、reason、scope、时间、前后版本、人工闸门和审计 ID；拒绝或暂停可恢复；交付反馈能关联到产品版本、Run、Recommendation 和真实行动事件；反馈只进入评估/下一轮需求，不自动改写既有事实。
- 证据要求：`RecommendationDecision`、`FeedbackSignal`、`DeliveryRecord`、审计事件、回放链接和删除证明（适用时）；AI 生成的成就叙事必须能回放到真实事件，不能凭空增加积分、等级、家庭总分或排名。

#### 统一证据来源规则

所有 Sprint 2 用户故事使用以下来源分层，并在交付物中保留来源引用：

| 来源层 | 可证明内容 | 最低字段 | 不能证明 |
|---|---|---|---|
| **A：用户/业务证据** | 家庭表达、已发生行动、交付反馈 | `source_ref`、主体范围、采集时间、同意/授权、去标识说明 | 不能单独证明市场规模或教育效果 |
| **B：市场/竞品证据** | 产品公开能力、定价/流程、已声明特性 | URL/文档引用、发布日期、检索日期、原文定位、来源类型、快照/哈希 | 不能把宣传语推导成真实效果或用户偏好 |
| **C：系统/运行证据** | 契约、测试、Trace、模型版本、交付结果 | request/run/attempt ID、版本、测试命令输出、审计/回放引用 | 不能把测试夹具当生产能力 |

AI 可以组合 A/B/C 生成洞察、竞品分析和体验草案，但所有 AI 产物都必须标注为视角、建议或假设；只有经过命名动作和人工确认，才能进入后续产品交付流程。

### 跨 Agent 对齐结论与未决项（Sprint 2，2026-08-30）

本节基于 AG-02 Model Benchmark 交付摘要、`backend/intelligence/experience/model_benchmark.py` 与 `MULTIMODAL_LLM_SELECTION.md`，以及 AG-03 `frontend/web/` 交付摘要和 `frontend/web/src/api/client.ts`、组件测试的现场核对。结论用于联调，不替代 AG-00 的最终验收。

#### 已对齐的验收映射

| 用户故事 | AG-02 模型评估/治理映射 | AG-03 Web 交互映射 | 当前结论 |
|---|---|---|---|
| **S2-US1 需求输入** | gold case 必须包含匿名处境、模态、期望 schema 和安全标签；benchmark 只能证明结构化/安全表现，不能证明需求真实性；provenance 至少含 request/context/prompt/schema/version | `ExpressionInput` 支持文字、图片 `media://` 引用、scope、purpose、locale、consent；缺同意或 scope 时拒绝 | 输入和治理边界一致；需求证据对象仍需接入后端/前端契约 |
| **S2-US2 市场洞察** | evidence-bound case；质量分只代表 schema pass；结果保留 case/version/provenance；合规 Gate 前保持 DRAFT | DRAFT 的 evidence/provenance 区已预留，但尚未接 `MarketInsight`/`evidence_refs` 对象 | 只能展示“有来源的 AI 草案”，不能展示为已验证市场事实 |
| **S2-US3 竞品分析** | AG-04 注入来源证据哈希；benchmark 不含 ranking 字段，禁止最好/最差排名 | 当前 Web 尚无竞品证据对象和来源卡片 UI | 未决：竞品字段、来源快照和未知项展示契约 |
| **S2-US4 体验草案** | 质量=结构化通过率；安全=(安全通过率+拒答准确率)/2；成本=单位微美元；延迟=P95；`ModelBenchmarkSummary` 记录权重、Gate 和 `education_outcome_status=NOT_MEASURED` | `DraftResult` 展示 `understanding`、`next_step`、`limitations` 和 provenance；输出固定 `DRAFT` | 模型评估只能标为“契约质量/安全评估”，不能渲染成孩子或家庭成绩 |
| **S2-US5 人工确认/交付反馈** | Recommendation/Feedback/Delivery Record 应挂 candidate/model/version、run/attempt、benchmark report/case_version、Gate；反馈进入下一轮评估；成就引用真实 ExperienceEvent | `DecisionActions` 支持 confirm/rewrite/reject/human；`FeedbackActions` 支持 helpful/not_helpful；已有删除和 `ReplayTimeline` | 决策/反馈交互已具备；关联字段和生产 API 命名待 AG-00 裁决 |

#### 统一字段建议（待 AG-00 采纳）

为避免模型评估和 Web 交互各自造字段，建议在 Experience Draft/Replay/Feedback 契约中使用以下可选治理字段：

```text
benchmark_report_ref
case_version
candidate_id / provider_id / model / model_version
quality_score / safety_score / cost_score / latency_score / composite_score
score_weights
benchmark_gate_status / failures
education_outcome_status = NOT_MEASURED
provenance_ref / human_gate_ref / feedback_ref
draft_version / attempt_id / real_event_refs
```

Web 只把上述字段作为“契约质量、安全评估、来源和版本”显示；`BLOCKED` 只显示不可运行/仅研究状态。`ReplayTimeline` 为只读投影，不重新调用 Gateway。任何成就展示都必须携带真实事件引用。

#### 未决项与责任人

| 未决项 | 影响 | 责任人 | 解除条件 |
|---|---|---|---|
| `CreateDraftInput` 是否增加 `demand_ref`、`market_insight_refs`、`competitor_analysis_refs` | US1→US4 无法形成可追溯输入链 | AG-00 + AG-01 + AG-02 | 评审后冻结字段、版本和空值/拒绝语义，并补契约测试 |
| `DeliveryRecord`、`Recommendation`、`Feedback` 的关联 ID 命名 | US5 无法跨 Web、Gateway、评估回放 | AG-00 + AG-02 + AG-03 | 选定 `run_id`/`attempt_id`/`draft_version`/`feedback_ref` 映射并写入 API 契约 |
| Web 的 `MarketInsight`/竞品证据卡片和未知项展示 | US2/US3 只能看到通用 provenance，无法审查证据 | AG-03 + AG-01 | `frontend/web/` 新增证据对象只读投影、来源快照和 `UNKNOWN` 状态测试 |
| 真实匿名 gold set、供应商正式准入和价格运行记录 | 无法从离线 benchmark 晋级 Pilot/生产 | AG-02 + AG-04 | gold set 版本化、DPIA/安全/转委托/删除资料齐全，Gate 变为 `ELIGIBLE` |

当前没有新增的 Sprint 2 阻塞；上述项目是 Sprint 2 的未决决策/后续任务。唯一已记录的 Web 工程阻塞已在本章程“Sprint 1 历史阻塞（已解除）”中关闭。Sprint 3 另有“真实后端 runtime resolver 尚未接入”的接线前置条件，见下节；在该条件满足前不得宣称生产 API 已接通。

### Sprint 3 下一迭代看板：真实后端 API 接线

Sprint 3 不再以 Fake client 或前端 seam 作为纵向切片的终点，目标是将 `frontend/web` 接到真实的 Family API Experience 路由；Model Gateway 仍是唯一模型入口，后端默认未配置时必须保持 fail-closed。

| 编号 | 工作包 | 状态 | 交付目标 | 进入/退出条件 |
|---|---|---|---|---|
| **S3-API-01 / AG-00** | API 路由、依赖注入和集成 | `READY_FOR_DEV` | 将 Web client 接入 `POST /families/{family_id}/experience/multimodal/drafts` 及决策/反馈/删除/回放端点 | 进入：AG-02 契约冻结；退出：真实 runtime resolver 注入且 HTTP 集成测试通过 |
| **S3-API-02 / AG-02** | 后端 runtime resolver 与 Gateway | `IN_PROGRESS` | 服务端解析 scope/consent/context/environment，组装 `StructuredRequest` 并返回 DRAFT/provenance | 进入：身份/授权/同意端口可用；退出：拒绝路径 provider invocation=0 |
| **S3-API-03 / AG-03** | Web HTTP client 接线 | `READY_FOR_DEV` | 用真实 API 替换生产路径 fake seam，保留 fake 仅作测试适配器 | 进入：请求/响应字段冻结；退出：Web smoke/e2e 覆盖成功、拒绝、超时、删除、回放 |
| **S3-API-04 / AG-04** | Contract freeze 与环境 parity Gate | `READY_FOR_REVIEW` | 验证字段、错误语义、租户隔离、DRAFT-only、fail-closed、回放不重算 | 退出：命令输出、trace、审计、回放和回滚证据齐全 |
| **S3-API-05 / AG-01** | 用户故事与交付反馈对齐 | `IN_PROGRESS` | 将 S2-US1~US5 的来源、草案、人工确认和反馈字段映射到 API | 退出：每条故事均能关联 request/run/draft/decision/feedback |

#### API Contract Freeze 验收标准

以下标准是 Sprint 3 的合约冻结门。未满足任一条，状态只能是 `PARTIAL` 或 `BLOCKED`，不得把前端页面或 Fake client 结果描述为真实后端能力。

**1. 客户端请求只提交生成意图**

`POST /families/{family_id}/experience/multimodal/drafts` 的 JSON 请求允许字段冻结为：

```text
run_id
prompt_version
schema_version
payload
output_schema
modalities
estimated_input_tokens
strategy
max_latency_ms
max_cost_microusd
input_refs
media_inputs
session_id
```

请求模型必须 `extra=forbid`；客户端不得嵌套或覆盖 `tenant_id`、`family_id`、`subject_ids`、`purpose`、`consent`、`environment`、`context_snapshot`、provider、secret 等受信字段。`media_inputs` 只传受控 URI/hash，不传原始儿童媒体 bytes。

**2. Scope/Consent 必须由服务端解析**

服务端从已认证的路径、身份、授权和同意解析 `tenant/family/subject/purpose/data_class/locale/consent_version/environment/context_snapshot`，再构造 runtime；不能信任请求体同名字段。缺同意、跨租户/主体、过期或已撤回上下文时，必须在调用 Provider 前拒绝，且证据包含 `provider_invocation=0`、拒绝码、scope 和审计/trace 引用。

**3. 成功响应固定为 DRAFT + Provenance**

成功响应至少冻结以下字段：

```text
run_id
status = DRAFT
output
requires_human_confirmation = true
scope{tenant_id, region_id, family_id, subject_ids, purpose,
      consent_version, consent_granted, data_class, locale}
context_snapshot_ref
context_snapshot_expires_at
provenance{provider_id, model, model_version, prompt_version,
           schema_version, context_snapshot_ref, latency_ms,
           data_class, use_case, confidence, generated_at}
route{provider_id, vendor, model, model_version, strategy,
      estimated_latency_ms, estimated_cost_microusd,
      fallback_provider_ids}
```

输出必须保持 `DRAFT`，不得直接写入 Family/Growth/Service/Commerce canonical Fact；`requires_human_confirmation` 必须为真。Web 可显示契约质量、安全和来源，但不得渲染为孩子或家庭成绩。

**4. Provider 准入与 fail-closed**

未配置 runtime resolver、无有效同意、策略/区域/数据分类不允许、Provider 未通过准入或预算/延迟约束无法满足时，API 必须返回稳定可识别的拒绝/不可用状态，不调用 Provider、不生成确定性假 AI 文案、不自动切换未经准入的 fallback。测试必须证明拒绝情况下 `provider_invocation=0`，并能安全重试或转人工。

**5. 回放只读且不重算**

`GET /families/{family_id}/experience/multimodal/runs/{run_id}/replay`（或等价端点）只能读取已持久化的 run/checkpoint/attempt/event 投影；回放不得重新调用 Gateway、重新计算模型输出、更新业务事实或产生新的 Recommendation/Feedback。相同幂等键重复请求不得产生双重事件、审计或副作用。

**6. 评估与成本字段的诚实边界**

当前后端 response 已有 `route.estimated_cost_microusd`，它只能表示估算；`actual_cost`、`attempt_id`、`benchmark_report_ref` 是否进入生产 response 仍为 `TBD`。在这些字段冻结前，AG-00 不得声称成本账单或模型 benchmark 已与一次真实 API 调用完成绑定；离线评估仍需使用 `education_outcome_status=NOT_MEASURED`。

**7. 接线完成证据**

至少提供：真实 HTTP 成功测试（DRAFT/provenance）、缺同意/跨 scope/未准入测试（provider invocation=0）、超时/重试/幂等测试、删除测试、回放不重算测试、Web smoke/e2e 输出、请求与响应 schema 版本、trace/audit 引用和回滚方式。只有 AG-04 复核通过并由 AG-00 记录集成结论，S3-API-01 才能进入 `DONE_WITH_EVIDENCE`。

### Sprint 4 看板：真实 API 验收与决策/反馈端点对齐

Sprint 4 以“真实后端可验证接线”为目标，但必须区分已实现路由、候选命名和未完成能力。当前后端只确认 draft POST 路由；决策、反馈、删除和回放尚未挂 HTTP，不能把 Web Fake client 演示当作后端完成证据。

| 编号 | 工作包 | 状态 | 最小交付 | 依赖/验收 |
|---|---|---|---|---|
| **S4-API-01 / AG-02** | Runtime resolver 与真实 draft API | `BLOCKED` | 接入身份、授权、同意、Context Snapshot 和环境 resolver | 解除条件：TestClient 成功 DRAFT；生产未配置时 503 fail-closed；拒绝路径 provider invocation=0 |
| **S4-API-02 / AG-00** | Family API 路由挂载与 OpenAPI | `READY_FOR_DEV` | 挂载并锁定 `POST /families/{family_id}/experience/multimodal/drafts` | 依赖 AG-02 resolver；OpenAPI 路径、请求/响应 schema 与版本快照可复核 |
| **S4-API-03 / AG-03** | Web HTTP client 接线 | `READY_FOR_REVIEW` | draft POST 使用真实 API；决策/反馈/删除/回放先保持 seam，禁止臆造 URL | 真实 draft API 通过后，补错误语义和 smoke/e2e；候选端点待后端确认 |
| **S4-API-04 / AG-04** | 最小验收证据与回归 Gate | `READY_FOR_REVIEW` | 成功、拒绝、scope、生产 fail-closed、幂等和 DRAFT/provenance 证据 | 指定 pytest、OpenAPI、Web 测试输出齐全；未完成端点标记 `TBD` |
| **S4-API-05 / AG-01** | 端点语义与用户故事追踪 | `IN_PROGRESS` | 将 S2-US1~US5 映射到 draft/decision/feedback/replay 资源 | 不允许把 AI 草案当事实；人工确认和真实事件引用保持显式 |

#### Runtime resolver / 真实 draft API 最小验收证据

AG-02 与 AG-00 对齐的最小证据集如下；未达到前，S4-API-01 只能保持 `BLOCKED`：

1. 运行 `uv run pytest tests/apps/family_api/test_experience_router_mount.py tests/apps/family_api/test_experience_wiring.py -q`，并贴出实际输出。
2. OpenAPI 必须出现 `POST /families/{family_id}/experience/multimodal/drafts`，请求只允许 Contract Freeze §1 的 generation intent 字段。
3. 显式安装 `install_synthetic_experience_runtime(..., environment="test")` 的 TestClient 成功返回 `status=DRAFT`、`requires_human_confirmation=true` 和服务端解析的 `scope.family_id`；非 `test` 环境安装 synthetic runtime 必须抛 `ValueError`。
4. production/AIFAMILY_ENV=production 未安装 synthetic runtime 时，返回 503 `multimodal_experience_runtime_not_configured`；不能自动降级为假 AI 文案。
5. 缺 consent、跨 scope、过期/撤回上下文和未准入 Provider 的测试必须证明 Provider invocation 为 0（可检查 FakeProvider invocations 或 Attempt ledger），并保留拒绝码、trace/audit 引用。
6. 成功路径必须保留 `run_id`、`provenance` 和 `route`；输出固定为 `DRAFT`，不写 canonical Fact。相同幂等键不得产生重复副作用。
7. Replay 证据必须来自已持久化的 run/checkpoint/attempt/event 投影，不能重调 Gateway 或重算模型；删除必须有删除状态/证明。当前后端尚无这些 HTTP routes，故此项是 Sprint 4 后续交付，不得标为已完成。

#### 决策、反馈、删除、回放端点命名对齐

下表是 AG-03 提议、AG-02/AG-00 待确认的统一命名。标为 `PROPOSED_TBD` 的端点在后端实际挂载前，Web `HttpExperienceApiClient` 不得实现或声称可用；Fake client 仅用于测试。

| 语义 | 建议 HTTP 端点 | 最小请求/查询 | 最小响应/状态 | 当前状态 |
|---|---|---|---|---|
| 草案生成 | `POST /families/{family_id}/experience/multimodal/drafts` | generation intent；`Idempotency-Key` header | `run_id,status=DRAFT,scope,context_snapshot_ref,provenance,route` | **IMPLEMENTED / 待 resolver 生产接线** |
| 决策确认 | `POST /families/{family_id}/experience/multimodal/runs/{run_id}/decisions` | `decision=confirm\|rewrite\|reject`、`draft_version`、改写文本/理由（适用时）；`Idempotency-Key` | `run_id,status,decision_ref,human_gate_ref,audit_ref` | **PROPOSED_TBD** |
| 反馈 | `POST /families/{family_id}/experience/multimodal/runs/{run_id}/feedback` | `signal`、`reason`、`draft_version`、`attempt_id`、`candidate_id`、`model_version`、`benchmark_report_ref`、`real_event_refs`；幂等 header | `run_id,feedback_ref,recorded` | **PROPOSED_TBD** |
| 请求人工 | `POST /families/{family_id}/experience/multimodal/runs/{run_id}/human-review` | `reason`、影响范围；幂等 header | `run_id,status=human_review,human_gate_ref` | **PROPOSED_TBD** |
| 删除 | `DELETE /families/{family_id}/experience/multimodal/runs/{run_id}` | 删除原因/幂等 header（不得传媒体 bytes） | `run_id,status=deleted,deletion_ref` | **PROPOSED_TBD** |
| 回放 | `GET /families/{family_id}/experience/multimodal/runs/{run_id}/replay` | 只读 scope；不得触发生成 | `run_id,entries,event_sequence,source_refs` | **PROPOSED_TBD** |

命名原则：所有端点以 `runs/{run_id}` 表示同一 Experience Run；`decision_ref`、`feedback_ref`、`human_gate_ref`、`deletion_ref` 和事件引用必须能回到审计/回放链。Replay 是只读投影，不重新调用 Gateway；任何决策或反馈都不能直接把 AI 草案写成 Family/Growth/Service/Commerce 事实。

#### Sprint 4 未决项

- runtime resolver 的真实身份、授权、同意和 Context Snapshot 组合根尚未接入；默认 API 仍应 503 fail-closed。
- 决策/反馈/人工/删除/回放端点尚无后端实现，以上 URL 和字段在 AG-00/AG-02/AG-03 确认前均为 `PROPOSED_TBD`。
- `attempt_id`、`benchmark_report_ref`、实际成本等运行字段是否进入生产响应仍需 AG-02 与 AG-04 根据评估和合规证据冻结。
- Web 已有 Fake client 的 16 个单元测试和 1 个 Playwright 场景只能证明交互 seam，不能证明真实后端能力；真实 API 接线后需重新执行同等路径。

### Sprint 5 看板：Durable Run ledger 验收矩阵

基于 AG-02 的 `backend/intelligence/experience/run_http.py` 与 `tests/intelligence/experience/test_run_http.py` 交付摘要，本 Sprint 将一次体验运行（Run）定义为 AI Runtime 的 append-only 账本：模型生成只建立 `DRAFT` checkpoint，用户决策、反馈、人工请求和删除只追加交互事件，不直接写入任何业务事实。

| 编号 | 工作包 | 状态 | 当前证据 | 集成边界 |
|---|---|---|---|---|
| **S5-RUN-01 / AG-02** | RunScope、DRAFT checkpoint、InteractionReceipt 与 HTTP routes | `PARTIAL` | 7 个 run_http 测试 + 2 个 HTTP route 测试通过；draft/decision/feedback/human-review/delete/replay 已挂载 | 创建调用幂等为 P0；SQL 重启持久化、真实 Human Gate、派生媒体删除和强 evidence 校验仍为 `PARTIAL` |
| **S5-RUN-02 / AG-03** | Web 决策/反馈/删除/回放映射 | `READY_FOR_REVIEW` | 后端 routes 已交付；Web Fake 可演示 receipt/status/replay，真实 HttpClient 仍待接线 | 等 Web HTTP client 接入和 e2e 复核；不得把 Fake 结果单独当生产证据 |
| **S5-RUN-03 / AG-04** | Durable Run 验收与故障注入 | `IN_PROGRESS` | 矩阵见下表；需补 provider invocation、审计和重启证据 | 通过后才可进入 `DONE_WITH_EVIDENCE` |
| **S5-RUN-04 / AG-00** | 持久化/HTTP 集成与发布裁决 | `IN_PROGRESS` | HTTP routes 已挂载；RunStore 与 run_http ledger 尚未统一 | 决定内存 ledger→SQLAlchemy 的唯一持久化路径，补真实 Gate/删除证据 |
| **S5-RUN-05 / AG-01** | 用户故事与交付反馈追踪 | `IN_PROGRESS` | S2-US4/US5 可关联 run/decision/feedback/event | 反馈只用于评估和下一轮需求，不改变 canonical Fact |

#### Durable Run 验收矩阵

| 操作 | 必须保留的 evidence | DRAFT-only / 安全语义 | 当前验收状态 |
|---|---|---|---|
| **create_draft** | `run_id`、`request_ref`、`RunScope(tenant/family/subjects)`、`idempotency_key`、checkpoint ID、artifact refs、event sequence、时间 | 创建 Durable Run 后只能有 `status=DRAFT` checkpoint；`draft_payload` 拒绝 `family_score/family_rank/ranking/canonical_fact` 等键；`may_mutate_business_state=false`；artifact 只允许引用，禁止 data URL/原始媒体 | **HTTP + 内存 ledger 已交付；调用幂等 `PARTIAL/P0`**（当前 Gateway 可能先于 ledger，重试会重复 invocation/计费）；SQL 重启持久化仍 `PARTIAL` |
| **decision** | `event_id`、`run_id`、完整 scope、`interaction_type=decision`、`payload.decision`、幂等键、sequence、occurred_at；重复请求返回 `status=replayed` | `accepted/rewrite/rejected/pending_human_confirmation` 只是交互记录，不是事实写入；升级为 Named Action/业务事实必须另过 Human Gate、审计和授权 | **已交付 HTTP + 追加/幂等**；真实 Human Gate/审计仍 `PARTIAL` |
| **feedback** | `event_id`、run/scope、`signal`、理由（如有）、`draft_version`/`attempt_id`/模型与 benchmark 引用（适用时）、真实事件引用、幂等键 | 反馈只能进入评估、产品迭代或后续建议；不得覆盖草案、改写事实或生成成就事实 | **已交付 HTTP + 追加/幂等**；强制模型/attempt/真实 event refs 校验仍 `PARTIAL` |
| **human-review** | `event_id`、run/scope、`reason`、`status=human_review`、人工闸门引用（接入后）、幂等键、审计引用 | 人工请求不等于批准；AI 草案仍保持 DRAFT，人工结果必须有明确决策和审计，不能静默转事实 | **已交付 HTTP + reason/status**；真实 Human Gate/审计仍 `PARTIAL` |
| **delete** | `event_id`、run/scope、`deletion_ref`、`status=deleted`、幂等键、级联对象列表/证明（接入外部存储后） | 删除是不可逆的展示边界；后续交互除同一删除幂等重放外全部拒绝；不返回草案 payload 或 artifact refs | **已交付 HTTP + 内存脱敏/幂等**；派生媒体、Context/embedding 删除仍 `PARTIAL` |
| **replay** | 只读 `RunReplaySnapshot`：run/scope、state、`status=DRAFT`、event sequence、interaction entries、draft/artifact refs（未删除时）、deletion state | 只能重放已存在的 run/checkpoint/event；不得调用 Model Gateway、重算模型、追加事件、写业务事实或生成新 Recommendation/Feedback；删除后 payload/artifact 必须为空 | **已交付 HTTP + 内存只读**；SQL 重启回放与持久化仍 `PARTIAL` |

#### 统一收口条件

1. `uv run pytest tests/intelligence/experience/test_run_http.py -q` 必须保持全绿；同时运行 `uv run ruff check backend/intelligence/experience/run_http.py tests/intelligence/experience/test_run_http.py` 并记录输出。
2. 每个交互事件的 evidence 至少能由 `event_id → run_id → scope → request/checkpoint → provenance/审计` 回溯；缺少上下游引用时只能标 `PARTIAL`。
3. 相同幂等键、相同 payload 必须返回 `replayed` 且不追加第二条事件；相同 key 不同 payload 必须拒绝并保留冲突证据。
4. 任一 scope 不匹配、已删除 Run、非法 decision status 或含家庭总分/排名/事实键的 payload 必须 fail-closed；不能通过 UI 文案掩盖拒绝。
5. `ReplaySnapshot.may_mutate_business_state` 固定为 `false`；Replay/Feedback/Decision 不能直接触发 domain repository、Named Action 或模型重算。
6. `run_http.py` 已经通过 HTTP routes 暴露 decision/feedback/human-review/delete/replay，但生产能力仍为 `PARTIAL`，直至真实审计/Human Gate、SQL 重启持久化、外部派生物删除和强 evidence 校验完成；不得标生产 `ADMITTED`。

#### Sprint 5 必须补测场景

以下场景是 HTTP routes 已交付后仍必须补齐或在集成环境复跑的验收项；已有内存单测不能替代这些证据：

1. **创建幂等与冲突（P0）**：必须先执行 `reserve/preflight(request fingerprint)`，再调用 Gateway，最后 `finalize` ledger；同一 `run_id + Idempotency-Key + payload` 重试返回同一结果、`provider_invocation=1` 且不新增 checkpoint/重复计费；同 key 改 payload 返回 409 并保留冲突证据；Provider 失败必须释放 reservation 并允许安全重试。
2. **全端点 scope 隔离**：以其他 tenant/family/subject 访问 decision、feedback、human-review、delete、replay，返回稳定 403/404，且不追加事件、不调用 Provider。
3. **幂等头强制**：所有 mutation 缺 `Idempotency-Key` 返回 422；同 key 不同操作或不同 payload 不得复用既有 receipt。
4. **Consent/Context fail-closed**：撤回、过期、删除中或缺少 consent 的 runtime 在任何模型调用前拒绝，证明 `provider_invocation=0`、拒绝码、trace/audit 均存在。
5. **决策与人工请求边界**：confirm/rewrite/reject 和 human-review 均追加 interaction，但不写 Family/Growth/Service/Commerce 事实；未接真实 Human Gate 时必须显式标 `PARTIAL`。
6. **反馈 evidence 完整性**：补测 `draft_version`、`attempt_id`、candidate/model、benchmark report 和真实 event refs 的合法/缺失/跨 scope 情况；在强校验完成前，缺字段不得被描述为完整 evidence。
7. **删除后语义**：delete 成功后 replay 返回 `deletion_state=deleted` 且 `draft_payload/artifact_refs` 为空；除同一删除幂等重放外，所有 mutation 返回 410；验证媒体派生物、Context/embedding 删除证明仍为待处理。
8. **Replay 不重算**：对 Gateway 注入 spy，调用 replay 不得触发模型、路由、事件追加或事实写入；状态、sequence、interaction 顺序与 ledger 一致。
9. **SQL 重启回放**：进程重启/新连接后仍可读取同一 Run、checkpoint 和 interaction，且幂等/删除状态不丢失；该项当前未完成。
10. **环境 parity 与生产 fail-closed**：test synthetic 可运行；production 未配置真实 resolver/ledger 时稳定 503，不回退 Fake；Web smoke/e2e 使用同一错误语义。

#### 仍保持 `PARTIAL` 的能力

| 能力 | 保持 PARTIAL 的原因 | 晋级条件 |
|---|---|---|
| SQL/耐久化重启 | `run_http` 当前为内存 ledger，尚未与 SQL RunStore 统一 | 迁移、事务、重启、幂等和跨实例回放测试通过 |
| 创建调用幂等与计费 | 当前 draft HTTP 路由在 ledger 写入前调用 Gateway，同一幂等键重试可能重复 invocation/计费 | reserve/preflight→Gateway→finalize 三段式；测试证明同 key 仅一次 invocation、冲突 409、Provider 失败可释放重试 |
| 真实 Human Gate 与审计 | 当前 human-review 只是 append interaction，未绑定真实人工闸门、actor、reason 和审计记录 | Human Gate/Named Action/审计链路接入并有拒绝、超时、重放证据 |
| 派生媒体/Context/embedding 删除 | delete 只隐藏 ledger 中 draft/artifact，未证明外部派生物级联删除 | 删除 Worker、外部存储回执、级联清单和删除证明齐全 |
| 强 evidence 校验 | feedback 可携带 evidence 字段，但当前未强制 attempt/model/benchmark/真实 event refs | schema/策略强制、缺失/伪造/跨 scope 拒绝测试通过 |
| 真实 Provider 生产准入 | 当前候选和 test runtime 不能证明生产供应商合规、成本和删除 SLA | Provider registry、DPIA、转委托、区域、预算和评估 Gate 全部批准 |

### Sprint 6 看板：SQL 重启持久化（P1 主线）

Sprint 6 将 SQL 重启持久化作为唯一主线之一：把 Sprint 5 已交付的 HTTP routes 与 `SqlAlchemyExperienceRunLedger` 接通，证明 Run、interaction、DRAFT checkpoint 和 deletion 状态在事务边界与进程重启后仍可安全回放。当前 WIP 由 `backend/intelligence/experience/sql_run_ledger.py`、`database/migrations/versions/0010_experience_run_interactions.py`、`tests/intelligence/experience/test_sql_run_ledger.py` 和 `governance/ADR/ADR-0047-async-sql-experience-run-ledger.md` 组成；SQLite 证据不等同于 PostgreSQL 生产证据。

| 编号 | 工作包 | 状态 | 本轮目标 | 退出条件 |
|---|---|---|---|---|
| **S6-SQL-01 / AG-02** | Async SQL ledger 与同步 HTTP bridge | `PARTIAL` | 保持 `AsyncSession` 非阻塞，提供明确的 await/事务组合根 | HTTP routes 通过显式 async bridge 使用 SQL ledger；不得用 `asyncio.run` 或伪同步阻塞 |
| **S6-SQL-02 / AG-00** | Migration/ORM/schema 对齐 | `IN_PROGRESS` | 冻结 `experience_runs` 幂等/删除字段和 `experience_run_interactions` 表 | ADR、Migration Manifest、ORM 对象清单、单 head、upgrade/downgrade/re-upgrade 证据齐全 |
| **S6-SQL-03 / AG-04** | 事务、唯一幂等和重启 replay 验收 | `IN_PROGRESS` | 补 PostgreSQL 并发、事务回滚、进程重启和删除擦除测试 | `AIFAMILY_TEST_DATABASE_URL` 下通过，且与 SQLite 结果一致 |
| **S6-SQL-04 / AG-03** | Web 真实 SQL 状态回读 | `PLANNED` | Web draft/decision/feedback/delete/replay 读取同一 durable Run | 刷新/重启后状态、sequence、DRAFT 和 deleted projection 一致 |
| **S6-SQL-05 / AG-01** | 用户故事与交付证据 | `IN_PROGRESS` | 将 S2-US4/US5 的 provenance、人工决定、反馈和真实事件引用落到 SQL ledger | 每个交互可由 event→run→scope→checkpoint→provenance/audit 回溯 |

#### Sprint 6 SQL 验收标准

**1. 显式事务与原子边界**

- `SqlAlchemyExperienceRunLedger` 只 `flush`，不私自 commit/close；事务由组合根通过 `ledger.transaction()` 或现有 Unit of Work 管理。
- create、interaction、delete 与其 audit/outbox（接入后）必须能在同一事务提交或整体回滚；异常后不能留下半条 interaction、孤立 checkpoint 或错误 deletion_state。
- 必须有事务回滚测试，并证明新的 AsyncSession 看不到已回滚 Run；禁止用线程阻塞、`asyncio.run` 或隐式自动提交掩盖边界。

**2. 数据库唯一幂等与并发**

- `tenant_id + run_id + idempotency_key` 唯一约束守住同一操作重放；`tenant_id + run_id + event_sequence` 唯一约束守住顺序。
- create 保存 `create_idempotency_key` 与 `create_fingerprint`；同 key 同 fingerprint 返回原 DRAFT，冲突 fingerprint 返回稳定 409/冲突码。
- PostgreSQL 并发 create/interaction 竞态必须只产生一条记录；唯一约束冲突可安全重试，不得静默覆盖或生成第二次模型事实。

**3. 进程重启后的 Replay**

- 在新连接/新进程中，按完整 `RunScope(tenant/family/subject_ids)` 读取同一 Run，保持 checkpoint、interaction sequence、DRAFT payload 和 artifact refs（未删除时）不变。
- Replay 只能读取 SQL ledger 投影，不调用 Model Gateway、不重算模型、不追加 interaction、不写 Family/Growth/Service/Commerce 事实。
- 跨 tenant/family/subject 的读取或重放必须 fail-closed；未知 Run 返回稳定 404/错误码，不能泄露其他作用域是否存在。

**4. 删除 Scrub 与可追溯性**

- delete 以 append-only interaction 保留最小审计线索，同时将 checkpoint 的 draft payload、artifact refs 和 run deletion_state 擦除/置 deleted。
- 删除后 replay 必须保持 `status=DRAFT` 但 `draft_payload=null`、`artifact_refs=[]`、`deletion_state=deleted`；除同一删除幂等重放外，新的 decision/feedback/human-review 返回 410/`RUN_DELETED`。
- 外部媒体、Context snapshot、embedding、缓存和供应商侧数据的级联删除证明尚未覆盖，继续标记 `PARTIAL`；不得把本地 SQL scrub 当作完整删除 SLA。

**5. 生产准入边界**

- SQL adapter 通过 SQLite 单测或本地 migration 不等于生产能力；必须有 Fresh PostgreSQL upgrade/downgrade/re-upgrade、并发唯一约束、重启 replay 和删除测试。
- 当前 HTTP routes 仍需显式 async bridge 才能注入 SQL ledger；在 bridge、真实 resolver、审计/Human Gate、删除 Worker 和 Provider 合规准入完成前，状态不得进入 `PILOT_CANDIDATE` 或 `ADMITTED`。
- 生产环境严禁 synthetic runtime；未满足 provider、DPIA、转委托、区域、成本和删除 SLA 时，API 必须继续 fail-closed。

#### Sprint 6 必须补测与交付证据

1. `uv run pytest tests/intelligence/experience/test_sql_run_ledger.py -q`（当前 SQLite WIP：5 passed）及对应 Ruff 输出。
2. 配置 `AIFAMILY_TEST_DATABASE_URL` 后执行 PostgreSQL 迁移 round-trip、并发 create/interaction、唯一约束、事务回滚、跨进程 replay 和 delete scrub；结果必须记录 migration revision、数据库版本和测试命令。
3. HTTP 集成测试证明 draft/decision/feedback/human-review/delete/replay 均使用 durable SQL ledger，而非隐式回落到 in-memory；同一 Run 在刷新/重启后 receipt 与 replay 一致。
4. 对 Gateway 注入 invocation spy，验证 replay、重复幂等和删除重试均不产生第二次模型调用；provider 失败时事务可安全回滚并允许重试。
5. 验证 `DRAFT`/`may_mutate_business_state=false` 贯穿 SQL row、HTTP response 和 replay projection；任何“accepted” interaction 都不能直接变成业务事实或成就事实。
6. 所有 migration/ORM/ADR/Manifest 文件必须已登记并可追溯；未登记的 head、未提交 WIP 或缺少真实 PostgreSQL 证据时，AG-00 必须将 Sprint 6 标为 `PARTIAL/BLOCKED`。

## 5. 通用任务卡格式

每张任务卡必须包含：

```text
任务编号 / Agent 编号 / Sprint
业务场景与用户价值
输入、活动、输出、规则、异常
契约：API / Command / Event / Projection / Gateway 对象
权限、同意、数据分类、保留和删除边界
成功、拒绝、超时、重试、暂停、人工、删除、回放测试
依赖、风险、回滚点
修改文件清单（仅限本 Agent 战场）
实际命令与输出
未完成项与下一步
```

## 6. 协作和同步要求

### 6.1 每日异步同步格式

每天由各 Agent 在项目线程提交一条不超过 10 行的同步：

```text
[AG-xx][YYYY-MM-DD]
昨日证据：完成了什么，命令/链接是什么
今日产出：准备交付什么
风险/阻塞：事实、影响、解除条件
需要 AG-00 决策：没有则写“无”
战场变更：文件路径和是否影响其他 Agent
```

不得只写“已完成”“代码已提交”；必须给出可核验路径或命令输出。

### 6.1.1 当前 Sprint 每日同步模板

各 Agent 在项目线程使用以下固定字段；缺少“证据”或“阻塞解除条件”的同步视为未完成同步：

```text
[SPRINT-1][AG-xx][YYYY-MM-DD][状态]
任务：<任务编号与一句话目标>
昨日证据：<文件/提交/命令及实际输出；没有则写“无”>
今日交付：<可审查的文件、接口、测试或决策>
依赖变化：<等待哪个 Agent，或“无”>
风险/阻塞：<事实 + 影响 + 解除条件；没有则写“无”>
体验指标：<本日涉及的理解时间/可控性/反馈/成就证据；不适用写“无”>
需要 AG-00 决策：<具体问题与建议；没有则写“无”>
战场变更：<绝对/仓库相对路径；是否影响其他 Agent>
```

AG-00 每日同步最后追加一行：

```text
集成结论：<继续 / 缩小切片 / BLOCKED / 可进入 Review>；唯一阻塞：<当前阻塞或“无”>
```

### 6.2 状态流转

```text
PLANNED → READY_FOR_DEV → IN_PROGRESS → READY_FOR_REVIEW
        → DONE_WITH_EVIDENCE → PILOT_CANDIDATE → ADMITTED
```

任何进行中状态都可以进入 `BLOCKED`。阻塞必须记录触发证据、影响范围、解除条件和负责人。`ADMITTED` 不是 Agent 自行决定的状态，必须有供应商、合规、DPIA、人工闸门和发布批准证据。

### 6.3 并发安全

- 不使用 `git add -A`、`git add .` 或 `git commit -a`；提交只带明确 pathspec。
- 不覆盖、格式化或清理其他 Agent 的未提交修改。
- 不创建第二个 Model Gateway、第二套 Experience 契约或第二个业务后端。
- 发现共享文件冲突时，停止修改并向 AG-00 报告，不通过强制覆盖解决。

## 7. Definition of Done（DoD）

任务只有同时满足以下条件，才能标记 `DONE_WITH_EVIDENCE`：

1. 用户故事、Web 流程、成功路径和拒绝/超时/重试/暂停/人工/删除路径已明确。
2. 代码只使用既有 canonical 契约；AI 调用统一经过 `backend/intelligence/model_gateway`。
3. 单元、契约、集成、架构或端到端测试按任务范围真实运行，并贴出命令和输出。
4. 修改文件范围符合 Agent 战场；相关 Ruff/类型/前端检查通过，新增错误已登记。
5. AI 输出带完整 provenance，初始状态为 `DRAFT`/`PROPOSED`，且不能自动改变 canonical Fact。
6. 媒体处理具备 purpose、consent、scope、retention、deletion_ref 和删除证明；普通日志不含原始儿童媒体。
7. Web UI 能表达 loading、partial、success、refused、timeout、retry、waiting、human review 和 deleted 等适用状态，并支持无障碍。
8. 极致体验所需的个性化节奏、即时反馈、成长叙事和难度调整有授权上下文和模型版本依据；成就只能绑定真实 `ExperienceEvent`/`ActionOutcome`，可回放。
9. 不产生家庭总分、家庭排名、虚构积分、儿童商业画像、临床诊断或疗效承诺。
10. sandbox/test/production 的路由、状态机、错误语义、权限和人工闸门一致；外部适配器差异已登记。
11. 交付说明列出未完成项、已知风险、回滚方式和下一步；“文档存在”或“页面能打开”不得单独作为完成证据。

## 8. 质量红线与升级机制

以下任一情况出现，AG-04 可直接将任务置为 `BLOCKED`，AG-00 必须在下一个同步窗口裁决：

- 未经准入的 Provider 被用于真实家庭/未成年人数据；
- 领域代码直接调用供应商，或 AI Runtime 导入业务 Repository；
- AI 结果直接写成 Family/Growth/Service/Commerce 事实；
- 成就由模型自由编造，或出现家庭总分、排名、虚构积分；
- 媒体无同意、跨租户、无法删除或删除证明缺失；
- 测试、拒绝路径或回滚证据缺失却要求标记完成；
- 竞品或市场结论没有来源，被当作产品事实使用。

AG-00 的裁决必须包含：事实证据、受影响任务、选择（修复/缩小/暂停/回滚）、责任人和下一次复核时间。任何 Agent 不得以进度压力自行越过红线。

## 9. 本章程的维护

本文件是本子项目的执行章程，属于 `NOT_CANONICAL` 交付文档。若要改变系统边界、AI 权限、数据治理、供应商准入或宪章约束，必须先由 AG-00 提交对应 ADR/治理变更，不得在本文件中悄然放宽。
