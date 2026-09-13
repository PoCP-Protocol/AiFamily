# ADR-0168: Family AGI Platform 战略边界重定位——Child + Family + Society，教育降级为 First Wedge

- **Status**: Accepted
- **Date**: 2026-09-13
- **Deciders**: project-owner
- **Supersedes**: null（不取代 ADR-0167 的 Runtime 分层，只收紧其"服务谁/边界在哪"这一层定位；亦不取代 `docs/01_strategy/FAMILY_AGI_PLATFORM_BLUEPRINT.md` V1.1 已有的大部分内容，那份草案已经方向正确，本 ADR 是把其中最关键的定位段落正式冻结为 canonical 决定，并纠正其余文档里仍然残留的教育中心化叙述）
- **Superseded By**: null

## Context

`docs/00_system/SYSTEM_MANIFEST.md` §2/§3（本次会话读取时的版本，`updated: 2026-09-04`）把系统边界写成：

> 服务对象：中国家庭 —— 家长（商业主体）、孩子（成长主体）、以及为家庭提供服务的教师/专家/机构。
> 解决的问题：家庭在孩子成长过程中反复出现的真实困境（亲子沟通、学习习惯、手机管理、自驱力不足）

这段文字把系统边界锚定在"孩子成长/教育"上，虽然没有明写"教育平台"，但足以让后续研发团队把系统理解成"家庭教育平台+AI"。

`docs/01_strategy/FAMILY_AGI_PLATFORM_BLUEPRINT.md`（V1.1，`canonical: false`，2026-09-11）已经在往正确方向修正——第一节把基本单位定义为 Family、第三十七节给出"从孩子成长切入、以家庭为基本需求单位"的战略定义——但项目负责人本次会话（2026-09-13）指出：即使这份草案，叙述重心仍然过多围绕"教育切入"展开（§二的"教育切入的原因"、§六的"从孩子切入"标题本身），容易被读成"教育平台升级成AGI"，而不是"AGI平台，教育只是第一个垂直切口"。这是叙述比例问题，不是方向错误——但足以造成 CLAUDE.md 铁律第7条要求的"如实汇报"在战略定位层面失效：读者会从主导叙事推断出错误的系统边界。

其余 18 处文档（`docs/05_ai/*`、`docs/06_platform/*`、`docs/07_data/*`、`docs/00_system/FAMILY_NEEDS_PLATFORM_TARGET_MODEL.md`、`docs/11_delivery/*` 等，见本 ADR "References" 段的完整清单）不同程度沿用"法咪莉教育"这一品牌叙事框架，是历史沉淀，本 ADR 不逐一改写（工作量超出单次会话边界，且多数是 `13_research`/`draft` 类非 canonical 文档），但本 ADR 的 Decision 段是后续任何修订这些文档时必须对齐的唯一权威定位。

按 `governance/ADR/README.md` 的"何时必须写 ADR"第 1 条（改变边界）与 `SYSTEM_MANIFEST.md` §9（"系统边界变化必须先有 ADR，再改本文件"），本决定必须先有 ADR。

## Decision

**冻结以下为 AiFamily 最高战略边界，优先于此前任何"家庭教育/家庭成长平台"框架下的表述：**

1. **平台基本单位**：Family = 最基本的需求、决策、关系和资源协同单位。Family ≠ "有孩子的教育家庭"。

2. **系统边界**：`Child + Family + Society`，不是 `Child + Education`。

   ```text
   FAMILY
     ├── CHILD   （孩子成长：学习/情绪/社交/兴趣/能力/未来）
     ├── PARENTS （父母发展：工作/压力/健康/成长/养老/生活）
     └── FAMILY  （家庭系统：关系/资源/决策/财务/生活/风险）
   ```

   向外连接：家庭 → AI 能力 → 学校/教师 → 专家 → 医疗健康 → 社区 → 生活服务 → 职业资源 → 金融保险 → 养老 → 社会公共资源。

3. **系统定义（正式版，取代 SYSTEM_MANIFEST §2 现有表述）**：

   > AiFamily 是一个以孩子和家庭为中心、以 Family 为基本需求单位的 AGI-native Family
   > Intelligence Platform。孩子成长与教育是第一切入口，而不是平台边界；平台长期服务
   > 家庭在人生不同阶段不断变化的需求，并通过 AI、家庭成员与社会资源网络共同形成行动
   > 和结果。

   简版：**AiFamily 是家庭的智能操作系统**——`Understand My Family → Understand What
   We Need → Help Us Decide → Help Us Act → Connect the Right Resources → Learn From
   What Happened`。

4. **教育的地位**：降级为 **First Vertical / First Wedge**，理由不是"我们要做教育公司"，而是孩子天然连接整个家庭系统（一个孩子的问题几乎总是同时涉及 Parenting/夫妻关系/家庭规则/学校/同伴/健康/时间/家庭资源），因此 Child Growth 是训练 Family AGI"不要把表面需求直接映射成商品"这条纪律的最佳入口场景，不是平台的最终品类。

5. **课程/教师/专家/直播全部降一级，归为 Capability / Resource，不是 Platform Core**：

   ```text
   课程     = 一种 Capability
   教师     = 一种 Human Capability
   医生/心理师 = 一种 Professional Capability
   AI Agent = 一种 Digital Capability
   社区     = 一种 Social Resource
   学校     = 一种 Institutional Resource
   ```

   平台核心链路固定为：`Family → Family Need → Family World Model → Goal → Plan →
   Capability/Resource → Action → Outcome`。以后新增任何服务品类（健康/职业/金融/养老）
   都通过在 Capability/Resource 层挂载新实现，不需要重构平台底座——这是本条决定的
   可执行判据：任何新品类接入如果要求修改 Family/Need/World Model/Goal/Plan 这条主链
   的 schema，说明底座设计违反了本条。

6. **Family World Model 覆盖整个家庭系统，不只是孩子/教育维度**。战略上允许的维度（不
   要求本次一次性建表）：

   ```text
   FamilyWorldState
   ├── Family Identity      ├── Health Context
   ├── Members(Child/Parent/ ├── Education Context
   │   Grandparent/Guardian) ├── Work Context
   ├── Relationships         ├── Financial Context
   ├── Child Development     ├── Living Context
   ├── Adult Development     ├── Social Context
   ├── Needs / Goals /       ├── Actions / Outcomes
   │   Preferences /         ├── Resources
   │   Constraints / Risks   └── Unknowns
   ```

7. **战略边界要宽，第一阶段产品边界要窄**——这是本 ADR 最容易被误读为"马上要建 20
   张表"的地方，必须明确：架构上允许上述维度存在（不阻断未来扩展、不要求现在推翻已
   有 schema），业务上继续从"孩子成长"纵切进入，其余维度按真实家庭需求出现时再长出来，
   不预先建空壳（违反 R14"骨架冒充能力"）。

8. **Society Brain / 三个 Brain 的定义扩大，不局限于教育资源**：

   - **Family Brain**：长期理解一个家庭的大脑（不是"教育孩子的大脑"）。
   - **Society Brain**：理解和调动社会资源的大脑（Education/Health/Mental
     Health/Sports/Arts/Career/Legal/Insurance/Finance/Elder Care/Travel/
     Community/Public Services/Home Services），核心资产是 **Resource
     Intelligence**（谁能解决什么问题、适合什么家庭、什么情况不适用、过去
     Outcome 如何、何时该升级真人），不是"教育资源库"。
   - **Evolution Brain**：根据真实家庭 Outcome 持续改善平台能力的大脑（不是
     "优化课程的大脑"）。

9. **"法咪莉校长"IP 的长期定位调整为 Family Principal**：从孩子成长切入，但不
   伪装"什么都会/什么都能诊断/什么都能解决"——能明确说"这个问题需要老师/建议
   请心理专业人员/涉及医疗我不能替医生判断/这件事必须由家庭自己决定"。这是对
   `governance/REPOSITORY_CONSTITUTION.md` R9（AI 输出不直写 canonical 事实）
   与"不做临床诊断"边界在人格化 IP 层面的具体化，不是新增合规要求，是既有红线
   的自然推论。

10. **商业终局重新定义为 Family Intelligence Membership**，不是"教育会员+课程收入
    +专家佣金"：家庭付费的本质是长期理解+持续规划+家庭记忆+智能陪伴+能力调用+
    资源连接+结果跟踪，教育/健康/专家/家庭/养老/生活服务是这份长期关系之上产生
    的交易，不是反过来。商业链路：`Family Intelligence → Trust → Need Discovery →
    Resource Orchestration → Service Transaction → Outcome → Higher Trust`，不是
    传统电商的 `Traffic → Product → Transaction`。

## Alternatives Considered

**A. 维持现状，只在草案文档（FAMILY_AGI_PLATFORM_BLUEPRINT.md）里描述这个边界，不写
ADR、不改 SYSTEM_MANIFEST。**
支持理由：改动范围小，不触碰 canonical 文档。
否决理由：草案文档 `canonical: false`，不具治理约束力；SYSTEM_MANIFEST 仍写着教育中心化
的边界，任何 Agent 严格按 CLAUDE.md 铁律第1条"先读 SYSTEM_MANIFEST"入场时，仍会得到
错误的边界认知。项目负责人本次会话明确要求"上升为最高战略边界"，只改草案文档不满足
这个要求。

**B. 一次性把全部 18 处沿用"法咪莉教育"叙事的文档都改写为新边界。**
支持理由：彻底消除文档间的叙事不一致，避免"两套故事并存"。
否决理由：其中多数是 `13_research`（非权威，本身就不该被当作当前定位引用）或
`draft`/历史资产（如 `法咪莉教育战略白皮书_30页演讲汇报版.txt` 是 source_material，
按 R2/文档治理规则不应被就地改写，改写历史材料本身违反"Current Truth Never Mixes
With History"）。真正需要立即对齐的只是 canonical 的 L0 文档（SYSTEM_MANIFEST）与
正在走晋升流程的战略草案（FAMILY_AGI_PLATFORM_BLUEPRINT.md）；其余 16 处留作独立、
有 owner、有验收条件的后续任务，避免本次改动范围失控且缺乏逐份核实。

**C. 把"教育"整体移出系统边界之外，作为独立子品牌/子产品运营。**
支持理由：彻底避免边界混淆。
否决理由：与项目负责人本次陈述直接矛盾——教育明确是"最好的第一入口"，移出边界
反而丢掉了"孩子天然连接整个家庭系统"这一入口价值，且现有绝大多数真实代码
（`family_need`/growth/assessment/course 等域）都是这条入口场景的真实落地，
移出边界会造成"代码在边界内、文档说边界外"的新矛盾。

## Consequences

### 正面
- SYSTEM_MANIFEST 与草案战略文档的定位从"品类不一致"收敛为"品类一致、进度不同"，
  降低后续 Agent 把系统误解释为教育平台的概率。
- 给"课程/教师/专家=Capability，不是Core"一条可执行判据（新品类接入是否要求改主链
  schema），可以直接写进后续架构测试（例如约束 `backend/domains/` 下不得让教育相关
  域直接耦合 Family/Need/Goal/Plan 的核心 ORM，需经 Capability/Resource 抽象层）。
- 为后续 Wave（P3 AI/P5 FGCN/P6 商品化）的范围判断提供更宽的战略参照系，避免每次
  新增品类都要重新论证"这算不算跑题"。

### 负面 / 代价
- 短期内 SYSTEM_MANIFEST 与仍未修订的 16 份下游文档之间会出现"L0 已更新、L1-L4 部分
  未更新"的过渡态，需要在这些文档被下次修订时逐份核对是否与本 ADR 冲突（不是本 ADR
  产生新矛盾，是暴露了已存在的、此前没有canonical依据可以判定谁对谁错的矛盾）。
- "战略边界宽"如果被误读为"现在就要建 FamilyWorldState 全部字段"，会重犯 ADR-0167
  已经明确警告过的"空目录骨架冒充能力"错误——本 ADR 第 7 条决定专门防这个误读，
  但仍需后续 PR review 时人工把关。

### 需要接受的风险
- 教育相关的现有真实代码（`family_need`/`growth`/`assessment`/`course` 域）短期内
  不会因为本 ADR 立即重构——本 ADR 是战略边界决定，不是本次代码变更范围，实际的
  Capability/Resource 抽象层收敛需要单独排期（见"下一步"）。

## Enforcement

- **当前仅为文档层决定**。本 ADR 本身不新增架构测试。
- 立即执行：`docs/00_system/SYSTEM_MANIFEST.md` §2/§3 按本 ADR 第 3/4 条改写（同一
  会话内完成，见 commit）。
- 后续执行路径（不在本 ADR 授权范围内立即做，留给总架构师单独排期）：
  1. 在 `tests/architecture/` 新增一条约束——教育垂类的 Domain（`course`/
     教师相关模块）不得被其他非教育 Domain 直接 import 具体实现，只能通过
     Capability/Resource 抽象接口——把本 ADR 第 5 条从"意图"变成"执行机制"。
  2. `docs/01_strategy/FAMILY_AGI_PLATFORM_BLUEPRINT.md` 完成 §8.2 晋升流程后，
     其 `canonical` 字段改为 `true`，并在其 front matter 加
     `authorized-by-adr: ADR-0168`。
  3. 逐份核对本 ADR References 段列出的 16 份下游文档，标记冲突/无冲突/待改写，
     登记为独立 backlog 项（不在本次会话创建具体任务，避免未经核实就派发）。

## References

- `docs/00_system/SYSTEM_MANIFEST.md` §2/§3（本 ADR 直接修改的 canonical 文档）
- `docs/01_strategy/FAMILY_AGI_PLATFORM_BLUEPRINT.md`（V1.1 草案，本 ADR 冻结其核心
  定位段落，不取代其余内容）
- `governance/ADR/ADR-0167-family-agi-runtime-architecture.md`（Runtime 分层，本 ADR
  不改动其内容，只收紧上层定位）
- `governance/ADR/ADR-0158-agi-native-family-growth-platform.md`（"AGENT-EVIDENCE"
  纪律，本 ADR 的"战略边界宽/产品边界窄"是同一纪律在战略层的应用）
- `docs/01_strategy/COMMERCIAL_VALUE_STRATEGY.md`（商业战略 V2.0，与本 ADR 存在
  叙事重心差异，留待后续单独核实是否需要修订，本 ADR 不越权改写）
- 待后续核对是否与本 ADR 冲突的其余文档：`docs/13_research/technology/
  FAMILY_MEDIA_001_REALITY_AUDIT.md`、`docs/11_delivery/migration/
  MIGRATION_PLAN_V2.md`、`docs/11_delivery/ARCHITECTURE_ALIGNMENT_REVIEW_V1.md`、
  `docs/11_delivery/AGILE_REBUILD_PLAN_V1.md`、`docs/07_data/
  PRINCIPAL_AI_DATA_ARCHITECTURE.md`、`docs/07_data/FAMILY_MEMORY_ARCHITECTURE.md`、
  `docs/06_platform/PRINCIPAL_AI_APPLICATION_ARCHITECTURE.md`、`docs/05_ai/
  GENERATIVE_SYSTEM_ARCHITECTURE.md`、`docs/05_ai/
  PRINCIPAL_AI_APPLICATION_ARCHITECTURE.md`、`docs/05_ai/
  AI_TECHNICAL_ARCHITECTURE_DEEP_DESIGN.md`、`docs/00_system/
  FAMILY_NEEDS_PLATFORM_TARGET_MODEL.md`、`docs/00_system/
  ARCHITECTURE_BENCHMARK_REVIEW_V3.md`、`docs/00_system/
  CORE_BLUEPRINT_GLOBAL_SCALE_ALIGNMENT.md`、`docs/00_system/
  ARCHITECTURE_ALIGNMENT_V2.md`、`docs/05_ai/SERVICE_PRODUCT_DESIGN_AI_PLATFORM.md`
  （`13_research`/`source_materials` 下的两份历史 PPT/白皮书文本不列入待改写清单，
  按治理规则属于 History，不改写）
