---
id: SYS-AI-MAP-001
title: AiFamily Current AI Capability Map
type: system
status: current
version: 2.0
owner: chief-architect
created: 2026-08-29
updated: 2026-08-29
canonical: true
supersedes: docs/00_foundation/CURRENT_AI_ARCHITECTURE.md
superseded_by: null
---

# 当前 AI 能力版图 (Current AI Map)

> 本文件回答一个问题：**AiFamily 有哪些 AI 能力，各自真实成熟到什么程度。**
> 它是版图 + 成熟度矩阵。详细设计规格在 `docs/05_ai/AI_ARCHITECTURE.md`，本文件不重复。

---

## 0. 一句话结论（读本文件前先看这里）

```text
backend/intelligence/ 下当前只有一个目录: design_copilot
design_copilot 的每个方法都是 NotImplementedError
零调用方 · 零测试

∴ AiFamily 当前 AI 能力的真实成熟度: 几乎全部 ABSENT 或 PLANNED
   没有任何一项 AI 能力达到 PILOT 或 PRODUCTION
```

**源仓库 TS 侧有真实实现（`packages/ai-gateway/src/index.ts`，894 行）不等于 AiFamily 有。** 按 `governance/REPOSITORY_CONSTITUTION.md` R1（唯一后端真相 = Python），TS 实现只能作为**参考实现**（reference implementation），不是 AiFamily 的能力。

**"研究过 / 设计过"不等于"已实现"。** 本文件下方所有 `PLANNED` 条目都有完整的设计文档，这恰恰是最容易被误读为"已有"的情形 —— `SYSTEM_MANIFEST.md` §6（Current Truth ≠ Specification ≠ Evidence）就是为防这个而存在。

---

## 1. 成熟度词表

| 成熟度 | 定义 | 判据 |
|---|---|---|
| `PRODUCTION` | 已上线，服务真实家庭 | 有生产运行记录 |
| `PILOT` | 有可运行实现 + 测试，在受控环境验证中 | 代码可跑 + 测试通过 + 有验证证据 |
| `EXPERIMENT` | 有可运行代码，未验证、未接线 | 代码能执行但无验收测试或无调用方 |
| `PLANNED` | 有设计与登记，无可运行代码 | governance 有条目 |
| `ABSENT` | 无设计、无登记、无代码 | 什么都没有 |

`NotImplementedError` 占位**不算 `EXPERIMENT`** —— 它不能执行，等价于 `PLANNED` 加一个目录名。这一区分直接来自 R4（代码行数不是成熟度）与 `MIGRATION_MANIFEST.yaml` 中 `design_copilot` 的 override 原文："迁移不得被解读为该能力已存在"。

---

## 2. Family Principal（AI 主体的五类能力）

Family Principal 是平台 AI 主体的统称。其五类能力当前状态：

| 能力 | 说明 | AiFamily 成熟度 | 源仓库参考实现 |
|---|---|---|---|
| **Understanding**（理解） | 从测评证据、对话、家庭历史中理解家庭处境 | `ABSENT` | `apps/api/src/modules/principal`（2337 行，真实 Postgres `principal_*` 表，DI 工厂 fail-closed 最严格）；UI-03 的 Hypothesis 生成链 |
| **Planning**（规划） | 生成 21/90 天成长计划草案 | `ABSENT` | 源仓库 UI-04/05 仅有 LLM draft，无报告事实 DTO，本身也未完成 |
| **Recommendation**（推荐） | 推荐行动、服务、教师 | `ABSENT` | 无（源仓库无真实推荐实现；`detect_scenario_keyword` 已被源仓库自己判定为"keyword-matching masquerading as understanding，verdict DEPRECATE"） |
| **Coordination**（协调） | 协调家庭、教师、机构多方（FGCN 一案一管家） | `ABSENT` | `apps/api/src/modules/orchestration`（5519 行，明确设计为不写 Growth 权威表） |
| **Reflection**（复盘） | 阶段复盘、越用越准的学习闭环 | `ABSENT` | 无。这是 `AI_NATIVE_PRINCIPLES.md` 判据 4（是否越用越准）的载体，源仓库无对应代码落地 |

**五项全部 `ABSENT`。** `principal_core` 在 `MIGRATION_MANIFEST.yaml` 中 disposition = MIGRATE、status = PLANNED，排期 Batch 5，且明确要求 `AttemptRecordingGateway` 等 fail-closed 机制必须**先于**业务逻辑迁移。

R9 硬约束（对全部五项适用）：Principal 的任何输出都只能是 `Perspective` / `Recommendation`，永不得直接写入家庭权威事实。源仓库 `principal` 模块自身已遵守此约束（明确不写 Growth 权威状态），这一正确决定必须在 Python 侧保留。

---

## 3. AI Runtime 组件（R10：各一份）

R10 要求所有 AI 能力收敛于 `backend/intelligence/`，且 Model Gateway / Context Engine / Agent Runtime / Tool Runtime / Prompt Registry / Safety / Human Gate / Evaluation / Trace / Cost / Audit **各一份**。

| # | 组件 | 目标位置 | AiFamily 成熟度 | 说明 |
|---|---|---|---|---|
| 1 | **Model Gateway** | `backend/intelligence/model_gateway` | `EXPERIMENT` | **2026-08-29 落地（T-06）**，由 `ABSENT`/`PLANNED` 升为 `EXPERIMENT`。真实可运行代码 + 110 项测试通过：Provider 准入（含第16条合规字段与 `sub_delegates` 三态）、双层 Timeout、外呼前 Attempt 登记、JSON+schema 校验、强制完整 `AiProvenance`、输出恒为 `ModelDraft`（`may_mutate_business_state` 只读恒 False）、受控 Routing。两个 adapter：`OpenAICompatibleProvider`（真实 httpx 路径，`MockTransport` 全程测试）与 `FakeProvider`。是 R7 规定的**唯一凭据读取点**，且该收敛由 `tests/architecture/test_ai_runtime_isolation.py` 机械强制。**不是 `PILOT`**：无任何调用方，且**零个外部供应商通过准入**（详见 §3.3）。参考实现：`packages/ai-gateway/src/index.ts`（894 行）、`packages/principal-ai/src/index.ts` |
| 2 | **Context Engine** | `backend/intelligence/context_engine` | `ABSENT` | 无 manifest 条目、无设计细目、无代码。Family Context 的载体，见 §5.1 |
| 3 | **Agent Runtime** | `backend/intelligence/agent_runtime` | `PLANNED` | 设计要求见 `AI_NATIVE_PRINCIPLES.md` §3.2（列为"核心域能工作的前提"，不是"未来可能加"）。无 manifest 条目、无代码 |
| 4 | **Tool Runtime** | `backend/intelligence/tool_runtime` | `PLANNED` | 同上。工具注册是判据 5（AI 权限边界显式建模）的载体 |
| 5 | **Memory** | `backend/intelligence/memory` | `ABSENT` | 源仓库 `FamilyMemoryDialogueRuntime` **未接入任何调用方**；embedding / pgvector **完全不存在于代码**。AiFamily 内无代码 |
| 6 | **Prompt Registry** | `backend/intelligence/prompt_registry` | `PLANNED` | `AI_NATIVE_PRINCIPLES.md` §3.2 列为前提。R6 要求 provenance 可追溯到 `prompt_version`，无 registry 则无法满足 |
| 7 | **Schema Registry** | `backend/intelligence/schema_registry` | `PLANNED` | 同上（结构化输出约束） |
| 8 | **Safety** | `backend/intelligence/safety` | `PLANNED` | 安全筛查须具备"批量可见性"（`MIGRATION_PLAN_V2.md` §0 保真要求）。R9 的 `legacy_alert.risk_score` → SAFETY_SIGNAL_SOURCE：**非阈值、非自动动作，高风险须过 Human Gate** |
| 9 | **Human Gate** | `backend/intelligence/human_gate` | `PLANNED` | R8 规定必须过闸的行为：类诊断输出、家庭计划变更、教师推荐、服务购买、对外沟通、会员升级、涉未成年人的敏感动作。闸门决策必须落库可审计。Python 侧零实现；源仓库 Human Gate 逻辑分散于 TS 侧多处接入模式 |
| 10 | **Evaluation** | `backend/intelligence/evaluation` | `ABSENT` | `AI_NATIVE_PRINCIPLES.md` §5 明确：判据 4（越用越准）的验证需要真实 eval 框架与回归测试，**不是靠声明**。当前无任何 eval 代码 |
| 11 | **Observability**（Trace / Cost） | `backend/intelligence/observability` | `ABSENT` | OpenTelemetry **尚未加入 `pyproject.toml`**（见 `CURRENT_SYSTEM_BASELINE.md` §4.6）。无 trace、无成本核算 |
| 12 | **AI Provenance** | 跨组件（`backend/packages/contracts` + model_gateway） | `EXPERIMENT` | 2026-08-29 由"仅类型层"升级：记录机制已存在。`model_gateway/contracts.py` 的 `AiProvenance` 强制 model / model_version / prompt_version / schema_version / context_snapshot_ref / confidence / latency_ms / provider_id / data_class，身份字段缺一即构造失败（依据 PIPL 第24条，见 `COMPLIANCE_HARD_CONSTRAINTS.md` §2）。`backend/packages/contracts` 的 `Provenance` / `evidence` 类型仍是被 4 个域引用的证据等级原语，两者**不重复**：前者记录"这条 AI 输出是怎么产生的"，后者标注"这条数据的证据等级"。仍缺的是**人工审批记录链条**（Human Gate 未落地）与持久化（attempt 账本仅进程内） |

**汇总**：12 项中 `PLANNED` 5 项、`ABSENT` 4 项、`EXPERIMENT` 3 项（Model Gateway / AI Provenance / design_copilot 计入方式见下）。**`PILOT` 与 `PRODUCTION` 仍为 0。**

### 3.3 Model Gateway 落地后仍然为真的话（不得被"已落地"掩盖）

1. **零个外部供应商可调用。** 真实 adapter 的登记条目 `openai-compatible-unassessed` 刻意设为 `status=TECHNICALLY_VALIDATED` + `sub_delegates=未确立`，因此 `admit()` 对它的任何数据类别都返回 `POLICY_REJECTED`——并有测试断言这一点。放行的前提是法务确立厂商分包结构（《儿童个人信息网络保护规定》第16条**不得转委托**，见 `COMPLIANCE_HARD_CONSTRAINTS.md` §7 与 §11.1 待办第1项）。**这不是工程可以自行判断的事**，也不是配置项。
2. **无调用方。** 没有任何业务域或 HTTP 路由使用本网关。按 R4，这是"能力存在且有测试"，不是"已投入使用"——不得据此声称任何 AI 业务能力可用。
3. **Attempt 账本非持久化。** 仅 `InMemoryAttemptSink`（进程内）。持久化归 `platform/audit` 的读取留痕扩展（T-07）；网关只依赖 `AttemptSink` 协议，不得反向 import 业务域仓储。
4. **仍无 Prompt Registry / Context Engine。** 故 `prompt_version` 与 `context_snapshot_ref` 由调用方自行提供，网关只强制非空，**不校验它们指向真实存在的 prompt 或上下文快照**。§3 表格第 6 项与第 2 项仍分别为 `PLANNED` / `ABSENT`。
5. **§3.2 列出的两项"待补检查"已补。** `AI_NATIVE_PRINCIPLES.md` §5 的两项（`backend/intelligence/` 不得 import 业务域 repository；不得把 AI 产出置为 VALIDATED/APPROVED）现由 `tests/architecture/test_ai_runtime_isolation.py` 执行，四个检查器均以植入违规的方式验证过会咬人。§5 第三项（判据4"越用越准"需真实 eval 框架）**仍未补**——Evaluation 仍是 `ABSENT`。

### 3.1 R10 的伤疤（Python 侧必须避免重演）

源仓库只有一份网关**实现**，但有三套互不相同的**接入模式**：

| 接入点 | 模式 | 严格程度 |
|---|---|---|
| `principal.module.ts:19-34` | DI 工厂 + fail-closed + AttemptRecording | 最严 |
| `family/family-model-gateway.provider.ts:17-22` | DI + 双 env 门控 | 中 |
| `orchestration/llm-gateway/family-llm-gateway.service.ts:58-63` | **裸 `new OpenAICompatibleAiGateway`** | 违规 |

**重复的不是实现，是纪律。** Python 侧落地 Model Gateway 时必须只允许一种接入模式。第三种是 R7 的直接伤疤：源仓库自己在 `packages/ai-gateway/src/index.ts:544-560` 声明了 `AI_GATEWAY_POLICY = { business_module_direct_provider_call: 'forbidden' }`，然后在业务服务方法内部违反了它 —— **策略写成了常量，但没有任何东西执行它**，这是 R14 存在的原因。

该违规文件在 manifest 中登记为 `orchestration_llm_gateway_violation`，status = BLOCKED，blocking_action：**REIMPLEMENT 时必须走 R7 的 Model Gateway，不得重复此违规**。

### 3.2 已有的机械护栏

`tests/architecture/test_no_direct_provider_calls.py` 与 `test_compliance_constraints.py::test_no_direct_provider_sdk_outside_model_gateway`（R7）已存在并通过。2026-08-29 之前它们**没有真实拦截对象**（无任何 AI 调用代码），属"预置护栏"；Model Gateway 落地后，`backend/intelligence/model_gateway` 成为它们唯一放行的路径，护栏开始有实际约束对象。

`AI_NATIVE_PRINCIPLES.md` §5 列出的两项待补检查**已于 2026-08-29 补齐**，落在 `tests/architecture/test_ai_runtime_isolation.py`：

| 检查 | 实现 | 验证会咬人 |
|---|---|---|
| `backend/intelligence/` 不得 import 业务域 repository | `test_ai_runtime_does_not_import_business_domains`（禁 `backend.domains.*` 与 `backend.platform.persistence`；后者刻意纳入——拿到 UnitOfWork 就等于拿到写 canonical 的能力） | 已植入违规验证失败 |
| 不得把 AI 产出置为 VALIDATED/APPROVED | `test_ai_runtime_does_not_promote_its_own_output`（查**赋值**而非提及：把这些状态写进拒绝清单是护栏，不是提升） | 已植入违规验证失败 |
| `may_mutate_business_state = false` 是运行时事实 | `test_model_gateway_output_type_cannot_mutate_business_state`（真实 import 并断言，且断言它**不是** dataclass 字段——带 False 默认值的字段今天能过检查、明天能在构造时被传 True） | 已把 property 改回字段验证失败 |
| 凭据只由 Model Gateway 读取（R7 原文） | `test_credentials_are_read_only_inside_the_model_gateway` | 已植入违规验证失败 |

§5 的第三项（判据 4"越用越准"需真实 eval 框架与回归测试）**仍未补** —— Evaluation 仍为 `ABSENT`，本轮未触碰。

---

## 4. 五个业务 Agent

`AI_NATIVE_PRINCIPLES.md` §3.5 定性：这 5 个不是五个功能，而是**五类被声明的 `AgentDefinition`**，各有 `allowed_skills` / `allowed_tools` / `context_policy` / `safety_policy` / `human_handoff_policy`，且统一 **`may_mutate_business_state = false`**。

| Agent | 服务对象 | 输出物定性（R9） | AiFamily 成熟度 |
|---|---|---|---|
| **家长顾问** | 家长 | Perspective / Recommendation | `ABSENT` |
| **孩子陪练** | 孩子 | Perspective（**儿童直接作答继续 HOLD**，见 UI-10 `GATE_BOUNDARY`） | `ABSENT` |
| **助教助手** | 教师/助教 | Recommendation | `ABSENT` |
| **成长规划师** | 家长 | Draft Plan（草案，非计划本身） | `ABSENT` |
| **经营助手** | 机构/运营 | Recommendation | `ABSENT` |

**五个 Agent 全部零实现**，在 AiFamily 与源仓库中都是（`docs/05_ai/AI_ARCHITECTURE.md` §1.2 已独立核实"5 个 Agent 当前均为零实现"）。**没有 `AgentDefinition` 数据结构，没有 Agent Runtime 承载它们。**

孩子陪练的额外约束：涉未成年人的动作须过 Human Gate（R8），且**禁止向未成年人做自动化决策商业营销**（《未成年人网络保护条例》第 24 条第 3 款，法定绝对禁止，见 `SYSTEM_MANIFEST.md` §3.2）。

---

## 5. 四个独占区候选

商业战略 V2 §8.2 提出的四个独占区候选。`AI_NATIVE_PRINCIPLES.md` §1 规定：**独占区候选必须 AI 原生**（五条判据全部答"是"）。

| 独占区候选 | 归属 | AiFamily 成熟度 | 空白证据 |
|---|---|---|---|
| **Family Context** | `backend/intelligence/`（AI Runtime 消费侧输入层，不产生业务权威状态） | `ABSENT` | 源仓库审计确认：`FamilyMemoryDialogueRuntime` **未接入任何调用方**，embedding / pgvector **完全不存在于代码** |
| **Family Growth Graph** | 数据结构 → 业务域持久化层；查询/推理 → `backend/intelligence/` | `ABSENT` | 完全空白。归属分歧（是否需专门只读投影层跨进程）未裁决，见 `TARGET_ARCHITECTURE.md` §6 |
| **Growth Intervention Engine** | `backend/intelligence/` | `ABSENT`（源仓库有雏形数据结构） | 源仓库有 `AssessmentInterpretationPort` 产出的 `hypotheses` / `action_candidates` 雏形，但**缺 `primary_contradiction` 排序层**。AiFamily 内零代码 |
| **Service Blueprint Library** | 蓝图对象 → `backend/domains/service`；匹配能力 → `backend/intelligence/` | `ABSENT` | 零实现。`ServiceBlueprintVersion` 状态机（DRAFT→REVIEWED→PUBLISHED→RETIRED，发布后冻结）尚无代码 |

### 5.1 Family Context 与 Family Growth Graph 是地基，不是增强

`AI_NATIVE_PRINCIPLES.md` §3.3 明确定性：

> Family Context 与 Family Growth Graph 是 AI 原生的**地基**，不是可选增强 —— 它们正是判据 2（数据结构为 AI 理解而设计）和判据 4（越用越准）的载体。源仓库审计已确认这两项目前完全空白，因此**它们是新建，不是优化**。

**含义**：不能把"我们研究过 Family Context 检索层的设计"读成"我们有一个可优化的 Context 层"。当前状态是零。

---

## 6. 明确不算 AI 能力的东西（反面清单）

`AI_NATIVE_PRINCIPLES.md` §4 的反面清单，均在源仓库真实存在，**不得作为 AI 能力交付**：

| # | 反面模式 | 源仓库实例 |
|---|---|---|
| 1 | **硬编码文案冒充智能** | `dev-core-growth.service.ts` 的 `GROWTH_FOCUS_CONTENT` 文案字典 + `dev-platform-surfaces.service.ts` 的 24 张硬编码卡片，返回体自述 `model_gateway: 'NOOP_NOT_INVOKED'` |
| 2 | **关键词匹配冒充理解** | `detect_scenario_keyword` —— 源仓库 `CAPABILITY_TRUTH_REGISTRY.yaml` 自己判定为 "keyword-matching masquerading as understanding，verdict DEPRECATE"。**这个自我诊断是对的，继续有效** |
| 3 | **确定性 fallback 冒充 AI 输出** | `principal_soul_deterministic`，标为 `DETERMINISTIC_TEST_BASELINE + SAFE_FALLBACK / verdict DEPRECATE`。fallback 本身是必要的（fail-closed 要求），但**不得对外呈现为 AI 能力** |
| 4 | **硬编码兜底数值** | UI-17 的 `pointsBalance = membership?.dev_points?.balance ?? 1280` |
| 5 | **AI 只在最后一步做摘要** | 前面全是传统表单流程，最后加一个"AI 生成报告"按钮 —— 判据 1 的典型失败 |

`design_copilot` 属于第六类：**目录名冒充能力**。它已迁入 `backend/intelligence/design_copilot`，`ProductCompiler` / `DesignSimulator` 的每个方法都是 `NotImplementedError`，零调用方、零测试。manifest override 原文：

> 代码已迁入 …… 但其能力状态不变 …… **迁移不得被解读为该能力已存在。**

---

## 7. 成熟度汇总

```text
PRODUCTION    0
PILOT         0
EXPERIMENT    2   Model Gateway（2026-08-29 落地，有代码有测试，零调用方、
                  零外部供应商通过准入）
                  AI Provenance（记录机制已存在，仍缺人工审批链与持久化）
PLANNED       5   Agent Runtime, Tool Runtime, Prompt Registry,
                  Schema Registry, Safety, Human Gate
ABSENT       21   Context Engine, Memory, Evaluation, Observability,
                  Family Principal ×5, 业务 Agent ×5,
                  独占区候选 ×4, design_copilot 的实际能力, ...
```

**AiFamily 有了第一项可运行的 AI 基础设施，但仍没有任何一项可运行的 AI 业务能力。** `backend/intelligence/` 下现有两个目录：`model_gateway`（真实代码 + 110 项测试）与 `design_copilot`（全 `NotImplementedError` 的占位，未变）。

必须同时记住：Model Gateway 是**前置基础设施**，不是能力本身。它当前**没有任何调用方**，且**零个外部供应商通过第16条准入**（见 §3.3）。也就是说，网关能否发出一次真实外呼，眼下取决于一个法务问题而不是工程问题。

这与 `SYSTEM_MANIFEST.md` §2 的定位形成的张力仍然成立：平台被定调为 **AI 原生**，而 AI 层依然是全系统最空的一层 —— 平台内核（6 项有代码有测试）和前端（34 屏幕完整）仍比它实在。**AI 原生目前是架构承诺，不是既成事实。** 落地 Model Gateway 改变的是"这条承诺现在有了合规的落地路径"，不是"承诺已实现"。

---

## 8. 约束来源（AI 能力落地时的硬约束，不可协商）

| 约束 | 内容 |
|---|---|
| **R7** | 领域不得直连模型供应商。一律经 `backend/intelligence/model_gateway`，凭据只由 Model Gateway 读取。`test_no_direct_provider_calls.py` 强制 |
| **R8** | 高影响行为必须过 Human Gate，闸门决策必须落库可审计 |
| **R9** | AI 输出永不自动成为事实。`Fact` ≠ `Perspective` ≠ `Recommendation` ≠ `Action`。**AiFamily 不计算、不存储、不暴露家庭总分与家庭排行** —— 即便某个模型偏好输出一个分数，落地层也不得将其持久化为权威状态 |
| **R10** | 唯一 AI Runtime：所有 AI 能力收敛于 `backend/intelligence/`，禁止 `family_ai_service` / `growth_llm_service` / `assessment_gpt_service` / `teacher_ai_service` 各自调模型。每个组件只允许一份，且只允许一种接入模式 |
| **R6 + Provenance** | AI 参与的每次状态变更必须可追溯到 model / model_version / prompt_version / context_snapshot / confidence / 人工审批记录 |
| **AI 原生五判据** | `docs/05_ai/AI_NATIVE_PRINCIPLES.md` §1，**上位约束**，与任何分项架构文档冲突时以它为准 |
| **AI Runtime 隔离** | `may_mutate_business_state = false`；AI Runtime 不得直接 import 业务域 repository；canonical 写入只能经业务域自己的 Named Action |
| **合规** | `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md`；不做临床诊断；不向未成年人做自动化决策商业营销 |

**R9 的 FELS 继承否定语义**（AI 相关部分）：

| 旧世界对象 | 规则 | 红线 |
|---|---|---|
| `legacy_ai_report.ai_conclusion` | HISTORICAL_AI_HYPOTHESIS | 非 Fact / 非诊断 / 非疗效承诺 |
| `legacy_assessment_score.score` | HISTORICAL_EVIDENCE | 非 GrowthState |
| `legacy_advisor_note.note_text` | PERSPECTIVE | 非 Fact |
| `legacy_alert.risk_score` | SAFETY_SIGNAL_SOURCE | 非阈值 / 非自动动作；高风险须 Human Gate |
| `legacy_profile.family_score` / `.ranking` | **RETIRE** | 永不入 Family |

---

## 9. 与其它文档的分工（避免两处重复维护）

| 文档 | 职责 | 与本文件的关系 |
|---|---|---|
| **本文件** | AI 能力**版图 + 成熟度** | 只答"有什么、多成熟" |
| `docs/05_ai/AI_ARCHITECTURE.md` | AI Runtime **详细设计规格**：5 个 Agent 的输出物定性、数据资产三层画像、Growth Intervention Engine 设计、`primary_contradiction` 判断层的最小可执行落地方式、排期依据 | 详细设计**只在那里维护**，本文件不复制 |
| `docs/05_ai/AI_NATIVE_PRINCIPLES.md` | AI 原生 5 条判据 + 反面清单（**上位约束**） | 本文件引用其判据与反面清单，不改写 |
| `governance/REPOSITORY_CONSTITUTION.md` | R7 / R8 / R9 / R10 原文 | 本文件引用，冲突以宪章为准 |
| `governance/MIGRATION_MANIFEST.yaml` | 各 AI 能力的 disposition 与证据 | 本文件的成熟度断言以它为依据 |
| `TARGET_ARCHITECTURE.md` | AI Runtime 在目标拓扑中的位置、独占区归属判断 | 本文件只记成熟度，不记归属推理 |
| `CURRENT_SYSTEM_BASELINE.md` §4.3/§4.4 | AI 层的 Not Implemented 声明 | 与本文件一致，本文件是其展开 |
