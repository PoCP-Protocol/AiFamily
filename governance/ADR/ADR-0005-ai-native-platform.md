# ADR-0005: AiFamily 是 AI 原生平台（不是"传统平台 + AI 功能模块"）

- **Status**: Accepted
- **Date**: 2026-08-29
- **Deciders**: project-owner / chief-architect
- **Supersedes**: null
- **Superseded By**: null

## Context

project-owner 明确定调：**"我们这个平台一定是AI原生的平台"**。

这不是修辞选择，是架构分叉点。而**默认惯性会把系统做成反面**——因为迁移工作天然倾向于复制源结构，而源仓库 `family-ai` 恰恰是"传统平台 + AI 功能模块"的标本：

1. **AI 被放在 `packages/ai-gateway`（894 行）作为被业务模块调用的工具。** 它的能力是真实的（Routing / Timeout / Admission / FailClosed / Provenance / HumanGate 全部真实存在），但它在架构中的位置是**旁挂的服务**，业务模块决定何时调用它。
2. **34 个 UI 中绝大多数是传统 CRUD 界面，AI 只出现在 UI-03（假设解读）这一处。** 一个平台如果 33/34 的界面在 AI 关掉后照常工作，它不是 AI 原生的。
3. **最直白的自白**：`50_开发_dev/apps/api/src/modules/family/dev-core-growth.service.ts:43-60` 用 24 张硬编码 UI 卡片和一本中文文案字典模拟"智能"，并在返回体里写着 `model_gateway: 'NOOP_NOT_INVOKED'`。**"智能"是硬编码的文案字典，模型根本没被调用**——而这套服务被 9+ 个真实 Mobile 屏幕消费。这是"AI 是可选装饰"的架构自白。
4. **AI 接入纪律的三重分裂**：只有一份网关实现，但有三套互不相同的接入模式——`principal.module.ts:19-34`（DI 工厂 + fail-closed + AttemptRecording，最严）、`family/family-model-gateway.provider.ts:17-22`（DI + 双 env 门控）、`orchestration/llm-gateway/*`（业务方法内裸 `new OpenAICompatibleAiGateway`，见 R7 伤疤）。重复的不是实现，是纪律。

如果不把 AI 原生的判据写下来并置于各分项架构文档之上，迁移会忠实地把上述形态复制到 Python 侧——因为每一步局部决策看起来都是合理的。

## Decision

AiFamily 是 AI 原生平台。这一定位以 `docs/05_ai/AI_NATIVE_PRINCIPLES.md`（`DOC_KIND = ARCHITECTURE_CONSTRAINT`，`STATUS = BINDING`）为载体，**优先于**总体蓝图 / 技术架构 / 数据架构 / 业务架构 / 业务场景 / AI 架构——上述任何文档与之冲突时以它为准。

### 1. AI 原生 5 条判据（可检验的判断题，不是宣言）

对任何能力/模块/功能，五问都答"是"才算 AI 原生：

| # | 判据 | 反面（传统平台 + AI 模块） |
|---|---|---|
| 1 | **AI 是不是主路径？** 关掉 AI，这个能力是否直接失去核心价值（而非"退化为手动版仍可用"） | AI 是旁路增强，关掉后走规则/人工兜底，业务照常 |
| 2 | **数据结构是否为 AI 理解而设计？** 存的是 AI 可推理的语义结构（证据/假设/上下文/时序） | 数据库是 CRUD 表单的持久化，AI 用时再临时拼 prompt |
| 3 | **是否生成式优先？** 智能部分由模型生成，硬编码只留护栏 | 用 if-else / 关键词匹配 / 硬编码文案模拟智能 |
| 4 | **是否越用越准？** 存在真实的学习闭环（交互→证据沉淀→下一次更准），且**有代码落地不只是设计意图** | 静态规则，用一年和用一天效果相同 |
| 5 | **AI 的权限边界是否显式建模？** 有 AgentDefinition / 工具注册 / Draft-only 输出 / 人工闸门 | AI 调用散落各处，能力边界靠开发者自觉 |

### 2. 判据 1 的重要推论：不是所有能力都必须 AI 原生

| 类型 | Domain | AI 原生要求 |
|---|---|---|
| **核心域** | assessment, growth, journey, action, outcome | **必须** AI 原生 |
| **优势域** | service, teacher, institution, community | **应当** AI 原生 |
| **支撑域** | identity, consent, tenancy, commerce | **不要求**。用户登录、支付回调、审计日志本就不该由 AI 主导 |

**把 AI 塞进支撑域是另一种错误**，R7 / R9 正是防这个。核心域/支撑域的判断用三区方法论：独占区候选必须 AI 原生，优势区应当，同质区与支撑域不要求。

### 3. 关键推论：AI 原生 ≠ 放宽约束

一个常见的错误推论是"既然是 AI 原生，AI 就该有更大权限"。相反：

```text
AI 是主干  →  AI 出错的破坏半径最大  →  约束必须更严，不是更松
```

以下宪章条款在 AI 原生架构下**加强**：

- **R9（AI 输出不得自动成为事实）**：AI 原生意味着绝大多数有价值的输出都来自 AI，因此 `Fact / Perspective / Recommendation / Action / Outcome` 的区分不是边角规则，是**主数据模型的骨架**。AI 产出永远落在 Perspective/Recommendation 层，跨越到 Fact 层必须经 Named Action + 人工确认。
- **R7（领域不直连供应商）**：AI 调用越多越必须收敛到单一 Model Gateway，否则会像源仓库那样散落在业务服务内部。
- **R6（无审计不改状态）+ AI Provenance**：AI 参与的每一次状态变更必须可追溯到 model / model_version / prompt_version / context_snapshot / confidence / 人工审批记录。**AI 原生系统若无 provenance，等于无法解释自己为什么这么建议——对家庭教育场景不可接受。**
- **不做家庭总分/家庭排名（R9 红线）**：AI 原生不是"用 AI 算出更精准的分数"。**恰恰因为 AI 能轻易生成一个看起来专业的分数，这条红线才更需要守。**

### 4. 架构含义

AI Runtime 不是挂在业务旁边的一个方框，而是与业务域**并列的主干**。三进程划分 `family_api` / `ai_runtime` / `workflow_worker`：`ai_runtime` 承载核心域智能，`family_api` 守护事实与权限，`workflow_worker` 承载"AI 提议→人工确认→落库"这类跨时长流程。**缺任何一个，AI 原生都不成立。**

## Alternatives Considered

### A. 传统平台 + AI 增强模块（源仓库的现状形态）
**支持理由（不弱）**：风险最低，AI 失效不影响主业务，可增量交付，每个 AI 功能独立验证独立回滚。合规上也更安全——AI 不在主路径就更容易论证"人类始终在决策链上"。

**否决理由**：
- 这条路径的终局是同质化产品。测评解读、成长诊断、干预决策若由规则驱动，则平台的独占价值不存在——任何竞品都能做出一套等价规则。
- 判据 4（越用越准）在这个形态下无法成立：AI 是旁路，交互不沉淀为证据，用一年和用一天效果相同。
- 最具体的反证是源仓库自己：`dev-core-growth.service.ts` 的硬编码文案字典**正是"AI 增强模块"路线走到极端的自然产物**——当 AI 是可选的，一个足够好的假 AI 就能满足验收，于是真 AI 永远不会被接上。

### B. AI 原生但放宽 R9（允许 AI 输出直接落库为事实）
**支持理由**：R9 的四层区分（Fact/Perspective/Recommendation/Action）带来大量确认步骤，每个 AI 建议都要家庭点确认，产品体验割裂，且工程上要维护两套状态。若 AI 足够准，直接落库更顺畅。

**否决理由**：
- 业务领域一票否决。家庭教育场景的 AI 输出是关于**未成年人的行为、性格、发展状况**的判断。AI 生成的"孩子有注意力问题"若直接成为家庭的权威事实，其后果不是数据错误，是对一个真实儿童的定性。FELS 参考实现留下的否定语义（`legacy_ai_report.ai_conclusion` → `HISTORICAL_AI_HYPOTHESIS`，非 Fact / 非诊断 / 非疗效承诺）是源系统踩过的坑。
- 法定约束（见 ADR-0006）：PIPL 第 24 条第 3 款赋予个人**拒绝仅通过自动化决策作出决定**的权利。AI 直接落库为事实在法律上就是"仅通过自动化决策"，不可行。
- 因此 **R9 与 AI 原生不是权衡关系，而是前提关系**：只有当 AI 是主干，才有必要如此严格地约束它能写什么。

### C. AI 原生适用于全部域（含 identity / consent / commerce）
**支持理由**：一致性，不需要维护"哪些域算核心域"这个判断，避免"支撑域"成为逃避 AI 原生要求的借口。

**否决理由**：把 AI 塞进支撑域是**具体的危害而非仅是浪费**。登录鉴权、同意判定、支付回调、审计写入必须是确定性的、可复现的、可审计的。让 LLM 参与"这个 actor 是否有权读这个家庭的数据"这个判定，等于把 fail-closed 换成概率性判断。R7 与 R9 存在的目的之一正是防止这个方向。

### D. 推迟这个决定，先把业务能力建起来再谈 AI 原生
**支持理由**：当前后端只有 `/health` `/ready`，零业务路由，谈 AI 原生像是过早优化。

**否决理由**：判据 2（数据结构为 AI 理解而设计）**是不可推迟的**。如果先按 CRUD 表单建 schema，之后再"加上 AI"，就必须重建持久化层——而那时数据已经在库里。判据 2 必须在第一张表建立前就生效。这也是为什么 `docs/05_ai/AI_NATIVE_PRINCIPLES.md` 被定位为约束**数据架构**文档的上位文件。

## Consequences

### 正面
- AI 原生成为可检验的判断题（5 问）而非口号，任何 PR 都能被问"这个能力对判据 1 答是还是否"。
- 核心域/支撑域的划分同时防住两个方向的错误：核心域做成 CRUD，与支撑域塞进 AI。
- 与宪章不冲突反而互为支撑，避免了"AI 原生"被用作放宽治理的理由。

### 负面 / 代价
- **判据 4（越用越准）当前完全无法满足**：`docs/00_system/CURRENT_AI_MAP.md` 记录 Family Context 完全空白，源仓库 `FamilyMemoryDialogueRuntime` 未接入任何调用方，embedding / pgvector 不存在。学习闭环连数据结构都没有。
- **判据 3 / 5 目前也不满足**：`backend/intelligence/` 下唯一的东西是 `design_copilot`，其 `ProductCompiler` / `DesignSimulator` 每个方法都是 `NotImplementedError`，零调用方零测试；`backend/intelligence/model_gateway` 目录**根本不存在**。也就是说 AI 原生当前是**零实现的定位声明**。
- 三进程架构（`family_api` / `ai_runtime` / `workflow_worker`）意味着运维复杂度从一开始就高于单体。
- Provenance 要求（model / prompt_version / context_snapshot / confidence）给每次 AI 参与的写入都加了持久化负担。

### 需要接受的风险
- **最大风险：定位声明与实现之间的落差本身会变成新的漂移源。** 一份 `STATUS = BINDING` 的 AI 原生原则文档，配一个 `backend/intelligence/` 只有 `NotImplementedError` 的仓库，正是本仓库反复警惕的形态（R14 伤疤：写成文档的策略等于没有策略）。缓释靠 `CURRENT_AI_MAP.md` 如实记录零实现状态，但这只是缓释不是消除。
- AI 原生依赖外部 LLM 供应商，而 ADR-0006 记录的"不得转委托"约束可能实质限制供应商选型，进而限制 AI 能力上限。这两个决定存在张力，尚未解决。
- 判据 1 使 AI 失效等于核心能力失效，可用性风险集中于模型供应链。

## Enforcement

**当前仅为意图，几乎无机械执行。这是本 ADR 最诚实的部分。**

- **唯一真实生效的相关护栏是否定形式的**：`tests/architecture/test_no_direct_provider_calls.py`（R7）禁止业务代码直连供应商 SDK。它防的是"AI 接入失序"，**不**证明任何 AI 能力存在。
- 5 条判据**全部无法机械检验**。没有测试能断言"关掉 AI 这个能力就失去核心价值"。
- 核心域/支撑域的划分目前只写在 `docs/05_ai/AI_NATIVE_PRINCIPLES.md` §1 与 `docs/00_system/CURRENT_DOMAIN_MAP.md` §2 的表格里，**`governance/DOMAIN_REGISTRY.yaml` 没有 `ai_native_required` 字段**——因此没有任何机制阻止一个核心域被实现成纯 CRUD。
- R6 的 AI Provenance 要求、R8 的 Human Gate 要求，宪章第 2 节均标注为"Wave 1–5 逐步接入"，当前无测试。

**补齐路径（应在核心域首个 PR 中落地）**：
1. 给 `DOMAIN_REGISTRY.yaml` 增加 `domain_class`（core / advantage / supporting / internal_tool）与 `ai_native_required` 字段，并加架构测试断言核心域条目必须声明其 AI 主路径所在模块。
2. `model_gateway` 建成后，加测试断言核心域的 AI 调用必须经它，且 Provenance 字段非空。

## References

- `docs/05_ai/AI_NATIVE_PRINCIPLES.md`（`DOC_KIND = ARCHITECTURE_CONSTRAINT`，`STATUS = BINDING` — 本决定的完整正文）
- `docs/05_ai/AI_ARCHITECTURE.md`、`docs/00_system/CURRENT_AI_MAP.md`
- `governance/REPOSITORY_CONSTITUTION.md` R6 / R7 / R8 / R9 / R10
- `governance/DOMAIN_REGISTRY.yaml` → `model_gateway`（`status: NOT_STARTED`）、`design_copilot`（`MIGRATED_STRUCTURE_ONLY`）
- `docs/00_system/CURRENT_DOMAIN_MAP.md` §2（核心域/支撑域划分表）
- ADR-0006（未成年人合规约束——与 AI 原生形成实质张力）
