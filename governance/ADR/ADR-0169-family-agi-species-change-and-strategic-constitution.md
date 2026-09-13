# ADR-0169: "物种变化"定案——AiFamily 一开始就是 Family AGI Platform，教育只是第一阶段产品验证

- **Status**: Accepted
- **Date**: 2026-09-13
- **Deciders**: project-owner
- **Supersedes**: null（扩展 ADR-0168，不推翻。ADR-0168 已冻结"边界=Child+Family+
  Society、教育=First Wedge"；本 ADR 在此基础上补三件 ADR-0168 没讲透的事：
  ① 战略/技术底座/第一阶段产品范围必须彻底分离这一元原则、② Family 一级对象
  ×Person 二级对象、FamilyNeed 提升为首要业务对象等具体本体决定、③ Vertical
  Pack 机制——用于防止"战略变宽"被误读成"现在就要把所有垂类都建出来"）
- **Superseded By**: null

## Context

ADR-0168 已经把系统边界从 `Child+Education` 纠正为 `Child+Family+Society`。项目
负责人本次会话（2026-09-13）进一步指出：这次纠正的本质不是"边界扩大"这么简单，
而是一次**物种变化**——

> 不是从家庭教育平台升级成 AGI，而是一开始就按照 Family AGI Platform 来建设，
> 只是用孩子成长完成第一阶段产品验证。

这句话解决的问题是：如果只停在 ADR-0168 的"边界更宽"，研发团队仍然可能把
"边界变宽"错误执行成"现在就要多做几个垂类"（养老/保险/医疗数据库），或者反过来
"边界写在文档里，代码架构继续按教育平台的方式长"（`course`/`teacher` 域继续直接
耦合 Family 核心 schema）。这正是 ADR-0158 已经点名的"AGENT-EVIDENCE"姊妹纪律
——叙述纠正了，如果底层本体和执行纪律不同步跟进，纠正就只停留在文档层，不构成
真正的架构决定。

项目负责人本次提供的材料给出了具体、可执行的本体设计（Family 一级/Person 二级、
FamilyNeed 优先于 Course/Assessment 成为首要 ID、Family World Model 改名为
Family World State 并要求区分 FACT/SIGNAL/SELF_REPORT/HYPOTHESIS 等信息类型、
四 Brain 模型新增 Action Brain、Vertical Pack 机制、R2-R10 蓝图重定义），以及
同样重要的、明确的"现在不做什么"清单——这份清单本身是防止本次战略扩大导致
研发范围失控的关键纪律，必须与本体决定同等地写入本 ADR，不能只记录"要建什么"。

## Decision

**冻结 `AIFAMILY_STRATEGIC_CONSTITUTION_V1`（全文见
`docs/00_system/AIFAMILY_STRATEGIC_CONSTITUTION_V1.md`，本 ADR 是其唯一治理来源）
中以下十一项为架构决定：**

1. **三个概念必须永久分离，不得混用**：战略边界（可以很大）/ 技术底座（必须
   通用）/ 第一阶段产品范围（必须足够窄）。任何后续文档、开发指令，在提出"要
   建 X"时必须先声明 X 属于哪一层，混用会重犯"骨架冒充能力"（R14）或"边界写
   一套、代码长另一套"两种反面案例之一。

2. **六条不可破坏原则**（详见 Constitution 文档 §1 表格），要点：
   基本服务单位=Family 非 Student/User；核心业务对象=FamilyNeed 非
   Course/Product；长期智能对象=FamilyWorldState 非 User Profile；解决问题
   方式=AI+Family+Human+Society Resources；价值评价方式=Outcome 非点击/消费/
   完课率；第一阶段垂直场景=Child Growth/Education 是 First Wedge 非 Platform
   Boundary。

3. **Family 是一级对象，Person 是二级对象**：家庭不是多个个人账户的简单相加，
   系统必须能表达家庭内部的共同目标/不同目标/利益冲突/认知差异/隐私边界/监护
   关系/决策权差异——这是与通用 AI 助手（回答"我需要什么"）的本质区别（AiFamily
   回答"我们这个家庭真正需要什么"）。

4. **Family World Model 改名为 Family World State，且信息类型必须显式区分**：
   `FACT / SIGNAL / SELF_REPORT / OTHER_REPORT / PREFERENCE / GOAL / CONSTRAINT
   / RISK / HYPOTHESIS / UNKNOWN / INFERENCE / PROFESSIONAL_OPINION`。**禁止
   AI 推断被静默升级为家庭事实**——这不是新规则，是 `REPOSITORY_CONSTITUTION.md`
   R9（AI 输出不直写 canonical 事实）在信息类型层面的具体化，本 ADR 要求任何
   持久化的家庭相关记录必须携带上述类型标签之一，否则视为违反 R9。

5. **FamilyNeed 提升为平台第一业务对象**，且 **Expression ≠ Need** 必须作为
   显式架构纪律：用户的原始表达（"给孩子找英语老师"）不能直接映射为可购买的
   Resource，必须先经过 Need 判定链路（评估紧迫度/严重度/证据/假设/未知/受
   影响成员/期望结果）。这是 R9 在业务流程层的推论：跳过 Need 判定直接映射为
   商品，等价于把一个未经验证的表达当成了家庭事实。

6. **四 Brain 模型**（在 ADR-0168 §8 三 Brain 基础上新增 Action Brain）：
   Family Brain（我们正在面对什么）→ Action Brain（下一步该怎么办：Decide/
   Plan/Coordinate）→ 并行调用 AI 与 Society Brain（谁能帮助，长期升级为
   Resource Intelligence Network）→ Action → Outcome → Evolution Brain（哪些
   方法真正有效）。Action Brain 存在的理由：防止系统停留在"很会理解、很会
   建议，但事情没有真正发生"。

7. **资源统一抽象为 Capability，Provider 与排序目标函数解耦商业利益**：
   `Resource --provides--> Capability --applies_to--> Need --produces--> Outcome`。
   资源排序目标函数方向性冻结为
   `Expected Outcome × Family Fit × Evidence Quality × Trust × Safety ×
   Availability × Preference Fit ÷ Cost/Burden`；**商业利益（佣金/广告位/
   出价）只能作为独立变量存在，不得作为排序目标函数的输入项**——这是防止
   Society Brain 退化为"家庭版大众点评/电商/广告平台"的具体判据，任何未来的
   排序实现如果把 GMV/佣金率直接加权进主排序公式，视为违反本条。

8. **Outcome Contract 是 Plan 执行前的强制要素，Outcome 类型必须多元化**：
   `Self-reported / Observed / Behavioral / Assessment / Professional /
   System Inferred / Long-term`，且必须能表达 `No Change / Negative Outcome
   / Unexpected Outcome`——Evolution Brain 不能只学习成功案例。

9. **Family Memory 分区是基础架构，不是后加的隐私功能**：`Private Member
   Memory / Shared Family Memory / Guardian-visible Memory / Professional
   Shared Context / System Operational Memory / Derived Intelligence`，每类
   信息必须携带 `owner/visibility/consent/purpose/source/confidence/
   retention`。**禁止把某一家庭成员私下表达的内容默认同步给其他成员**——这是
   R6（未成年人数据合规）与 R9 在家庭多主体场景下的具体化，不是新增合规负担。

10. **Family Principal Agent（"法咪莉校长"技术定位）必须具备 Know/Don't
    Know/Escalate 能力**，能明确输出以下六类判断之一而不伪装全知：`I know /
    I have a hypothesis / I don't know yet, need more info / AI should not
    decide this / A professional should evaluate this / The family must
    decide this`。

11. **Vertical Pack 机制**：Family Intelligence Core（Family/Members/
    Relationships/Consent/Family World State/Needs/Goals/Decisions/Plans/
    Resources/Actions/Outcomes/Evidence/Unknowns/Risks）与垂直业务
    （Child Growth/Education/Relationship/Health/Career/Elder Care...）之间
    必须有清晰边界：Vertical Pack 只声明 Domain Ontology/Need Types/Evidence
    Types/Risk Rules/Capability Types/Outcome Metrics/Professional
    Boundaries/Workflows/UI Components，**不得要求修改 Core 的主链 schema**
    （与 ADR-0168 第 5 条判据一致，本条把它从"教育垂类"泛化为"任何垂类"）。
    第一阶段只交付 **Child Growth Vertical Pack V1**，其余 Pack 只作为架构
    预留，不在当前阶段建表。

**同时冻结以下"当前明确不做"清单，与上述本体决定具有同等约束力**（详见
Constitution 文档 §7）：不建"大而全家庭超级App"；不一次性建完 Family World
State 全部字段；不做医疗诊断；不做家庭理财产品；不建养老商城；不建复杂社会
资源市场（当前只需 Distribution 雏形，见既有 `family-allocation-platform-
mechanisms` 记忆）；不给每个垂直业务单独开发 Agent；不把课程/教师/专家写入
平台 Core（已由 ADR-0168 第 5 条冻结，本条重申）；不把所有聊天自动写入永久
Family Memory；不让 Agent 无审计地修改 Family World State。

**北极星重新定义**：不是"服务多少家庭"或"日活"，而是 Family Outcome——是否
更准确理解家庭、是否发现真正问题、是否减少无效行动、是否促成正确资源介入、
是否产生实际改善、**家庭是否越来越有能力自己解决问题**（最后一条尤其重要：
好的 Family AGI 不应该让家庭越来越依赖 AI，而应该让家庭本身变得更有能力）。

## Alternatives Considered

**A. 只把这些内容作为 ADR-0168 的补充段落追加，不单独开 ADR。**
支持理由：避免 ADR 数量膨胀，且内容与 ADR-0168 高度相关。
否决理由：ADR-0168 的 Decision 段已经 Accepted，`README.md` 第 4 条写作纪律明确
"不得原地重写已 Accepted 的 ADR 的 Decision"。本次新增内容（Family/Person
分级、FamilyNeed 优先级、Vertical Pack 机制、四 Brain、"现在不做"清单）体量和
重要性都达到独立 ADR 的门槛，且 README "何时必须写 ADR"第 1/3/4 条（边界/数据
所有权/AI 能力边界）均被触及，理应独立成文，便于未来单独引用和 Supersede。

**B. 直接把 `docs/01_strategy/FAMILY_AGI_PLATFORM_BLUEPRINT.md` 整篇重写为
`AIFAMILY_MASTER_BLUEPRINT_V2`，一次性完成项目负责人提出的"下一轮真正应该重写
的"任务。**
支持理由：一次做完，避免文档体系在过渡期内出现"宪法已冻结、蓝图还是旧叙述"的
不一致。
否决理由：项目负责人本次材料第十六条明确要求"这次战略扩大绝不能导致研发范围
爆炸"，且 Master Blueprint V2 涉及把测评/21天营/教师/专家/直播/法咪莉校长
全部重新挂载到 Child Growth Vertical Pack——这是一项体量与本次 ADR 相当甚至
更大的独立工程，需要逐个现有域核实当前实现是否真的耦合了 Core schema（不能
凭本 ADR 的判据"假设"违反，必须逐一 grep/核实），仓促合并到本次会话交付,
反而会违反 R14"如实报告未完成项"——本 ADR 只冻结决定与判据，Master Blueprint
V2 的编写作为独立、有 owner、有验收条件的后续任务（见 Enforcement 段）。

**C. 不新增 Constitution 文档，把全部内容直接写进 `SYSTEM_MANIFEST.md`。**
支持理由：避免文档数量增加，读者只需读一份文件。
否决理由：`SYSTEM_MANIFEST.md` 自身定位是"身份与边界导航，变更频率应当很低"
（§9），本次内容体量（六原则+四Brain+本体决定+R2-R10+Vertical Pack+不做清单）
远超导航文档应有的篇幅，会违反其自身"禁止在本文件堆积架构细节，它是导航不是
百科"的维护规则。参照 `CURRENT_SYSTEM_BASELINE.md`/`CURRENT_AI_MAP.md`等既有
模式，独立 L0 文档 + SYSTEM_MANIFEST 指针引用是本仓库既定做法。

## Consequences

### 正面
- 给"战略边界宽、产品边界窄"提供了可执行判据（Vertical Pack 不得修改 Core
  schema；商业利益不得进入排序目标函数；AI 推断不得静默升级为事实），不再是
  只能靠人工判断的原则宣言。
- Family/Person 分级、FamilyNeed 优先级等本体决定为后续 `governance/
  DOMAIN_REGISTRY.yaml` 的 Domain 边界判断提供了上位依据，减少未来"这个能力该
  归哪个域"的反复讨论。
- 明确的"现在不做"清单本身是对项目负责人本次战略扩大最大风险（范围失控）的
  直接对冲。

### 负面 / 代价
- 现有 `backend/domains/course`、`backend/domains/service`（教师/专家相关）
  等域是否已经耦合了 Family/Need/Goal/Plan 的核心 schema，本 ADR **未逐一核实
  代码**，只冻结判据。如果核实后发现耦合，需要单独的 REFACTOR 决定（且按
  ADR-0168 Alternatives B 的否决理由，属于独立工程，不在本 ADR 范围内）。
- `docs/01_strategy/FAMILY_AGI_PLATFORM_BLUEPRINT.md` 与新 Constitution 文档
  会短期内并存（前者是 draft 蓝图记录长期演化推理过程，后者是本 ADR 授权的
  canonical 摘要），读者需要通过 front matter 的 `authorized-by-adr` 字段判断
  谁是权威——已有先例（ADR-0168 之后蓝图文档已经用同样方式处理）。

### 需要接受的风险
- "四 Brain/Vertical Pack/FamilyNeed 优先级"等决定目前只是文档层判据，没有对应
  架构测试强制执行（见 Enforcement 段）。在测试补齐前，违反本 ADR 的代码变更
  不会被 CI 自动拦截，需要 code review 人工把关。

## Enforcement

- **当前仅为文档层决定**，与 ADR-0168 同样的诚实标注：没有强制机制的地方不
  假装有。
- 本会话已执行：新建 `docs/00_system/AIFAMILY_STRATEGIC_CONSTITUTION_V1.md`
  （canonical，见该文件 front matter `authorized-by-adr: ADR-0169`），
  `SYSTEM_MANIFEST.md` §5.1 / §2 接入指针引用。
- 后续执行路径（不在本 ADR 授权范围内立即做，留给总架构师单独排期，且必须先
  逐个现有域核实真实耦合状况再动代码，不得凭本 ADR 判据直接假设违规）：
  1. `tests/architecture/` 新增判据测试：Vertical Pack 类域（`course`等）
     不得直接 import Family/Need/Goal/Plan 域的具体 ORM 实现，只能通过
     Capability/Resource 抽象接口——把本 ADR 第 11 条从意图变成执行机制
     （与 ADR-0168 Enforcement 第 1 条是同一件事，本 ADR 重申范围从"教育"
     泛化为"任何 Vertical Pack"）。
  2. 新增判据测试或代码 review checklist：任何写入家庭相关持久化记录的
     代码路径必须携带本 ADR 第 4 条枚举的信息类型标签之一。
  3. 排序/推荐相关代码（如存在）核实是否已经把商业变量混入主排序公式，
     核实结果记录为独立发现，不在本 ADR 内假定"已经违反"或"从未违反"。
  4. 按项目负责人本次材料第十四节的 R2–R10 表，评估是否需要新 ADR 正式
     Supersede 现有 Wave/Sprint 编号体系（`docs/11_delivery/
     CURRENT_PROGRAM_PLAN.md` 的 P0-P6），本 ADR 不越权直接改写该文件的
     执行排期——排期变更需要总架构师和项目负责人另行确认，避免本 ADR 在
     一次会话内同时决定"定位"和"排期"两件不同量级的事。
  5. `AIFAMILY_MASTER_BLUEPRINT_V2`（重写 `FAMILY_AGI_PLATFORM_BLUEPRINT.md`
     全文、把测评/21天营/教师/专家/直播/法咪莉校长重新挂载到 Child Growth
     Vertical Pack）作为独立任务排期，不在本次会话交付。

## References

- `governance/ADR/ADR-0168-child-family-society-boundary.md`（本 ADR 扩展的
  前置决定）
- `docs/00_system/AIFAMILY_STRATEGIC_CONSTITUTION_V1.md`（本 ADR 授权的
  canonical 摘要文档）
- `docs/01_strategy/FAMILY_AGI_PLATFORM_BLUEPRINT.md`（长期演化推理过程，
  draft，非本 ADR 直接修改对象）
- `governance/REPOSITORY_CONSTITUTION.md` R6/R9（未成年人数据合规、AI 输出
  不直写事实——本 ADR 第 4/5/9 条是这两条规则在家庭多主体场景下的具体化）
- `governance/ADR/ADR-0158-agi-native-family-growth-platform.md`
  （"AGENT-EVIDENCE"纪律）
- `docs/11_delivery/CURRENT_PROGRAM_PLAN.md`（现有 Wave/P0-P6 排期，本 ADR
  不越权改写，留待后续单独核对是否需要 Supersede）
