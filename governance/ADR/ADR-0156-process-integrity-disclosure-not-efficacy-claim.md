---
id: ADR-0156
title: 过程确定性证据可对外披露；结果因果声明永久禁止
status: accepted
date: 2026-09-07
decision_owner: project-owner
supersedes: null
superseded_by: null
---

# ADR-0156：过程确定性证据可对外披露；结果因果声明永久禁止

## 背景

`docs/13_research/market/FIVE_COMPANY_BENCHMARK_STATUS_V1.md` §3.2 对标
Maven Clinic 时留了一个悬而未决的产品决策：Maven 的 Clinical Research
Institute 把汇总后的服务贡献证据做成可复现研究公开发表（例如"doula 支持
降低 20% 剖腹产率"），方法论开放给行业复用。该文档当时的结论是"这是否
值得做，取决于产品战略是否需要对外证明疗效，不是当前技术债，是产品决策，
先不建议动代码"。

project-owner 现已就"品牌是否需要对外科学背书"这一前提拍板：**需要**。
本 ADR 把这个产品决策落地为架构边界，且必须先解决一个真实冲突：Maven
发表的是**结果因果声明**（"支持降低了剖腹产率"），这类表述直接撞
`governance/REPOSITORY_CONSTITUTION.md` R9（AI 输出不得自动成为事实）
延伸出的平台级红线——不做家庭总分、家庭排名、临床诊断、疗效保证、疗效
承诺。这条红线贯穿全架构（`ADR-0005` §3、`ADR-0029` "不采用的方案"第 4
条、`ADR-0056` 决策第 3 条、`docs/02_business/BUSINESS_ARCHITECTURE.md`、
`docs/05_ai/AI_TECHNICAL_ARCHITECTURE_DEEP_DESIGN.md` 等二十余处一致
措辞），不是某个模块的局部约束，不能为了对外发表而开一个例外口子。

现有证据链已经具备一部分 Maven 式"可复现证据"的结构，但性质不同：

- `backend/domains/service/fgcn/quality_contribution_application.py` 的
  `ServiceContribution` 只有人工审核通过（`quality_state == VERIFIED`）
  才产生，且模块 docstring 显式声明"不调用 AI、不计算家庭价值、不产生
  资金/结算行"——这本身已经比 Maven 更保守。
- `backend/domains/product_intelligence/application/family_experience_signal.py`
  的 `ComponentExperienceSummary` 已有 `MIN_SAMPLE_SIZE_FOR_CONFIDENT_RATE
  = 5` 门槛，防止小样本伪共识——这条统计纪律与学术发表要求最小样本量是
  同一类约束，可以直接复用其思路，但发表级门槛需要远高于这个家长可见
  confidence 门槛。
- 当前真实交付量处于第一条端到端闭环刚打通的阶段
  （见 `docs/13_research/market/FIVE_COMPANY_BENCHMARK_STATUS_V1.md` 引用
  的 `aifamily-first-real-closed-loop` 里程碑），样本量远不足以支撑任何
  对外发表——这一点不因本 ADR 而改变，本 ADR 解决的是"允许不允许、允许
  什么"，不是"现在就能发表"。

## 决策

1. **区分"过程确定性证据"与"结果因果声明"，只允许前者对外披露。**
   过程确定性证据指服务交付链路本身的结构化事实：准入标准、匹配-履约
   时延、Human Gate 拒绝率、`TaskQualityReview` 通过率、样本量分布。
   结果因果声明指任何形如"X 改善/提升/降低了 Y 结果"的表述——永久禁止，
   不因样本量增长、不因外部审核、不因免责声明而解除。

2. **对外材料的数据来源被冻结为现有证据链，禁止为发表新建数据结构或
   新增采集字段。** 只能读取 `ServiceContribution` / `TaskQualityReview`
   / `ComponentExperienceSummary` 等既有、已经过独立人工动作产生的事实
   投影，不允许引入新的"为了发表而设计"的评分或标签字段——这正是
   `ADR-0005` 判据 5 警惕的"AI 权限边界靠自觉"重演在"证据边界靠自觉"上。

3. **发表门槛与家长可见 confidence 门槛分离，且必须显著更高。**
   `MIN_SAMPLE_SIZE_FOR_CONFIDENT_RATE = 5` 是面向单个家长"这条建议是否
   够可信"的门槛，不是面向公众/媒体/监管方的发表门槛。发表级门槛的具体
   数值本 ADR 不预先设定（当前样本量为零，设定具体数字是伪精确），留待
   有真实数据后由产品负责人与统计/合规共同定，但必须满足：足以支撑一个
   独立第三方复现同样的过程指标计算,而不仅是复述平台自己的汇总数字。

4. **任何对外发表材料上线前必须联合签字，不能由单一职能自行发布。**
   至少需要产品负责人 + 合规/法务 + 本 ADR 或其后续 ADR 的 owner 三方
   书面确认该材料不含结果因果表述。这条纪律借用 `ADR-0029` "验收与回滚"
   段"需产品、服务、教研、AI 治理和合规负责人联合评审"的既有先例，不是
   新发明的流程。

5. **触发条件是数据规模,不是时间。** 本 ADR 现在生效的是"允许做什么、
   禁止做什么"这条边界,不是"现在就可以发表"的批准。实际发表动作需要
   另开一次产品决策(不要求另开 ADR,除非发表机制本身需要新的架构原语)，
   确认真实样本量已达到第 3 条要求的门槛。

### 后续变更：project-owner override（2026-09-07，必须记录）

project-owner 复核后指出第 3、4 条把一件还没有任何真实数据支撑的事
预先设计成一套重流程（留白门槛 + 三方联合签字），这是过度设计，不是
审慎——**先简化决策第 3、4 条**：

- **第 3 条改为**：发表级门槛不预先设计任何机制或占位字段，留到有真实
  数据时按当时的实际样本量、由当时的产品负责人直接判断是否足以支撑
  发表，不引入"发表门槛"这个概念本身。
- **第 4 条改为**：对外材料上线前由产品负责人确认不含结果因果表述即可，
  不要求另外的三方联合书面签字流程——第 1 条"过程证据 vs 结果因果声明"
  的边界本身足够清晰，不需要额外的组织流程来防守一条概念上已经讲清楚
  的边界。

**这个 override 是决定的简化，不是本 ADR 核心主张的失效**：第 1、2 条
（过程证据可披露、结果因果永久禁止、不为发表新建数据结构）完整保留，
这是唯一真正做不到让步的红线；被砍掉的只是"如何执行这条边界"的流程
设计，那部分本来就不该在数据都不存在的阶段预先定案。

## 结果

### 正面

- 把一个悬而未决三周的产品决策转成可检验的架构边界，下次有人翻到
  `FIVE_COMPANY_BENCHMARK_STATUS_V1.md` §3.2 不会重新纠结一遍"能不能
  做"，只需要检查"数据是否够了"。
- 明确区分"过程"与"结果"两个维度，让 Maven 式对外证据链的价值（透明度、
  第三方可复现）在不违反 R9 的前提下可以被吸收，而不是简单地"因为
  Maven 讲疗效我们不能碰这整套机制"。
- 复用既有的 `ServiceContribution`/`ComponentExperienceSummary`/最小
  样本量纪律，不新增任何代码或数据结构，符合"这不是技术债，只是产品
  决策"的原始判断。

### 代价 / 需要接受的风险

- "过程确定性证据"与"结果因果声明"的边界在文字表述上容易被营销/公关
  语言无意中越界（例如"审核通过率 98%"很容易被下一句改写成"98% 的家庭
  获得了改善"）。简化后（见后续 override）没有额外的组织流程防守这条
  边界，唯一防线是发表前产品负责人自行判断，这是已知且接受的风险，
  不引入更重的流程来弥补。
- 发表门槛/时机不预先设计任何机制，意味着这条决策目前不可被自动化
  测试验证，Enforcement 段如实记录为"当前仅为边界声明"。

## 不采用的方案

- **不采用"完全照搬 Maven，允许结果因果声明"**：直接撞 R9 及其在
  `ADR-0005`/`ADR-0029`/`ADR-0056` 的一致延伸，且家庭教育场景对未成年人
  下"疗效"结论的伤害远高于一般消费产品，没有讨论空间。
- **不采用"完全不做,维持原状悬置"**：project-owner 已明确"品牌需要
  科学背书"这一前提成立,继续悬置等于没有回应这个业务需求,且会让下一个
  翻到 `FIVE_COMPANY_BENCHMARK_STATUS_V1.md` 的人重新纠结一遍同一个问题。
- **不采用"现在就设定具体发表样本量门槛（如 N=500）"**：当前真实交付
  样本量为零,任何具体数字都是伪精确,反而可能被误当作"已经有统计学依据"
  的既成事实。留白比编造数字更诚实。
- **不采用"为发表新建一套独立的疗效评估数据管道"**：这正是本 ADR 决策
  第 2 条否决的方向,会制造第二套业务真相,与 `ADR-0029` "不把知识快照、
  Prompt 或模型响应当作产品事实"的既有纪律冲突。

## 验收与回滚

本 ADR 进入 accepted 前需 project-owner 确认（已确认，见背景段"拍板"
记录）。第 3、4 条按上述 override 简化后，实际发表材料的产出只需产品
负责人在发布前确认不含结果因果表述，不要求额外的联合签字流程；若发表
材料被发现包含结果因果表述，产品负责人负责撤回该材料。回滚本 ADR 第
1、2 条核心主张（即重新允许结果因果声明）需要新的 ADR，不能通过修改
本 ADR 的 Decision 段直接实现（宪章 ADR 写作纪律第 4 条）。

## Enforcement

**当前仅为边界声明，无机械执行**（如实记录，避免虚假安全感）：

- 没有代码或测试能检测"审核通过率 98%"与"98% 的家庭获得改善"之间的
  表述漂移；发表前产品负责人的人工判断是唯一防线，本 ADR 不为此设计
  额外的组织流程。
- `MIN_SAMPLE_SIZE_FOR_CONFIDENT_RATE = 5`（家长可见门槛）已有代码
  （`backend/domains/product_intelligence/application/family_experience_signal.py`）
  和测试覆盖；发表级门槛按 override 后的决定不预先设定,因此也没有
  对应护栏，等有真实数据时按需判断。
- 若未来实现发表流程且调用量、误用风险等形成可测瓶颈，可以再补一个
  校验"对外材料不含结果因果关键词清单"的自动化检查，但这不是本 ADR
  现在要求的前提条件。

## 关联

- `docs/13_research/market/FIVE_COMPANY_BENCHMARK_STATUS_V1.md` §3.2
  （原始悬而未决的产品决策）
- `governance/ADR/ADR-0005-ai-native-platform.md` §3（R9 在 AI 原生
  架构下加强，不放宽）
- `governance/ADR/ADR-0029-service-product-ai-platform-boundaries.md`
  "不采用的方案"第 4 条、"验收与回滚"联合评审先例
- `governance/ADR/ADR-0056-multimodal-evaluation-boundary.md` 决策
  第 3 条（技术指标 vs 家庭总分/疗效的既有边界先例）
- `backend/domains/service/fgcn/quality_contribution_application.py`
- `backend/domains/product_intelligence/application/family_experience_signal.py`
- `governance/REPOSITORY_CONSTITUTION.md` R9
