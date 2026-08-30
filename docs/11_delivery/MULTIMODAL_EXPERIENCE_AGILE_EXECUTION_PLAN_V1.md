---
id: DLV-AI-MULTIMODAL-EXECUTION-001
title: AiFamily 多模态 AI 体验子项目敏捷实施计划
type: delivery-specification
status: draft
version: 1.0
owner: project-manager
created: 2026-08-30
updated: 2026-08-30
canonical: false
evidence_class: NOT_CANONICAL
---

# AiFamily 多模态 AI 体验子项目敏捷实施计划 V1

> 本文是项目经理用于拆解、派工、验收和复盘的执行计划，不是系统当前真相、架构决策或能力完成声明。
> 本子项目只交付 Web UI；移动端不在本计划范围内。所有外部模型调用必须经
> `backend/intelligence/model_gateway`，成熟多模态 LLM 先以隔离适配器接入，供应商准入和合规未完成时保持 fail-closed。

## 1. 项目任务书

### 1.1 目标

在一个可回放、可暂停、可人工接管且具有极致体验的 Web 产品中，完成以下最小闭环：

```text
家长输入文字 + 受控图片
  → 同意/权限/媒体登记
  → Model Gateway 生成结构化理解草稿
  → Web 展示证据、限制和候选下一步
  → AI 生成个性化节奏、即时反馈、成长叙事和适配难度
  → 家长接受、改写、跳过、暂停或请求人工
  → Feedback / RecommendationDecision / Trace / Replay
```

成功标准不是“模型说得像人”，而是用户能看懂系统在做什么、能控制下一步、失败后能回来，且每个输出都有可解释来源。游戏感来自 AI 对当前家庭上下文生成的个性化节奏、即时反馈、成长叙事和难度调整，而不是预设积分、排行榜或刺激性机制。成就只能由真实的体验/行动事件触发，并带有证据引用。

### 1.2 范围与非目标

**本期范围**

- Web Experience Studio：文本和图片输入、状态反馈、草稿查看、反馈和回放。
- Model Gateway：结构化请求、图片媒体引用、供应商准入、重试、超时、schema 校验和 provenance。
- Experience Run：异步状态、attempt 账本、事件时间线、人工闸门和幂等恢复。
- 质量与治理：gold set、拒绝矩阵、删除证明、成本/延迟/质量指标和发布 Gate。

**明确不做**

- 不做 Mobile UI、原生 App 或移动端适配。
- 不在本期生产启用未经合规批准的供应商；候选模型只能用于隔离评测。
- 不把 AI 草稿写成 Family/Growth/Service/Commerce 的 canonical Fact。
- 不实现音频、视频、短剧和商品生产链路；本期只为后续模态保留契约和异步边界。
- 不做家庭总分、家庭排名、儿童商业画像、临床诊断或疗效承诺。

### 1.3 已知基线（用于计划，不等于完成）

| 能力 | 当前证据 | 本计划处理 |
|---|---|---|
| Model Gateway | 有 `StructuredRequest`、`ModelDraft`、provider admission 和图片 `MediaInput` 适配器 | 以 Gateway 作为唯一模型入口，补齐真实调用方、运行状态和 Web 接线 |
| Experience 契约 | `backend/intelligence/experience/` 已有契约、curation、multimodal 相关原语 | 先确认公共边界，再做纵向切片，不复制第二套契约 |
| 供应商 | 当前无可直接宣称生产可用的获准外部 provider | 先 FakeProvider/隔离评测，准入由合规 Gate 决定 |
| 持久化与回放 | Attempt/部分事件能力仍有内存或实验状态 | Sprint 2 才允许声称 durable；之前只能标 Pilot |
| 评估 | 多模态评测原语正在形成，gold set 和发布阈值尚未完成 | Sprint 0 建基准集，Sprint 3 才形成发布闸门 |

## 2. 交付原则与工作协议

### 2.1 敏捷原则

1. **纵向交付**：每个 Sprint 必须包含 Web UI、应用服务、Gateway、测试和拒绝路径；不以“只完成某一层”作为完成。
2. **小批量可回滚**：每个 Sprint 只合并一个可演示切片；功能开关默认关闭，失败可回到人工或稍后重试。
3. **证据先于状态**：没有测试命令、输出、trace、拒绝和回放证据，状态只能是 `PLANNED`、`IN_PROGRESS` 或 `BLOCKED`。
4. **AI 主路径但权限收敛**：AI 负责理解和生成候选，业务事实仍由领域 Named Action、授权和人工闸门确认。
5. **Web-first，多模态渐进**：先跑通文字+图片，再按供应商能力、权利、删除和评测结果扩展音频/视频。
6. **真实失败可见**：超时、未准入、schema 错误、无同意、过期媒体、跨租户读取都要有稳定错误语义，不能伪装成成功。

### 2.2 运行节奏

- 采用一周一个 Sprint；每个 Sprint 设一个目标、一个可演示切片和一个退出 Gate。
- 每日异步站会只回答：昨天证据、今天产出、当前阻塞、需要 PM 决策。
- Sprint Review 必须现场演示成功、拒绝、超时、重试、暂停、人工升级、删除和 replay 中适用的路径。
- Sprint Retro 只产生可执行改进项，必须有 owner、截止 Sprint 和验证证据。
- PM 负责拆片、优先级、依赖协调和验收；实现 Agent 负责代码和测试；PM 不替 Agent 修改实现来“绿测试”。

## 3. Epic 与用户故事

### E1：受治理的多模态入口

**价值**：让家庭可以安全地提交文字和图片，并知道媒体如何被使用。

| 故事 | 验收要点 | 优先级 |
|---|---|---:|
| E1-US1 作为家长，我能在 Web 输入场景文字并上传一张图片 | purpose、subject、locale、consent、sha256 和 deletion ref 完整；缺任一项可解释拒绝 | P0 |
| E1-US2 作为家长，我能看见上传、解析、等待和失败状态 | UI 状态不把 OCR/视觉推断当作原话；失败提供重试、跳过或人工入口 | P0 |
| E1-US3 作为合规负责人，我能撤回并删除媒体 | 源媒体、派生 OCR/缓存/embedding（若存在）按主体级联删除，并返回可审计证明 | P0 |

### E2：Model Gateway 结构化生成

**价值**：让成熟多模态 LLM 可替换、可评估、可审计地服务体验主路径。

| 故事 | 验收要点 | 优先级 |
|---|---|---:|
| E2-US1 作为 AI Runtime，我只通过 Gateway 发送请求 | 业务代码无供应商 SDK；请求含 prompt/schema/data class/context snapshot/policy context | P0 |
| E2-US2 作为产品经理，我能得到可渲染的体验草稿 | 输出通过 JSON Schema；含 situation summary、observable signals、candidate next steps、risk flags、needs human gate | P0 |
| E2-US3 作为审计员，我能解释一次生成 | provenance 完整记录 provider/model/version、prompt/schema、context ref、media hash、latency、token/cost（可得时） | P0 |
| E2-US4 作为平台管理员，我能阻断未准入模型 | provider admission、区域、未成年人数据、转委托和删除要求不满足即 fail-closed | P0 |

### E3：可恢复的 Experience Run

**价值**：长任务不是一次同步请求；用户可以等待、暂停、恢复或升级人工。

| 故事 | 验收要点 | 优先级 |
|---|---|---:|
| E3-US1 作为用户，我能看到运行状态 | `QUEUED/RUNNING/WAITING/SUCCEEDED/FAILED/CANCELLED` 在 Web 可观察，刷新后状态一致 | P0 |
| E3-US2 作为用户，我能暂停并恢复 | `WAITING` 必须有 reason 和 event id；恢复重新校验 scope、consent、媒体有效期和幂等键 | P1 |
| E3-US3 作为 SRE，我能重放一次运行 | replay 使用受控媒体引用和固定版本，不复制原始媒体到日志；重复事件无副作用 | P1 |

### E4：建议确认与学习闭环

**价值**：AI 只提出候选，家庭做选择，反馈用于后续评测而不是直接改事实。

| 故事 | 验收要点 | 优先级 |
|---|---|---:|
| E4-US1 作为家长，我能接受、改写、跳过建议或请求人工 | 生成 `RecommendationDecision(PROPOSED)`；未确认不写 canonical Fact | P0 |
| E4-US1a 作为家庭成员，我能获得适合当下状态的游戏化体验 | AI 基于授权上下文生成个性化节奏、即时反馈、成长叙事和下一步难度；输出标注依据、限制和可调整项，不生成虚构事实 | P1 |
| E4-US1b 作为家庭成员，我能看到真实行动带来的成就 | 成就仅由已记录的 `ExperienceEvent`/`ActionOutcome` 等真实事件触发，引用事件证据；不得凭模型叙事编造积分、家庭总分、等级或排名 | P0 |
| E4-US2 作为人工顾问，我能处理高影响请求 | approve/reject/request-more-evidence、理由、操作者、超时和审计记录齐全 | P1 |
| E4-US3 作为评测员，我能按反馈复跑 gold set | 反馈与 request/attempt/recommendation 绑定；可按模态、语言和安全标签切片 | P1 |

### E5：质量、成本和发布控制

**价值**：只有可测、可追溯、可回滚的模型版本才能晋级。

| 故事 | 验收要点 | 优先级 |
|---|---|---:|
| E5-US1 作为 QA，我有匿名 gold set 和拒绝集 | 每例有输入引用、期望结构、安全标签和评审记录；不得挂真实生产家庭数据 | P0 |
| E5-US2 作为发布负责人，我能比较模型版本 | schema 通过率、安全拒绝命中、证据完整率、延迟、成本均有报告 | P1 |
| E5-US3 作为预算负责人，我能限制成本 | 预算、重试上限、并发和超时可配置；超限不自动切换未审 provider | P1 |

## 4. Sprint 计划

### Sprint 0：项目对齐与可测性基座（5 个工作日）

**目标**：冻结边界、证据分层和契约，确保后续 Agent 不各自发明路径。

**任务切片**

- S0-1：确认 Web Experience Studio 的用户流程、状态字典、错误码和最小输出 schema。
- S0-2：登记 text/image/audio/video 的媒体契约、provenance、deletion_ref 和生命周期；本期只启用 text/image。
- S0-3：建立 provider admission 清单和合规阻塞模板；未准入 provider 不得进入家庭数据路径。
- S0-4：创建匿名/合成 gold set、拒绝集和固定评测报告格式。
- S0-5：定义 trace 字段、attempt ledger、幂等键、保留期限和日志脱敏规则。

**退出验收**

- 产品、AI Runtime、合规、QA 对 scope、schema、错误码和 Gate 签字。
- 至少一条无同意、跨租户、过期媒体、未准入 provider 的可重复拒绝测试。
- gold set 可版本化、可重跑；不包含真实儿童媒体。
- 通过相关架构测试和 lint；未通过项登记为阻塞，不用文档状态掩盖。

### Sprint 1：文字+图片 → 结构化草稿 Web 纵向切片（5 个工作日）

**目标**：用户在 Web 完成一次真实的“输入—生成—查看草稿”流程。

**任务切片**

- S1-1：Web 输入组件和上传安全边界，生成受控 media ref。
- S1-2：体验应用服务组装 `StructuredRequest`，统一调用 Model Gateway。
- S1-3：接入 FakeProvider 和隔离候选 provider；支持图片输入，输出固定 schema。
- S1-4：展示 DRAFT、provenance、风险提示和“需要人工确认”状态。
- S1-5：补充成功、schema 错误、超时、无 provider、非法媒体和 scope 越权测试。

**退出验收**

- Web sandbox 能完成一次文字+图片生成，且模型输出只表现为 `ModelDraft(DRAFT)`。
- provider 不可用时明确显示可恢复错误，不展示确定性假文案冒充 AI。
- request/attempt/provenance 可查询；原始媒体不进入普通日志。
- 相关单元、契约、集成测试和 lint 均有实际命令输出。

### Sprint 2：确认、反馈、暂停与回放（5 个工作日）

**目标**：把草稿变成可控的家庭选择闭环，形成耐故障的 Experience Run。

**任务切片**

- S2-1：将草稿映射为 `RecommendationDecision(PROPOSED)`，实现接受/改写/跳过/请求人工。
- S2-2：实现 Human Gate；高影响动作只允许显式批准，记录 actor、reason、policy 和 audit。
- S2-3：持久化 Run 状态、attempt、事件时间线和 checkpoint；刷新/进程重启后可恢复。
- S2-4：实现 feedback、pause/resume、replay；事件和 webhook（如启用）保持幂等。
- S2-5：实现媒体撤回、派生物删除和回放权限检查。
- S2-6：基于授权上下文生成个性化节奏、即时反馈、成长叙事和难度调整；将成就投影绑定真实行动事件，不使用虚构积分、家庭总分或排名。

**退出验收**

- 成功、拒绝、暂停、人工升级、超时、重试、删除、重放各至少有一条可重复测试。
- 同一幂等键重复提交不产生双重建议、双重审计或双重副作用。
- AI Runtime 不导入任何领域 repository；领域事实只通过 Named Action 转换。
- 进程重启后 Run 状态和 provenance 可回读；删除后 UI 不再展示派生内容。
- 个性化节奏、即时反馈、成长叙事和难度调整均能回溯到授权上下文与模型 provenance；成就只能由真实 `ExperienceEvent`/`ActionOutcome` 触发并可回放。

### Sprint 3：评估、发布 Gate 与多模态扩展准备（5 个工作日）

**目标**：让首个 Web 切片具备 Pilot 晋级依据，并为音频/视频预研留出稳定边界。

**任务切片**

- S3-1：运行 gold set 回归，产出按模态/语言/安全标签的质量报告。
- S3-2：接入 schema、安全拒绝、证据完整率、延迟、token/cost 和失败率指标。
- S3-3：定义 provider/model/prompt/schema 的版本晋级、回滚和预算阈值。
- S3-4：补齐 sandbox/staging parity 检查；外部适配器是唯一允许的环境差异。
- S3-5：为 audio/video 建立契约、异步 Job、权利和删除检查清单，但不打开生产路由。

**退出验收**

- 评测报告可由另一名 Agent 用同一命令复跑，结果和版本绑定。
- 未达到阈值的模型版本不能进入 Pilot；降级策略和人工处置人明确。
- 供应商合规资料、DPIA、转委托、区域和删除 SLA 未齐全时，生产路由保持关闭。
- Web 体验切片在 sandbox/staging 使用相同状态机、错误语义、权限和闸门。

## 5. 验收标准矩阵

| 类别 | 必须证明 | 失败处理 |
|---|---|---|
| 功能 | 输入、生成、查看、选择、暂停、反馈、人工、删除和回放路径 | 回退到人工或稍后重试；不伪装成功 |
| AI 约束 | Gateway 唯一入口；`may_mutate_business_state=false`；草稿为 DRAFT/PROPOSED | 架构测试失败即阻断合并 |
| 数据与合规 | consent、purpose、scope、subject、retention、deletion_ref、audit 可追溯 | fail-closed，禁止发送或展示 |
| 安全 | 跨租户、越权媒体、未准入模型、儿童商业营销、诊断承诺均拒绝 | 记录拒绝原因，不泄露敏感媒体 |
| 可靠性 | 超时、限流、重试、重复事件、进程重启、checkpoint 和回放 | 进入人工/重试队列；保留原始 trace |
| 质量 | schema、证据、拒绝集、延迟、成本和人工评分可复现 | 不达阈值不晋级，不能用点击率替代教育效果 |
| 体验 | Web 状态清晰、可访问、无障碍；AI 能按授权上下文生成个性化节奏、即时反馈、成长叙事和难度调整；事实/草稿/建议/成就边界清楚 | 退回设计与文案评审；禁止用虚构积分、家庭总分或排名补偿 |

## 6. 依赖、风险与决策门

### 6.1 依赖

- Model Gateway 公共契约、provider registry、FakeProvider 和测试夹具。
- Web 应用入口、身份/授权、Consent、Audit、Idempotency、持久化和事件基础设施。
- Experience 契约、Recommendation/Feedback/Run 状态模型；不能再造平行业务实体。
- 合规、法务和安全对供应商处理区域、转委托、留存、删除及 DPIA 的书面结论。
- QA 的匿名 gold set、故障注入和环境 parity runner。

### 6.2 风险登记

| 风险 | 触发信号 | 预防/处置 | Owner |
|---|---|---|---|
| Provider 未获准却被接入 | registry 缺 admission 或 DPIA | Gateway fail-closed；仅 FakeProvider 继续开发 | CMP/AIR |
| Agent 各自造接口 | 出现第二个 provider client 或重复 schema | PM 评审拦截；统一走 Gateway/Experience contract | PM |
| AI 输出被当成事实 | 直接写 Family/Growth 表或状态 | 架构测试 + Named Action + Human Gate；立即回滚 | DOM/AIR |
| 长任务不可恢复 | 刷新丢状态、重复 webhook | 持久化 Run、checkpoint、幂等和 replay 测试 | PLT/AIR |
| 媒体泄露或删除不完整 | 日志有原始 bytes、删除无 proof | hash/ref only、派生物清单、主体级删除测试 | CMP/PLT |
| 质量只看演示效果 | 没有 gold set 或拒绝集 | S0 退出门阻断 S1；固定报告和人工抽检 | QA |
| 并发改坏共享文件 | 不明来源 diff、registry 冲突 | Agent 战场隔离、pathspec 提交、PM 集成窗口 | PM |

### 6.3 必须上呈的决策

- 是否批准任何真实供应商处理家庭/未成年人数据。
- 是否扩大到音频/视频、浏览器操作、外部连接器或生成商品。
- 是否改变 Web-only 边界、AI 输出权限、人工闸门或数据保留策略。
- 是否接受评测阈值、成本预算、延迟目标和降级体验。

PM 可自行决定 Sprint 顺序、任务拆分、FakeProvider、测试数据和既有 ADR 范围内的实现选择；以上决策不得由 Agent 默认为已批准。

## 7. Definition of Done（DoD）

任何用户故事只有同时满足以下条件，才能标记 `DONE_WITH_EVIDENCE`：

1. 有用户故事、Web 流程、成功路径和拒绝/超时/重试/暂停/人工/删除路径。
2. 绑定唯一的契约、Command/Event/Projection 或 Gateway 对象；没有平行实现。
3. 代码测试通过：单元、契约、集成、架构；必要时有持久化、重启和故障注入证据。
4. `uv run ruff check <changed files>` 干净；结构变更按仓库规则运行架构测试。
5. 所有 AI 输出含完整 provenance，初始状态为 DRAFT/PROPOSED，且不能自动改变 canonical Fact。
6. 媒体与派生物有 consent、purpose、scope、retention、deletion_ref 和删除证明；日志无原始儿童媒体。
7. Web UI 能展示 loading、partial、success、refused、timeout、retry、waiting、human review、deleted 等适用状态；AI 生成的个性化节奏、即时反馈、成长叙事和难度调整有上下文引用、可解释限制和人工/用户调整入口。
8. 成就只由真实 `ExperienceEvent`/`ActionOutcome` 等事件生成，证据可回放；系统不创建虚构积分、家庭总分、家庭排名、等级或以此驱动商业营销。
9. sandbox/staging/production 的路由、schema、状态机、错误语义、权限和人工闸门一致；差异有登记。
10. 变更说明包含实际测试命令和输出、未完成项、风险、回滚方式及下一步；不能只写“已完成”。

## 8. Agent 协作规则

### 8.1 角色与战场

| 角色 | 责任 | 只修改的范围 |
|---|---|---|
| PM/Lead | 目标、拆片、优先级、集成和最终验收 | `docs/11_delivery/`、集成记录 |
| AIR | Gateway、Experience Run、Provider、Prompt/Schema、评测 | `backend/intelligence/`、对应测试 |
| WEB | Web UI、状态呈现、无障碍、API 对接 | Web 前端目录、对应测试 |
| PLT/CMP | Identity、Consent、Audit、Idempotency、Deletion、Human Gate | `backend/platform/`、治理检查和测试 |
| DOM/API | Named Action、API 契约和领域投影 | 对应 `backend/domains/`、`backend/apps/`、契约测试 |
| QA/EVAL | gold set、故障注入、parity、回归报告 | `tests/`、`reports/` |

### 8.2 派工和交付格式

每张 Agent 任务卡必须写明：用户故事、只读基线、允许修改的文件范围、依赖、验收命令、拒绝路径和回滚方式。

Agent 回报必须包含：

- 修改文件的绝对路径和摘要；
- 实际执行的测试/lint 命令及关键输出；
- 仍存在的失败、阻塞和未验证假设；
- 是否需要 PM 决策；
- 不得把“代码已存在”写成“能力已生产可用”。

### 8.3 并发安全

- 开工先检查 `git status`，只改自己战场；其他 Agent 的 WIP 不格式化、不顺手修复。
- 禁止 `git add -A`、`git add .`、`git commit -a`；提交只能带明确 pathspec。
- 共享契约、治理 YAML、迁移清单和前端路由需先向 PM 登记，采用集成窗口合并。
- 发现架构、合规或权限问题时停止扩展并报告，不通过临时旁路绕过 Gate。
- PM 负责合并前验证；任何 Agent 不得以“另一个 Agent 应该会修”作为 DoD 证据。

## 9. PM 看板状态与晋级规则

```text
PLANNED → READY_FOR_DEV → IN_PROGRESS → READY_FOR_REVIEW
        → DONE_WITH_EVIDENCE → PILOT_CANDIDATE → ADMITTED
```

- `BLOCKED` 可从任意进行中状态进入；必须写清阻塞证据和解除条件。
- `DONE_WITH_EVIDENCE` 只表示代码和测试在当前环境满足 DoD，不表示生产准入。
- `PILOT_CANDIDATE` 需要 Sprint 3 评测报告；`ADMITTED` 需要供应商、合规、DPIA、人工闸门和发布批准。
- 任何发现供应商、数据、权限或 AI 输出越权，立即降级为 `BLOCKED`，保留 trace 和回滚点。

## 10. 本计划的下一步

1. PM 将 E1/E2/E3/E4/E5 故事登记到项目看板，并给每张卡分配唯一 owner。
2. 先执行 Sprint 0，未通过退出 Gate 前不扩展真实家庭媒体和新模态。
3. Sprint 1 只验收 Web 文字+图片纵向切片；FakeProvider 是默认测试路径。
4. 每个 Sprint Review 后更新本计划的实际状态、证据链接和未完成项；不要直接把本文件改成 canonical。

**NOT_CANONICAL / DRAFT / 执行计划**
