# AI架构 (AI Architecture)

- **状态**: CURRENT — 依据 `governance/REPOSITORY_CONSTITUTION.md` R13，本文件是本主题唯一当前真相
- **生效**: 2026-08-29
- **在...基础上扩展**: `CURRENT_AI_ARCHITECTURE.md`（Wave 0 判定登记：Model Gateway/Human Gate/AI Provenance三项REIMPLEMENT，Python侧零实现）——本文件不推翻其判定，是在其基础上补充Agent体系、数据资产画像、Growth Intervention Engine设计与治理红线的具体展开
- **GROUNDING**: `docs/20_product/strategy/raw/法咪莉教育战略白皮书_30页演讲汇报版.txt`（Slide 16/17/18/19）、`docs/20_product/reference/FAMILY_COMMERCIAL_VALUE_STRATEGY_V2.md`第8节、`governance/REPOSITORY_CONSTITUTION.md`R7/R9/R10、`governance/MIGRATION_PLAN_V2.md`第0节AI Runtime隔离规则

---

## 0. 本文件的性质

`CURRENT_AI_ARCHITECTURE.md`已经确认：AiFamily当前没有任何AI代码，Model Gateway/Human Gate/AI Provenance三项能力在Python侧均为零实现，判定为REIMPLEMENT。本文件不改变这一判定，而是把白皮书里描述的Agent体系、数据资产画像设计、以及V2战略第8节的Growth Intervention Engine设计，对照当前代码现实逐条标注真实完成度——延续`CURRENT_AI_ARCHITECTURE.md`一贯的写法：**每条设计断言后面跟一条"现状核实"**，不允许把PPT愿景写成既成事实。

---

## 1. AI Agent体系：5个Agent

来源：白皮书Slide 17（"AI Agent体系要按真实场景设计"，"每个Agent都必须绑定一个用户任务和一个可衡量结果"）。

| Agent | 服务对象 | 核心任务 | 输出物 |
|---|---|---|---|
| 家长顾问 | 父母 | 解释问题与建议话术 | 沟通方案 |
| 孩子陪练 | 孩子 | 任务提醒与行为鼓励 | 成长任务 |
| 助教助手 | 交付团队 | 批改、点评、预警 | 服务建议 |
| 成长规划师 | 家庭 | 阶段目标与路径 | 成长计划 |
| 经营助手 | 管理层 | 用户、收入、交付分析 | 经营看板 |

### 1.1 R9约束下每个Agent输出物的真实定性

宪章R9（AI输出不得自动成为事实）与`MIGRATION_PLAN_V2.md`第0节保留清单（"AI Runtime隔离规则：`may_mutate_business_state=false`，AI Runtime不得直接import业务域repository，只能产出Draft/Hypothesis/Explanation/Proposal，canonical写入只能经业务域自己的Named Action"）共同决定：上表"输出物"一列的字面表述（沟通方案/成长任务/服务建议/成长计划/经营看板）在实现层必须被重新定性为下面这张表，任何一个Agent都不能跳过右列直接写canonical状态：

| Agent | PPT字面输出物 | 实现层必须的定性 | 谁才能把它变成Fact |
|---|---|---|---|
| 家长顾问 | 沟通方案 | Recommendation（建议） | 家长本人采纳后的行动才是Fact |
| 孩子陪练 | 成长任务 | Proposal（任务候选） | 家庭确认生成的GrowthAction才是Fact（对照UI-09的Named Action：开始/暂停/继续/取消/完成） |
| 助教助手 | 服务建议 | Recommendation（面向服务管家的建议） | 服务管家的验收动作（ServiceTask VERIFIED）才是Fact |
| 成长规划师 | 成长计划 | Draft/Hypothesis（草案） | 家庭确认Intent后生成的正式计划投影才是Fact（对照UI-04/05现状：仅LLM draft/说明，尚无报告事实DTO） |
| 经营助手 | 经营看板 | 只读聚合视图（不涉及Fact/Perspective的家庭层面区分，但同样不得暴露家庭总分/排名——R9） | 不适用（经营看板本身不写业务权威状态） |

### 1.2 现状核实：5个Agent当前均为零实现

`CURRENT_AI_ARCHITECTURE.md`第1、2节已确认Model Gateway/Human Gate在Python侧无对应实现，TS侧唯一网关实现（`packages/ai-gateway/src/index.ts`，894行）也没有以"5个具名Agent"的方式组织代码——TS侧存在三套互不相同的接入模式（`principal.module.ts`最严格的DI工厂+fail-closed、`family-model-gateway.provider.ts`的DI+双env门控、`orchestration/llm-gateway/*`裸`new`违规），但没有一套是按白皮书的5个Agent划分的。**这5个Agent目前只是产品设计意图，不是代码结构**。落地时必须先满足R10（唯一AI Runtime），即5个Agent都收敛于同一套`backend/intelligence/`下的Agent Runtime，而不是像TS侧历史那样各自接入模式不一致。

---

## 2. 数据资产三层画像设计（白皮书Slide 19原始设计）

来源：白皮书Slide 19（"数据资产不是口号，必须从第一天设计采集结构"，"没有结构化数据，AI只是客服；有高质量数据，AI才能成为成长操作系统"）。

| 画像层 | 采集内容 | 定位 |
|---|---|---|
| 父母画像 | 教育方式、沟通风格、焦虑点、参与度 | 理解决策者 |
| 孩子画像 | 习惯、兴趣、动力、行为变化、情绪状态 | 理解成长对象 |
| 家庭画像 | 互动频率、冲突类型、任务完成、改善路径 | 理解关系系统 |

### 2.1 现状核实：三层画像目前是空白，不是已有基础上的优化

这是V2战略第8.2节技术现状调研的直接结论，本文件如实继承，不做乐观化改写：

> 目前只有单会话内规则聚合（`FamilyMemoryDialogueRuntime`未接入任何调用方，embedding/pgvector完全不存在于代码），这是空白，不是已有基础上的优化。

具体拆解到三层画像：

- **父母画像/孩子画像**：白皮书设计的采集字段（教育方式/沟通风格/焦虑点/参与度；习惯/兴趣/动力/行为变化/情绪状态）在代码里没有对应的持久化结构。`perspectives`/`evidence_records`表严格限定在单次onboarding内查询，从未跨会话检索，即没有"持续积累"这一画像的核心特征。
- **家庭画像**：互动频率/冲突类型/任务完成/改善路径同样没有独立的家庭层面时间序列结构。`GrowthAction`的状态机（UI-09已验证）记录的是单次任务的完成状态，不等同于跨任务、跨阶段聚合出的"改善路径"。
- **`FamilyMemoryDialogueRuntime`空白的意义**：这不是"功能还没做完"的一般性描述，是审计层面确认的具体事实——该Runtime类存在但没有任何调用方接入，即写了代码但从未在业务流程中被真实触发，是纯粹的死代码/占位符。

**结论**：白皮书Slide 19的三层画像设计方向正确（与Family Context/Family Growth Graph独占区候选完全对应），但当前完成度是0，不是30%或50%。任何后续设计文档如果引用"父母画像已建立xx字段"，必须先核实是否真的接入了调用方，不能只看是否存在同名的Python类定义。

### 2.2 三层画像与独占区候选的映射关系

`BUSINESS_ARCHITECTURE.md`第6节、`BUSINESS_SCENARIOS_AND_PROCESSES.md`第4.8节已把Family Context/Family Growth Graph列为独占区候选。白皮书Slide 19的三层画像设计，正是这两个独占区候选在数据结构层面的具体展开：

- 三层画像的静态字段（教育方式/习惯/互动频率等）对应 **Family Context** 的"结构"维度；
- 三层画像随时间演化的记录（行为变化/改善路径）对应 **Family Growth Graph** 的"T0→T1→T2→T3时间轴"维度。

两者目前均为空白，落地时应该是同一套底层存储与检索能力的两个视图，不应该分别重复建设。

---

## 3. Growth Intervention Engine设计

来源：V2战略第8.2/8.3节。

### 3.1 定位：不是推荐引擎

> Growth Intervention Engine——不是推荐引擎，是"给定Family Context+GrowthNeed+当前状态+历史证据，判断下一步最适合做什么（可能是"暂停干预"而不是"推荐课程"）"的决策能力。

这个定位本身是对R9（不诊断不打分却依然专业陪伴）和六项战略原则第5条（AI可以建议、生成和协助，但高风险分派、验收与权益决定必须由人负责）在这一具体能力上的落地：这个引擎的输出永远是"建议下一步做什么"这一层的Recommendation，"暂停干预"这个选项本身就是对"AI不应该为了显得有用而强行推荐内容"这一红线的工程化体现。

### 3.2 现状核实：雏形数据结构存在，缺主要矛盾判断层

当前`AssessmentInterpretationPort`已经产出结构化的`hypotheses`/`action_candidates`字段，是这个引擎的雏形数据结构，但：

- 没有"主要矛盾（primary_contradiction）"这一层判断；
- 没有跨会话历史证据输入（因为第2节确认Family Context/Growth Graph均为空白，这个引擎依赖的输入数据本身还不存在）。

### 3.3 主要矛盾（primary_contradiction）判断层的最小可执行落地方式

来源：V2战略第8.3节，逐字引用其设计判断，不做改写：

> 现有的`hypotheses`（假设）已经是"从evidence到可能原因"的一步，但AI不应该从"问题"直接跳到"方案"——中间必须有"在这些假设里，当前最应该突破的1-3个关键矛盾是什么"这一层判断，且排除法之外的假设不是被否定，只是暂不作为本轮干预依据。
>
> **最小可执行的落地方式（不是新建一整套引擎）**：在现有hypothesis结构基础上，给`GrowthHypothesis`/`hypotheses`字段增加一个`primary_contradiction_ref`（可空）+置信度排序，而不是新建`GrowthProblemModel`这样的全新对象。理由：现有`AssessmentInterpretationPort.interpret()`已经产出结构化的`hypotheses`数组，加一个排序/标注字段的成本远低于从零建模。

这条设计的关键约束是**增量优先于新建对象**——技术现状调研已经证明"从零建"在这个项目里代价高、周期长。落地时若有工程师提出"应该新建一个GrowthProblemModel类"，需要先回答这个增量路径为什么不够用，不能默认从零开始。

Service Blueprint层的呼应（同样来自V2战略8.3节）：如果一个21天计划的设计输入里包含"这个家庭当前的primary_contradiction是什么"，产品设计者就被迫先回答矛盾是什么、再决定选哪些课程/干预，而不是反过来先选内容再凑理由——这个约束应该体现在Service Blueprint Library的生成输入契约里加一个必填字段，不需要新建组件。

### 3.4 排期依据（沿用V2战略8.4节，不重新拍板）

| 优先级 | 能力 | 理由 |
|---|---|---|
| P0 | Family Context 最小可用检索层 | 四个独占区候选里最基础，其它三项都依赖它 |
| P0 | GrowthHypothesis加primary_contradiction排序 | 成本最低的增量，不是新建对象 |
| P1 | Principal Soul YAML与代码脱域修复 | "灵魂"要先自己不脱节，再谈深化 |
| P1 | Service Blueprint接入primary_contradiction输入 | 把方法论落进已有对象，不新建组件 |
| P2 | Growth Intervention Engine雏形（在现有hypotheses/action_candidates基础上加决策层） | 依赖P0的Context落地后才有输入数据 |
| P3 | 多Agent协同/Agent Runtime | 现有代码连单一Agent的记忆和人格一致性都没做实，多Agent协同不应该先做 |

**这条优先级直接约束第1节的5个Agent落地顺序**：P3明确"多Agent协同不应该先做"，意味着5个Agent不应该在Family Context P0落地之前，同时开工建设成一套完整的多Agent Runtime——应该先让单一Agent（很可能是与ASSESSMENT闭环绑定的"成长规划师"或"家长顾问"）在有真实Family Context输入的情况下把记忆和人格一致性做实，再横向扩展到其余4个Agent。

---

## 4. AI治理红线

本节汇总约束AI能力落地方式的红线，全部来自已生效的宪章条款或已确认未推翻的商业原则，不新增红线，只做汇总以便AI架构落地时对照检查。

### 4.1 六项战略原则第5条：高风险决定必须由人负责

> AI可以建议、生成和协助，但高风险分派、验收与权益决定必须由人负责。

来源：V1.1第1.4节，V2战略第4节确认未被推翻。落地到AI架构：

- 服务分派（哪个教师/顾问承接哪个ServiceTask）——AI可以给出候选排序建议，但最终分派决定必须经过`Human Gate`（对应宪章R8：高影响行为必须过闸的具体清单之一"教师推荐"）。
- 服务验收（ServiceTask是否VERIFIED）——AI不能自行判定验收通过，必须由服务管家或质量审核人确认。
- 权益决定（会员升级、分配池释放）——同样必须由人负责，AI不能触发`AllocationStatement`的finalize动作。

### 4.2 R9：不做家庭总分/排名

`AiFamily不计算、不存储、不暴露家庭总分与家庭排行`——这条约束对AI生成的任何"评分/排名"倾向输出同样适用：即便某个模型偏好输出一个分数，落地层也不得将其持久化为权威状态（`CURRENT_AI_ARCHITECTURE.md`第4节原话）。这也是`BUSINESS_SCENARIOS_AND_PROCESSES.md`第2.3节GROWTH闭环全部标注`GATE_BOUNDARY`的直接原因——不是技术缺口，是这条红线主动限制的结果。

### 4.3 R7 + R10：AI Runtime不得直接import业务域repository，只能经Named Action写入canonical状态

这是本文件对第1节Agent输出物定性表（1.1节）的制度依据，合并两条宪章规则表述：

- **R7（领域不得直连模型供应商）**：任何领域模块、应用服务、工作流，不得直接调用OpenAI/Anthropic/DeepSeek/Gemini等供应商SDK或HTTP端点，也不得直接实例化会发起外部请求的网关类。一律经由`backend/intelligence/model_gateway`，凭据只由Model Gateway读取。
  - 伤疤证据：`family-llm-gateway.service.ts:58-63`在业务服务方法内部直接`new OpenAICompatibleAiGateway({...})`，绕过DI、绕过fail-closed工厂、绕过`AttemptRecordingGateway`审计——**策略写成了常量，但没有任何东西执行它**，判定为`orchestration_llm_gateway_violation`（REVIEW_REQUIRED/BLOCKED），Python侧重建时不得重复此违规。
- **R10（唯一AI Runtime）**：所有AI能力收敛于`backend/intelligence/`。禁止出现`family_ai_service`/`growth_llm_service`/`assessment_gpt_service`/`teacher_ai_service`各自调模型。Model Gateway/Context Engine/Agent Runtime/Tool Runtime/Prompt Registry/Safety/Human Gate/Evaluation/Trace/Cost/Audit各一份。
- **`MIGRATION_PLAN_V2.md`第0节的AI Runtime隔离规则**（作为V1保留清单，未被推翻）：`may_mutate_business_state=false`，AI Runtime不得直接import业务域repository，只能产出Draft/Hypothesis/Explanation/Proposal，canonical写入只能经业务域自己的Named Action。

这三条共同构成"AI Runtime与业务域之间只能通过Named Action单向通信"的架构约束：AI Runtime生成Draft/Hypothesis/Recommendation → 家庭或服务管家做出Decision → 业务域自己的Named Action把Decision写入canonical Fact状态 → 产生AuditEvent（R6）。AI Runtime全程不接触业务域的repository/ORM层。

### 4.4 高影响行为过闸清单（R8）

以下行为必须经过对应Human Gate，且闸门决策必须落库可审计：类诊断输出、家庭计划变更、教师推荐、服务购买、对外沟通、会员升级、涉未成年人的敏感动作。这份清单直接约束第1节5个Agent中"成长规划师"（家庭计划变更）、"助教助手"（隐含教师推荐场景）、"经营助手"（若涉及对外沟通）的落地范围。

---

## 5. 与`CURRENT_AI_ARCHITECTURE.md`的关系

`CURRENT_AI_ARCHITECTURE.md`第5节小结表（Model Gateway/Human Gate/AI Provenance三项REIMPLEMENT判定）继续有效，本文件不修改该表。本文件补充的是该表之上的产品设计层——5个Agent、三层画像、Growth Intervention Engine——这些设计对Model Gateway/Human Gate/AI Provenance三项基础设施均有依赖，落地顺序上必须先有Model Gateway（P0前置）才能开始任何Agent的实际调用。
