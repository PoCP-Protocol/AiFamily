---
id: AI-PRINCIPLES-001
title: AiFamily AI 原生原则
type: ai
status: current
version: 1.0
owner: project-owner
created: 2026-08-29
updated: 2026-08-29
canonical: true
supersedes: null
superseded_by: null
---

# AiFamily AI 原生原则 (AI-Native Principles)

```text
DOC_KIND      = ARCHITECTURE_CONSTRAINT (上位约束, 优先于各分项架构文档)
DATE          = 2026-08-29
AUTHORIZED_BY = project-owner ("我们这个平台一定是AI原生的平台")
STATUS        = BINDING
适用范围        = MASTER_BLUEPRINT / TECH_ARCHITECTURE / DATA_ARCHITECTURE /
                BUSINESS_ARCHITECTURE / BUSINESS_SCENARIOS_AND_PROCESSES / AI_ARCHITECTURE
                —— 上述任何一份文档与本文件冲突时，以本文件为准
```

## 0. 为什么需要这份文件

项目负责人明确定调：**AiFamily 是 AI 原生平台**，不是"传统业务平台 + AI 功能模块"。

这两者的差别不是修辞，是架构分叉点。如果不写下来，默认惯性会把系统做成后者——因为源仓库 `family-ai` 目前正是后者的形态，而迁移工作天然倾向于复制源结构：

- 源仓库把 AI 放在 `packages/ai-gateway`(894行) 作为被业务模块调用的**工具**；
- 34个UI中大部分是传统CRUD界面，AI 只出现在 UI-03(假设解读) 这一处；
- `dev-core-growth.service.ts` 用 24 张硬编码卡片和一本中文文案字典模拟"智能"，`model_gateway: 'NOOP_NOT_INVOKED'` 写在返回体里——这是"AI 是可选装饰"的架构自白。

本文件定义 AI 原生的判据，并明确它与已有工程宪章(`governance/REPOSITORY_CONSTITUTION.md`)的关系：**AI 原生不是放宽宪章，恰恰是宪章 R9(AI输出不得自动成为事实) 的前提**——只有当 AI 是系统的主干，才有必要如此严格地约束它能写什么。

## 1. AI 原生的判据（不是宣言，是可检验的判断题）

对任何一个 AiFamily 的能力/模块/功能，用以下五问检验。五问都答"是"才算 AI 原生：

| # | 判据 | 反面（传统平台+AI模块） |
|---|---|---|
| 1 | **AI 是不是主路径？** 关掉 AI，这个能力是否直接失去核心价值（而不是"退化为手动版仍可用"） | AI 是旁路增强，关掉后走规则/人工兜底，业务照常 |
| 2 | **数据结构是否为 AI 理解而设计？** 存的是 AI 可推理的语义结构(证据/假设/上下文/时序)，而不是仅供人读的表单字段 | 数据库是 CRUD 表单的持久化，AI 用时再临时拼 prompt |
| 3 | **是否生成式优先？** 智能部分由模型生成，硬编码只留护栏 | 用 if-else/关键词匹配/硬编码文案模拟智能 |
| 4 | **是否越用越准？** 存在真实的学习闭环(交互→证据沉淀→下一次更准)，且该闭环有代码落地不只是设计意图 | 静态规则，用一年和用一天效果相同 |
| 5 | **AI 的权限边界是否显式建模？** 有 AgentDefinition/工具注册/Draft-only 输出/人工闸门，AI 能做什么是被声明和执行的 | AI 调用散落各处，能力边界靠开发者自觉 |

**判据1的重要推论**：不是所有能力都必须 AI 原生。用户登录、支付回调、审计日志本就不该由 AI 主导——它们是**支撑域**。AI 原生的要求作用于**核心域**：测评解读、成长诊断、干预决策、陪伴对话、方案生成。把 AI 塞进支撑域是另一种错误（宪章 R7/R9 正是防这个）。

判断某能力属于核心域还是支撑域，用 `docs/01_strategy/COMMERCIAL_VALUE_STRATEGY.md` 第8节的三区方法论：**独占区候选必须 AI 原生；优势区应当 AI 原生；同质区和支撑域不要求**。

## 2. AI 原生 ≠ 放宽约束（与工程宪章的关系）

一个常见的错误推论是"既然是 AI 原生，AI 就应该有更大权限"。相反：

```text
AI 是主干  →  AI 出错的破坏半径最大  →  约束必须更严，不是更松
```

具体地，以下宪章条款在 AI 原生架构下**加强**而非削弱：

- **R9(AI输出不得自动成为事实)**：AI 原生意味着绝大多数有价值的输出都来自 AI，因此 `Fact / Perspective / Recommendation / Action / Outcome` 的四层区分不是边角规则，是**主数据模型的骨架**。AI 产出永远落在 Perspective/Recommendation 层，跨越到 Fact 层必须经 Named Action + 人工确认。
- **R7(领域不直连供应商)**：AI 调用越多越必须收敛到单一 Model Gateway，否则供应商调用会像源仓库那样散落在业务服务内部(`family-llm-gateway.service.ts:58-63` 的裸 `new OpenAICompatibleAiGateway`)。
- **R6(无审计不改状态)** + **AI Provenance**：AI 参与的每一次状态变更都必须可追溯到 model/model_version/prompt_version/context_snapshot/confidence/人工审批记录。AI 原生系统若无 provenance，等于无法解释自己为什么这么建议——对家庭教育场景是不可接受的。
- **不做家庭总分/家庭排名(R9红线)**：AI 原生不是"用 AI 算出更精准的分数"。恰恰因为 AI 能轻易生成一个看起来专业的分数，这条红线才更需要守——`docs/01_strategy/COMMERCIAL_VALUE_STRATEGY.md` 第0.1节"家是港湾"定位已经把这一点确立为价值筛选器。

## 3. 架构含义（各分项架构文档必须遵守的具体要求）

### 3.1 对总体蓝图 (MASTER_BLUEPRINT.md)
AI Runtime 不是挂在业务旁边的一个方框，而是与业务域**并列的主干**。三进程划分 `family_api` / `ai_runtime` / `workflow_worker` 中，`ai_runtime` 承载核心域智能，`family_api` 守护事实与权限，`workflow_worker` 承载"AI提议→人工确认→落库"这类跨时长流程。缺任何一个，AI 原生都不成立。

### 3.2 对技术架构 (TECH_ARCHITECTURE.md)
- AI 调用必须是**一等公民基础设施**：Model Gateway 的容错(超时/重试/降级/成本控制/fail-closed)与数据库连接池同等重要级别。
- 需要 Agent Runtime、Tool Runtime、Prompt Registry、Schema Registry、Context Broker、Memory System、Eval 框架——这些不是"未来可能加"，是核心域能工作的前提。
- 逻辑隔离仍然强制：`ai_runtime` 代码不得 import 业务域 repository(沿用源仓库迁移计划第6节的这条正确决定)。

### 3.3 对数据架构 (DATA_ARCHITECTURE.md)
数据模型的第一目标是**让 AI 能推理**，不是让表单能保存：
- 证据(Evidence)、假设(Hypothesis)、上下文快照(Context Snapshot)、时序(T0→T1→T2→T3)是一等实体，不是附属字段。
- Family Context 与 Family Growth Graph 是 AI 原生的**地基**，不是可选增强——它们正是判据2和判据4的载体。源仓库审计确认两项曾完全空白；当前 AiFamily 已有 Context SQL durable adapter 与 Growth Graph 0023 只读投影实验接缝，但全域事件接入、生产权限和长期评测仍未完成，因此仍按“新建能力”治理，不把实验接缝误读为生产能力。
- 每条 AI 生成记录必须带 provenance 字段与 `status: DRAFT/PROPOSED` 初始态，且无任何代码路径可自动置为 VALIDATED/APPROVED。

### 3.4 对业务架构与场景流程
业务流程设计要假设"AI 先给出理解和建议，人在关键节点确认"，而不是"人填表单，AI 事后总结"。六类业务闭环(ASSESSMENT/PLAN/GROWTH/SERVICE/COMMERCE/COMMUNITY)中，ASSESSMENT 和 PLAN 属核心域必须 AI 原生；COMMERCE 的支付结算属支撑域不要求。

### 3.5 对 AI 架构 (AI_ARCHITECTURE.md)
这份文档从"AI 功能清单"升级为**平台核心运行时规格**：5个 Agent(家长顾问/孩子陪练/助教助手/成长规划师/经营助手)不是五个功能，是五类被声明的 AgentDefinition，各有 allowed_skills / allowed_tools / context_policy / safety_policy / human_handoff_policy，且统一 `may_mutate_business_state = false`。

## 4. 反面清单（明确不算 AI 原生，不得作为 AI 能力交付）

以下模式在源仓库中真实存在，是被本文件明确否定的：

1. **硬编码文案冒充智能**：`dev-core-growth.service.ts` 的 `GROWTH_FOCUS_CONTENT` 文案字典 + `dev-platform-surfaces.service.ts` 的24张硬编码卡片。
2. **关键词匹配冒充理解**：源仓库 `governance/CAPABILITY_TRUTH_REGISTRY.yaml` 自己已把 `detect_scenario_keyword` 判定为"keyword-matching masquerading as understanding，verdict DEPRECATE"——这个自我诊断是对的，继续有效。
3. **确定性 fallback 冒充 AI 输出**：同一 registry 里 `principal_soul_deterministic` 被标为 `DETERMINISTIC_TEST_BASELINE + SAFE_FALLBACK / verdict DEPRECATE`。fallback 本身是必要的(fail-closed 要求)，但不得对外呈现为 AI 能力。
4. **硬编码兜底数值**：UI-17 的 `pointsBalance = membership?.dev_points?.balance ?? 1280`。
5. **AI 只在最后一步做摘要**：前面全部是传统表单流程，最后加一个"AI 生成报告"按钮——这是判据1的典型失败。

## 5. 验证方式

本文件的约束需要落到可执行检查，而不是停留在文档：

- 已有的架构测试 `tests/architecture/test_no_direct_provider_calls.py`(R7) 是第一道，防 AI 调用散落。
- **待补(Wave 2+)**：`may_mutate_business_state=false` 的静态检查——扫描 `backend/intelligence/` 下是否有 import 业务域 repository 的路径。
- **待补(Wave 2+)**：AI 生成记录的初始 status 检查——扫描是否存在把 AI 产出直接置为 VALIDATED/APPROVED 的代码路径。
- **待补(独占区能力落地时)**：判据4(越用越准)的验证需要真实 eval 框架与回归测试，不是靠声明。

未被检查覆盖的判据只是意图，不是护栏——这与宪章 R14 的立场一致。
