# ADR-0015: 采纳 Family Growth Intelligence OS 为平台组织架构，并裁决价值层的三条边界

- **Status**: Accepted
- **Date**: 2026-08-29
- **Deciders**: project-owner（定调）/ chief-architect（边界裁决）
- **Supersedes**: null
- **Superseded By**: null

## Context

### 1. project-owner 的定调

2026-08-29，project-owner 提出把平台的组织原则从「以 LLM / Agent / RAG 为中心」与
「以课程 / 测评 / 21 天成长营为中心」双双上移，改为围绕一条**家庭价值创造链**建设：

```text
理解家庭 → 稳定情绪 → 看清问题 → 找到主要矛盾 → 恢复掌控感 → 采取行动
→ 产生改变 → 形成成长证据 → 降低家庭时间与试错成本 → 建立长期信任 → 更深地理解家庭
```

并给出两条关键结构判断：

1. **`Model` 是最底层，不是最上层。** 分层为
   Experience → Value → Growth Intelligence → Product Intelligence → Service Intelligence
   → AI Runtime → Data Platform → Model Layer。
2. **平台的中心不是 Agent Runtime，而是 Family Value & Growth Kernel。**
   核心资产是 Family Context / Family State / Growth Problem Model / Value Architecture /
   Growth Strategy / Intervention / Evidence / Long-Term Memory；
   **Agent 是执行这些资产的智能劳动者，不是平台本身。**

以及七个引擎的职责划分（Family Context / Emotional Intelligence / Growth Intelligence /
Intervention / Product Intelligence / Service Intelligence / Learning & Value）、
四层价值（Emotional → Action → Growth → Economic）、
以及一条具体的落地建议：**PR-003 时把 `Value Architecture` 正式纳入领域模型**，
插入既有链条成为 `Problem → Hypothesis → Contradiction → Value Architecture → Strategy`。

### 2. 为什么这个定调解决了一个实测存在的张力

`docs/00_system/CURRENT_AI_MAP.md` §7 记录了一个必须被诚实对待的矛盾：
平台被定调 AI 原生，而 **AI 层是全系统最空的一层**——平台内核 6 项有代码有测试、
前端 34 屏完整迁入，而 `backend/intelligence/` 下 `design_copilot` 全为 `NotImplementedError`；
该文件的结论是「AI 原生目前是架构承诺，不是既成事实」。

「`Model` 在最底层 + Agent 不是中心」这一判断**消解了这个张力**：
若护城河本就不在 AI 层，则 AI 层当前为空不是致命缺口，而是正常的建设顺序。
核心资产（Context / State / Problem / Contradiction / Strategy / Evidence）
**都不是模型能力，是领域建模能力**——它们不随供应商更替而失效。
这与 `docs/05_ai/AI_PLATFORM_FORWARD_ARCHITECTURE.md` §0 的立论同源
（未来竞争力是可信自主而非更强；护城河在治理层）。

### 3. 与既有决定的咬合关系（无需返工）

| 定调中的要素 | 既有决定 | 关系 |
|---|---|---|
| Growth Evidence Network / Intervention Evidence Graph | ADR-0010 的 `graph_projection.*` 只读投影 | 同一套底座，投影正是该图的存储 |
| `Family State` 不得成为家庭权威事实 | ADR-0014 的 Draft→Fact 边界三层机制 | 该边界正是防 State 越界的闸 |
| 决策来源可追溯 | `AI_PLATFORM_FORWARD_ARCHITECTURE.md` §2 决策来源图 | 同一对象的两个命名 |
| `Value Architecture` 增量插入既有链 | `docs/05_ai/AI_ARCHITECTURE.md` §3.3 | 该节已裁定「**增量优先于新建对象**」：加字段而非新建 `GrowthProblemModel`。本 ADR 沿用同一纪律 |

### 4. 三处与已生效硬约束的正面冲突（本 ADR 的主要工作）

**冲突一 —— Family Value Score 撞 R9 红线。**
`governance/REPOSITORY_CONSTITUTION.md` R9 原文：
「**AiFamily 不计算、不存储、不暴露家庭总分与家庭排行。**」
其 FELS 继承否定语义表进一步把 `legacy_profile.family_score` 判为
**RETIRE / 永不入 Family / 非 GrowthState (M036)**，`legacy_profile.ranking` 判为
**RETIRE / 无家庭排行 (M035)**。
定调 §17 提出六个 Score（Emotional / Action / Growth / Economic / Trust / Safety），
并说明「不是一个简单的总分，而是多维度」——**但 R9 禁的不是「总分」这个形态，是「给家庭打分」这件事。**
多维度不构成豁免。

**并且这里有一个实测出来的护栏漏洞，必须同批修补。**
`tests/architecture/test_compliance_constraints.py:140-146` 的判据是：

```python
has_subject  = any(token in lowered for token in SUBJECT_TOKENS)   # family/child/parent/...
scoring_hit  = next((t for t in SCORING_TOKENS if t in lowered), None)  # score/rank/grade/...
if has_subject and scoring_hit: violation
```

**必须字段名里同时命中主体词与打分词才会响。** 因此：

- `family_value_score` → 被拒收 ✔
- `emotional_value_score` → **完全通过**（字段名无主体词）✘
- 一个类名为 `FamilyValueScore`、字段为 `emotional` / `action` / `growth` / `economic`
  的模型 → **整个模型一条都不会被咬** ✘

即：**四层价值若按最自然的方式建模，会恰好从现有护栏的漏洞里走过去。**
判据是字段名形状，不是语义上下文。这与 ADR-0014 记录的另一处同类漏洞
（`decide()` 靠一个 `actor_id: str` 骗过人类 actor 启发式）是同一种失效模式。

**冲突二 —— Emotional State / Family State 若持久化为属性，违反三条约束。**
定调 §5 举例 `parent_anxiety = HIGH`、`autonomy = LOW`、`child_engagement = LOW`。
定调 §7 已自行划出「Interaction State ≠ Clinical Diagnosis」并要求高风险入 Human Gate——方向正确。
但架构上还差一层：这些量一旦落库为**持久字段**，就成了人格标签，而：

- R9 的 FELS 表：`legacy_tag.*` → `LEGACY_ANNOTATION` / **非永久人格标签 / 非诊断**；
  `legacy_alert.risk_score` → `SAFETY_SIGNAL_SOURCE` / **非阈值、非自动动作、高风险须 Human Gate**；
  `legacy_assessment_score.score` → `HISTORICAL_EVIDENCE` / **非 GrowthState**。
- ADR-0006 与 `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` §1：
  14 岁以下个人信息**按类别**属敏感信息，每个字段须有明示留存期限与到期处理方式；
  §2：AI 评估输出属自动化决策，须可解释 + 有人工复核/拒绝路径；
  §6：删除权覆盖派生数据。
- 宪章禁止事项：**不做临床诊断。**

**冲突三 —— 七个引擎若变成七个目录，就是把已被点名的反面模式放大七倍。**
`CURRENT_AI_MAP.md` §6 把 `design_copilot` 判为
「**第六类：目录名冒充能力**」（全 `NotImplementedError`、零调用方、零测试），
并引 manifest override 原文「迁移不得被解读为该能力已存在」。
`docs/05_ai/AI_ARCHITECTURE.md` §3.4 的排期表亦已裁定
「P3 多 Agent 协同**不应该先做**……现有代码连单一 Agent 的记忆和人格一致性都没做实」。

## Decision

### 0. 采纳

**Family Growth Intelligence OS 成为 AiFamily 的平台组织架构**，
七层分层与七引擎职责划分即刻生效为**命名法与归位依据**——
它约束「下一步建什么、新代码归到哪一层」，不追认任何既有能力。
`Model Layer` 位于最底层；**Agent 不是平台中心**。

本 ADR **不修改**任何既有 canonical 文档的现状断言。
`CURRENT_AI_MAP.md` / `CURRENT_SYSTEM_BASELINE.md` 的成熟度记录一律不变。

### 1. 裁决冲突一：Value 只有「方向」进家庭侧，「分数」只进平台侧群体度量

分三条，缺一不可：

**(a) 家庭侧永不出现分数。** 任何挂在 Family / Person / Child / Parent / Guardian
主体上的对象，**不得含任何评分、等级、百分位、排名、进度百分比字段**，
无论字段名是否包含主体词。四层价值在家庭侧只能表达为**方向与状态转移**：

```text
Emotional : from_state → to_state   （如 "被作业冲突淹没" → "今晚有一件事能做"）
Action    : next_action_ref          （下一步能做什么，指向一个具体动作）
Growth    : changed_dimension_ref    （什么行为/关系/能力发生了变化，指向证据）
Economic  : 可量化 —— 见 (b)
```

**(b) 四层中只有 Economic Value 可以量化，且量化对象不是家庭而是成本。**
Emotional / Action / Growth 三层**不得有数值**——理由不是技术限制：
一个「情绪价值 78 分」的数字，其本质就是 `legacy_profile.family_score` 换了名字，
而 R9 把它判为 RETIRE。Economic Value 可以量化，因为它度量的是
**时间 / 金钱 / 试错次数**（客观事件计数），不是对家庭的评价。

**(c) `Family Value Realization` 是队列指标，不是家庭属性。**
定调 §22 的北极星（有多少家庭从困扰走到掌控、从掌控走到行动、从行动走到真实改善）
**成立且被采纳**，但它的宿主是 **Product Intelligence 侧的群体统计**，
落 `graph_projection.*` 的聚合视图，**永不写回家庭对象、永不对家庭呈现、永不用于家庭间比较**。
六个 Score（Emotional / Action / Growth / Economic / Trust / Safety）**只在这一层存在**，
且必须是队列级（cohort-level）而非个体级。

> **若 project-owner 要的确实是「给单个家庭打分」，本条不适用**——
> 那需要走 `governance/REPOSITORY_CONSTITUTION.md` 第 3 节的**修宪程序**修改 R9
> （新 ADR + 说明 R9 对应的伤疤为何不再适用 + 同 PR 更新第 2 节执行状态表）。
> **架构师不得在实现 PR 里绕过 R9**，这是本条最重要的一句。

### 2. 裁决冲突二：State 建模为「带来源与有效期的观察」，不是「属性」

`Family State` 与 `Emotional State` **不得**建模为主体上的列
（`family.parent_anxiety` 这种形态被禁止）。统一建模为**追加式观察记录**：

```text
StateObservation
  subject_ref        指向 Person / Family（不含 subject 的评价语义）
  dimension          emotional | relationship | participation | growth | risk | service
  observed_value     枚举或区间，非分数（HIGH/RISING/LOW 这类序数标签允许，数值分数不允许）
  evidence_refs      非空 —— 无证据的观察不得存在
  provenance         必填，复用 backend/packages/contracts/evidence.py 的 Provenance
  observed_at
  expires_at         必填 —— 观察会过期，人格标签不会。这一列是"非永久标签"的执行机制
  retention_policy   必填 —— COMPLIANCE_HARD_CONSTRAINTS §1 的明示留存期限
```

由此，`Family State` 是**从未过期观察推导出的当前视图**，不是存起来的结论。
四条约束因此自动满足：非永久人格标签（`expires_at`）、可解释（`evidence_refs` + `provenance`）、
有留存期（`retention_policy`）、可按主体级联删除（追加式行级记录，符合 ADR-0006 §6）。

**附加红线三条：**
- **`risk` 维度的观察不得触发任何自动动作**（R9：`legacy_alert.risk_score` →
  非阈值、非自动动作）。高风险只能产出 Human Gate 待办。
- **涉未成年人主体的 `emotional` 维度观察，其 `data_class` 必须为 `MINOR_PERSONAL_DATA`**
  （`backend/intelligence/model_gateway/contracts.py:34-51`），不得报为 `OPERATIONAL_TEXT`。
- **`StateObservation` 全部为 AI 产出时，状态是 Draft**，跨越为业务事实须过 ADR-0014 的三层机制。
  State 本身**永不是 Fact**——它是 Perspective。

### 3. 裁决冲突三：七引擎是命名法，目录按需长出

七个引擎**不建目录**。当前真实成熟度如实登记：

| 引擎 | 当前 | 依据 |
|---|---|---|
| Product Intelligence | 有真代码 + 测试 | `backend/domains/product_intelligence`，`MIGRATED_TESTED` |
| Growth Intelligence | 雏形数据结构 | `hypotheses` / `action_candidates` 存在，**缺 `primary_contradiction` 排序层**（`AI_ARCHITECTURE.md` §3.2） |
| Family Context | `ABSENT` | `CURRENT_AI_MAP.md` §5 |
| Emotional Intelligence | `ABSENT` | 本 ADR 之前不存在于任何设计文档 |
| Intervention | `ABSENT` | 同 §5 |
| Service Intelligence | `ABSENT` | `ServiceBlueprintVersion` 无代码 |
| Learning & Value | `ABSENT` | Evaluation 零代码 |

**沿用 `AI_ARCHITECTURE.md` §3.3 已裁定的纪律**：增量优先于新建对象。
若有人提出「应该新建一个 `GrowthProblemModel` / `EmotionalEngine` 类」，
须先回答增量路径为什么不够用。

### 4. 采纳 `Value Architecture` 进领域模型（PR-003），这是本次唯一进代码的一刀

链条变为 `Problem → Hypothesis → Contradiction → Value Architecture → Strategy`。
`Value Architecture` 按 §1 的形态实现：**三层方向 + 一层可量化成本**，无分数。
它作为 `Strategy` 生成的**必填输入**——即产品设计者被迫先回答
「这个家庭该获得什么价值」再决定选什么干预，而不能反过来。
这与 `AI_ARCHITECTURE.md` §3.3 末段对 Service Blueprint 的同类要求一致。

### 5. 本 ADR 强制的护栏补强（不落地则 §1/§2 退化为意图）

**必须与 `Value Architecture` 同 PR 落地**，否则 §1(a) 无执行者：

1. 扩展 `test_no_scoring_or_ranking_fields_anywhere`：
   判据从「字段名同时命中主体词与打分词」扩展为
   「**类名命中主体词 → 该类任何字段不得命中打分词**」，
   闭合 `FamilyValueScore.emotional` 这类走名字漏洞的形态。
2. 新增断言：`StateObservation` 及其后继模型**必须**有 `expires_at`、
   `retention_policy`、`evidence_refs`、`provenance` 四个字段。缺一即失败。
3. 新增断言：`observed_value` 的类型注解**不得**为 `float` / `int` / `Decimal`
   （序数标签允许，数值分数不允许）。

## Alternatives Considered

### A. 走修宪程序修改 R9，允许对单个家庭打分（多维度、不做总分、不做排名）
**支持理由（必须严肃对待）**：不打分会让「越用越准」难以度量；
产品侧无法回答「这个家庭比上个月好了吗」；
定调 §17 的 Evaluation 升级（从 AI 质量到价值质量）在没有任何家庭级量化时确实更难落地；
且 R9 的伤疤来自 FELS 的**总分与排行**，而多维度、不比较、不排名的分数在形态上与它不同。

**否决理由**：
- **伤疤仍然适用。** R9 的 FELS 表把 `legacy_assessment_score.score` 判为
  `HISTORICAL_EVIDENCE / 非 GrowthState`——即源系统的分数不是「总分」也被否决了，
  被否决的是「用分数表示家庭状态」这件事本身。修宪程序要求
  「说明对应的伤疤为何不再适用」，而这条伤疤并未失效。
- **ADR-0005 §3 已有更强的表述**：「AI 原生不是用 AI 算出更精准的分数。
  恰恰因为 AI 能轻易生成一个看起来专业的分数，这条红线才更需要守。」
- **§1(c) 已经满足了度量需求**：队列级指标能回答「多少家庭走到了掌控」，
  这正是定调 §22 要的北极星；它不需要个体分数。
- 修宪不是架构师可单方面发起的动作。**保留为 project-owner 的显式选项，
  但默认不走**——因为不走的方向是可逆的（将来要加分数总能加），
  而走了之后要退回来，库里已经有分数了。

### B. 让 `Family State` 直接存为主体上的列（`family.parent_anxiety` 等）
**支持理由**：查询极简（一次 SELECT 拿到全部状态），无需推导，
性能好，代码量小一个量级；且「当前状态」在概念上确实像一个属性。

**否决理由**：这是 FELS 的 `legacy_profile` 形态原样重现，被 R9 判为 RETIRE。
更实质的是**它无法满足法定义务**：一个列没有 `expires_at`，
所以无法表达「非永久标签」；没有 `evidence_refs`，所以无法满足 PIPL 第 24 条的可解释性；
被覆盖写后**没有历史**，所以无法支撑定调 §16 的 Evidence 与 §22 的价值实现追踪
——覆盖写会把「这个家庭从困扰走到掌控」这条轨迹本身擦掉。
**追加式记录不是为了合规才选的，它同时是价值实现可被证明的前提。**

### C. 七个引擎立即建成七个目录 + 接口占位，便于并行开工
**支持理由**：七个团队/会话可并行；目录结构先定下来避免将来搬迁；
接口占位能让依赖方先写调用代码。

**否决理由**：`CURRENT_AI_MAP.md` §6 已把这个模式命名为
「第六类：目录名冒充能力」，`design_copilot` 是活标本（全 `NotImplementedError`、
零调用方、零测试，且 manifest override 明写「迁移不得被解读为该能力已存在」）。
七个空目录会让 `CURRENT_AI_MAP.md` 的成熟度表出现七行 `PLANNED`，
而 R4 明确「代码行数不是成熟度」。**目录是零成本创建、高成本撤销的**——
撤销要动 registry、manifest、文档三处。

### D. 只采纳分层图，暂不裁决三处冲突，等实现时再说
**支持理由**：现在裁决基于尚不存在的代码，判断可能过早；
实现者遇到真实约束时的裁决质量更高。

**否决理由**：**冲突一有一个已实测的护栏漏洞。** 若不在采纳的同一份 ADR 里补掉，
第一个实现 `Value Architecture` 的人会写出 `emotional_value_score`，
测试全绿，然后它就成了既成事实——而 R9 是本仓库最重的红线。
「等实现时再说」在有已知漏洞的情况下等价于**默认放行**。

## Consequences

### 正面
- 平台组织原则从「AI 能力清单」变为「家庭价值创造链」，
  且消解了「自称 AI 原生而 AI 层最空」的张力。
- `Model` 在最底层这一判断，使模型供应商更替成为路由问题而非架构问题，
  缓解 ADR-0005「需要接受的风险」中记录的供应链集中风险。
- 补掉了 R9 护栏的一个实测漏洞（类名维度未被检查）——
  **这个收益独立于本次定调是否落地，它现在就存在。**
- `StateObservation` 的四个必填字段让合规从「事后补」变成「不填就构造失败」。
- 四层价值有了可实现的形态（三层方向 + 一层成本），而非停留理念。

### 负面 / 代价
- 追加式 `StateObservation` 的查询成本显著高于列存储，
  「当前状态」每次需要按 `expires_at` 过滤 + 按维度取最新。将来可能需要投影层缓存
  （落 ADR-0010 的 `graph_projection.*`，不新建机制）。
- 「三层价值不得有数值」会让部分产品度量诉求无法直接满足，
  需要通过队列指标间接回答，产品侧要接受这个绕行。
- 三条新护栏断言会产生假阳性（例如一个合法的 `progress_pct` 用在服务任务而非家庭上）。
  豁免必须像 `FIELD_TOKEN_EXEMPTIONS` 那样**写明理由**，不允许裸豁免。
- 七引擎命名法与现有 `backend/domains/*` 的域划分是两套坐标系，
  需要一张映射表（归 §Enforcement 的补齐路径），否则新代码归位会有歧义。

### 需要接受的风险
- **最大风险：本 ADR 描述的七层里有五层完全没有代码。** 一份完整的分层图
  极易被误读为「平台已具备这些层」。缓释：§0 明确不追认任何既有能力，
  §3 给出逐引擎真实成熟度，且 `CURRENT_AI_MAP.md` 不因本 ADR 改动一个字。
  **有 ADR 不等于有能力**——这是本仓库反复被记录的失效模式。
- Emotional Intelligence 是本 ADR 引入的**全新能力方向**，此前不在任何设计文档中。
  它涉及未成年人情绪推断，是全平台合规风险最高的单点。
  §2 的三条附加红线是最低门槛，不是充分条件；正式开工前应单独出 ADR
  并考虑重跑一次针对性的合规 deep-research。
- 「序数标签允许、数值分数不允许」的界线存在被规避的空间：
  一个把 `HIGH/MEDIUM/LOW` 映射为 3/2/1 的下游计算，在字段层是合规的。
  这条只能靠 review（见 Enforcement）。

- **★ 最大的未验证风险：领域模型本身没有外部证据基础（本条为 2026-08-29 补记，
  是本 ADR 起草时的漏记）。**

  本 ADR 的中心命题是「护城河在领域建模，不在模型能力」，并据此把
  `Problem → Hypothesis → Contradiction → Value Architecture → Strategy`
  确立为主链条。但这条链的来源是**内部设计文档**——
  `docs/05_ai/AI_ARCHITECTURE.md` §2/§3 的 GROUNDING 字段明确写它来自战略白皮书
  Slide 17/19 与 V2 战略第 8 节。**没有任何一处引用外部证据证明
  「识别主要矛盾」真的能预测干预效果。**

  为什么这条比本 ADR 已列的其它风险更严重：**它无法靠工程手段发现。**
  如果「主要矛盾」是一个有吸引力的隐喻而非真实的预测因子，那么
  域边界、四种通信契约、Draft→Fact 三层机制、R9 类名护栏、只读投影、八层组织架构
  ——全部会继续正常工作，所有测试继续全绿，而底下的领域模型是空的。
  **精密的工程护栏无法检验它所保护的理论是否成立。**

  同一风险的三个具体子项，均未经外部核验：
  1. **「主要矛盾」应否作为一等实体？** `AI_ARCHITECTURE.md` §3.3 已裁定「增量优先于新建对象」
     （加 `primary_contradiction_ref` 而非新建 `GrowthProblemModel`）——该裁决在**工程成本**上正确，
     但它没有回答这个概念本身是否有效。若临床判断的机制识别一致性低，
     则「AI 识别主要矛盾」的可靠性上限就被那个一致性钉住了。
  2. **21 天周期**。「21 天形成习惯」的常见来源是 Maltz 的说法而非实证；
     已有的 parenting program（Triple P / Incredible Years / PCIT / PMTO）标准课时远高于此。
  3. **家长自评是当前唯一数据源。** 家长报告儿童行为的偏差在文献中是已知问题
     （depression-distortion、shared method variance）。若学习闭环的唯一信号来自家长自评，
     则「越用越准」可能测到的是家长期望的变化而非儿童行为的变化。

  **缓释（已启动，非已解决）**：2026-08-29 已启动一份针对性 deep-research，
  专门检验这四点，且要求「对该领域模型不利或与之冲突的证据」一节**不得为空**。
  结论落 `docs/13_research/`（须标 `RESEARCH_ONLY`），**若结论推翻上述任一子项，
  应出新 ADR 修正本 ADR，而不是静默调整实现**。

  **在该研究返回之前，PR-003（T-18）不应把 `primary_contradiction` 建成一等实体**——
  按 §Decision 3 已沿用的「增量优先于新建对象」纪律，先做置信度排序字段，
  这恰好也是万一该概念被推翻时代价最小的形态。

## Enforcement

| 裁决 | 机制 | 状态 |
|---|---|---|
| §1(a) 家庭侧无分数 | 扩展 `test_no_scoring_or_ranking_fields_anywhere` 至**类名维度** | **未落地**，本 ADR §5.1 强制要求与 `Value Architecture` 同 PR |
| §1(b) 仅 Economic 可量化 | §5.3 的 `observed_value` 类型注解检查可覆盖 State 侧；`Value Architecture` 侧需同类断言 | **未落地** |
| §1(c) Score 只在队列层 | **不可机械检验**——「这个统计是队列级还是个体级」是语义判断。靠 review + 本 ADR |
| §2 State 为观察非属性 | §5.2 的四必填字段断言 | **未落地** |
| §2 risk 不触发自动动作 | 可检验：扫 `risk` 维度相关代码路径是否出现自动状态迁移 | **未设计**，需与 Intervention Engine 同批 |
| §2 未成年人 `data_class` | **不可机械检验**——ADR-0014 §Enforcement 已记录同一条（申报正确性无法查） |
| §3 七引擎不建目录 | 可检验：`backend/intelligence/` 下每个子目录必须有 manifest 条目 + 非空测试路径。**现有 `test_migration_manifest.py` 已部分覆盖**（R3：含文件的目录须被 manifest 覆盖） | 部分有效 |
| §4 `Value Architecture` 为 `Strategy` 必填输入 | 可检验：`Strategy` 构造函数无该参数默认值（照 `Provenance.level` 无默认值的既有手法，`evidence.py:50`） | **未落地** |

**补齐路径**：本 ADR 产出两张任务卡写入 `docs/11_delivery/TASK_BACKLOG.md`：

- **R9 打分护栏的类名维度**：**已由本 ADR 作者同批落地**，不再是待办。
  `tests/architecture/test_r9_value_layer_boundary.py` 新增两条判据（类名自身、类名×字段名）
  + 一条防词表漂移断言，已验证会咬人（5 用例：2 植入形态被咬、2 对照保持绿、1 豁免保持绿）。
  该漏洞独立于本次定调、在定调之前就存在。
- **T-18**：`Value Architecture` 领域模型 + `StateObservation` 模型 + §5 剩余两条断言
  （四必填字段反射断言、`observed_value` 类型注解检查）+ `Strategy` 构造器无默认值。属 PR-003 范围。

（该卡原取号 T-14，与并发会话 commit 消息中已使用的编号撞号，重编为 T-18；
台账下一个可用编号 = T-20。）

**七引擎 ↔ `backend/domains/*` 的映射表**尚不存在，
应作为 `docs/04_domains/`（该目录当前全空）的第一份文档产出。

## References

- project-owner 定调原文（2026-08-29 会话），本 ADR §Context 1 为其结构化转述
- `governance/REPOSITORY_CONSTITUTION.md` R9（含 FELS 继承否定语义表：`family_score` / `ranking`
  → RETIRE；`legacy_tag.*` → 非永久人格标签；`legacy_alert.risk_score` → 非阈值非自动动作；
  `legacy_assessment_score.score` → 非 GrowthState）、R4、第 3 节修宪程序
- `tests/architecture/test_compliance_constraints.py:71-91, 115-146`（护栏漏洞的精确位置与判据）
- `docs/00_system/CURRENT_AI_MAP.md` §5、§6（第六类：目录名冒充能力）、§7（AI 层最空的张力）
- `docs/05_ai/AI_ARCHITECTURE.md` §3.2（缺 `primary_contradiction` 排序层）、
  §3.3（**增量优先于新建对象**）、§3.4（P3 多 Agent 不应先做）
- `docs/05_ai/AI_PLATFORM_FORWARD_ARCHITECTURE.md` §0（护城河在治理层的立论）、§3（记忆三态）
- `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` §1 / §2 / §6
- `backend/packages/contracts/evidence.py:44-51`（`Provenance` 无默认值的手法，§4 沿用）
- `backend/intelligence/model_gateway/contracts.py:34-51`（`DataClass` 词表）
- `backend/domains/loyalty_points/`（"能力的缺席即执行机制"的既有先例：无 `balance` 字段、
  无 `rank_families` 方法）
- ADR-0005 §3（AI 原生不是算更准的分数）、ADR-0006、ADR-0010（投影层）、ADR-0014（Draft→Fact 边界）
