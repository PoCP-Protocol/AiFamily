---
id: FAMILY-AGI-PLATFORM-BLUEPRINT-001
title: FAMILY AGI PLATFORM 总体蓝图
type: strategy
status: draft
version: 1.1
owner: chief-architect
created: 2026-09-11
updated: 2026-09-11
canonical: false
supersedes: null
superseded_by: null
supersedes-positioning-of: docs/00_system/FAMILY_NEEDS_PLATFORM_TARGET_MODEL.md
relates-to: governance/ADR/ADR-0167-family-agi-runtime-architecture.md, governance/ADR/ADR-0158-agi-native-family-growth-platform.md
---

# FAMILY AGI PLATFORM 总体蓝图

> `canonical: false`是因为本文档尚未走完`docs/12_governance/DOCUMENT_GOVERNANCE.md`
> §8.2规定的Research→Decision→Canonical晋升流程（需要先有对应ADR，再由总
> 架构师把决定写入canonical文档）——不代表内容不重要，只代表治理程序尚未走完。
> 本文档记录的是**终局定位**与**十年命题**，不是当前系统的能力声明。凡本文出现的
> 能力描述，均以"目标态"书写；当前诚实进度见第十一节。任何后续文档、汇报、代码
> 评审，引用本文时必须区分"定位"与"已建成"——这是本平台一贯的纪律
> （见`governance/ADR/ADR-0158-agi-native-family-growth-platform.md`
> "AGENT-EVIDENCE"原则的姊妹纪律：叙述不是证据，蓝图也不是实现）。

> **V1.1修订（2026-09-11）**：在V1.0"品类重新定位"基础上，补上一条更根本的
> 第一性原理——本平台不是"数字化平台+外挂大模型"，是**AGI-native
> Platform：智能本身是平台的运行机制，不是外挂能力**。第十二至二十三节是这次
> 修订新增的Learning Architecture + Evolution Engine + AGI Governance三层，
> 是V1.0与"普通AI家庭平台"之间的核心架构分水岭，不是V1.0的可选附录。

## 零、这次重新定位解决的问题

此前的战略文件（`family-platform-v3-blueprint`、`FAMILY_NEEDS_PLATFORM_TARGET_MODEL.md`
等历史资产）已经建立了扎实的业务架构（三中心/五Engine/N0-N8需求闭环/成长服务
北极星），但始终在"家庭教育/家庭成长平台"这个品类框架内做深化。这次重新定位不是
否定这些工作——`FAMILY_NEEDS_PLATFORM_TARGET_MODEL.md`的N0-N8需求闭环、五层
架构映射、数据架构在本蓝图里全部保留，作为"孩子成长"这条纵向场景的第一个真实
落地案例，不重写。

真正改变的是**品类边界**：不再把自己框定成"在线家庭教育平台"或"家庭成长平台"，
而是正式定义一个新的互联网/AI平台品类——

> **以家庭为基本需求单位，以孩子成长为第一锚点，以家庭关系和家庭长期福祉为
> 目标，以AGI为智能内核，以社会专业资源网络为执行网络。**

教育是最合适的第一入口，不是终点和边界。

## 一、重新定义 Family：家庭需求操作系统

传统互联网平台的基本单位各不相同（淘宝=商品、抖音=内容/兴趣、微信=人/关系、
美团=本地服务、LinkedIn=职业身份、医院=患者、学校=学生、保险=保单）。Family
第一次明确采用：

```text
基本单位 = Family（家庭）
```

一个家庭进入系统后，不需要每次重新向AI描述自己是谁——AGI已经理解：

```text
这个家庭是谁 → 有哪些成员 → 成员之间是什么关系 → 孩子处于什么发展阶段
→ 最近发生了什么 → 家庭长期希望成为什么样 → 当前最主要矛盾是什么
→ 过去尝试过什么、什么有效什么无效 → 谁有决策权 → 哪些事需要Guardian确认
→ 需要什么外部资源
```

Family的核心资产不是课程数量、直播场次或老师规模，而是**一个持续演化的
Family World Model**（见第四节）。

## 二、产品世界观：孩子—家庭—社会，三个同心圆

```text
┌─────────────────────────────────────────────┐
│                社会资源网络                  │
│  老师/专家/学校/医生/心理师/教练/社区/营地/    │
│  机构/内容/服务/AI Agent                     │
│        ┌───────────────────────────┐        │
│        │          家庭              │        │
│        │  父亲 ←→ 母亲              │        │
│        │    ↘     ↑     ↙           │        │
│        │      ┌─────────┐           │        │
│        │      │  孩子   │           │        │
│        │      └─────────┘           │        │
│        │  关系/环境/价值观/资源       │        │
│        └───────────────────────────┘        │
└─────────────────────────────────────────────┘
```

**第一圈：孩子。** 教育切入的原因是孩子成长是绝大多数中国家庭高频、高情绪、
高付费意愿、高长期性的共同需求。系统理解的不能只是成绩，而应逐渐形成儿童的
多维成长模型：认知、学习、情绪、行为、社交、身体、兴趣、品格、自主性、未来
发展。

**第二圈：家庭。** 很多"孩子的问题"，真正变量不只在孩子——夫妻教育观不同、
父母情绪状态、家庭沟通方式、祖辈介入、作息节奏、数字设备规则、家庭压力，都
可能影响孩子。已有循证家庭支持体系（如Triple P）的效果指标不只包括儿童，也
包括养育实践、父母效能、父母关系等家庭层变量——这是本平台长期可以参考、但要
用AGI+资源网络superset掉的路线，而不是照搬其"干预体系"定位。

**第三圈：社会。** AGI不应该把所有事情都自己回答。平台价值的关键判断是：何时
AI足够、何时需要课程、何时需要教师、何时应连接心理专业人员、何时需要线下活动、
何时需要同龄群体、何时需要学校参与。这是从"AI助手"变成"平台"的关键分界线。

> 孩子不是孤立用户，家庭不是账号集合，社会资源也不是商品目录。
> Family AGI的任务是持续协调三者。

**与现有市场"局部接近者"的差异判断**（供战略对齐，不是竞品分析文档）：Triple P
是很强的循证家庭支持体系但本质是干预体系；Maven已从生育延伸到育儿/儿科/心理/
专家导航但核心仍是女性与家庭医疗福利；Care.com更接近"家庭作为需求方"但主要是
资源匹配市场，不持续理解家庭、不制定长期目标、不跟踪结果。机会不在于再做一个
家庭服务Marketplace，而在于创建"Family as a Demand Unit"这个新平台范式——把
"持续理解"+"目标形成"+"资源编排"+"结果追踪"四件事第一次统一起来。

## 三、AGI内核：不是更聪明的聊天机器人，是一个真实闭环

法咪莉校长是用户看到的统一入口（Principal，见ADR-0167边界冻结：不得拥有独立
Model Gateway路径），后台真正的智能系统是：

```text
                   法咪莉校长（Principal）
                       │
                       ▼
              Family Intelligence Kernel
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   UNDERSTAND        PLAN           ACT
   理解家庭          规划成长        调动资源
        │              │              │
        └──────────────┼──────────────┘
                       ▼
                    OUTCOME  观察真实结果
                       ▼
                   REFLECT  为什么有效/无效
                       ▼
                    REPLAN
                       └────→ 下一轮
```

普通AI：`问题 → 回答`。Family AGI：`家庭状态 → 理解 → 假设 → 目标 → 计划
→ 行动 → 社会资源执行 → 结果 → 学习 → 更新家庭模型 → 下一次决策`。

**Outcome → Reflection → Replan必须真实改变下一次决策**——这是本平台此前多轮
架构评审反复强调的一条纪律（ADR-0158主线："失败复盘与模型更新"这一步），本蓝图
把它正式确认为整个Family AGI最核心的智能闭环，不是可选的加分项。

**与ADR-0167四级Run Taxonomy的对应关系**（技术内核已冻结，见该ADR）：

```text
UNDERSTAND/PLAN 对应的模型调用 → GatewayAttempt
一次有边界的技术执行            → AgentRun
一次完整的认知演化（含Guardian校准、反思、重规划链条）→ IntelligenceRun
ACT调动资源产生的真实业务事实   → NamedAction / DomainFact
```

本蓝图定义的是"为什么要有这个闭环"（业务/产品层），ADR-0167定义的是"这个闭环
在代码里怎么落地、每层谁拥有什么"（技术层）——两者是同一件事的两个视角，不重复
定义，互为印证。

## 四、Family World Model：持续演化的数字家庭模型

不是一张"大宽表"，是持续变化的家庭数字模型，分层如下：

| 层 | 记录什么 |
|---|---|
| Identity | 谁属于这个家庭、角色、监护关系 |
| Development | 每个孩子所处发展阶段 |
| Relationship | 父母—孩子、夫妻、兄弟姐妹等关系 |
| Context | 最近发生的事件与家庭背景 |
| Needs | 当前显性需求、潜在需求 |
| Goals | 家庭确认的短中长期目标 |
| Hypotheses | AGI当前对问题机制的假设 |
| Evidence | 测评、行为、反馈、观察、专业意见 |
| Plan | 当前成长计划 |
| Actions | 已经采取过什么行动 |
| Outcomes | 行动以后发生了什么 |
| Resources | 已使用/可使用的老师、课程、服务等 |
| Preferences | 家庭偏好、节奏、约束条件 |
| Consent | 哪些家庭成员允许什么数据被怎样使用 |
| Unknowns | **系统明确知道自己还不知道什么** |

`Unknowns`层是关键——真正成熟的AGI不是"什么都知道"，而是能够说"目前我有三个
可能解释，但还缺少两个关键观察，暂时不能下结论"。这对涉及未成年人的场景尤其
重要：Family World Model允许显式承认不确定性，跟`AI_NATIVE_PRINCIPLES.md`
既有的fail-closed纪律（宁可澄清也不猜测）是同一条原则在数据模型层的落地。

**跟已有资产的关系**：`docs/00_system/FAMILY_NEEDS_PLATFORM_TARGET_MODEL.md`
第3.3节列出的`FamilyNeed`/`NeedSignal`/`NeedProfile`/`SolutionBlueprintVersion`
等数据对象，是Family World Model里`Needs`/`Goals`/`Plan`层在"孩子成长"纵向
场景下的第一批真实落地对象，不是平行的另一套模型——本蓝图统一其归属，后续新增
数据对象前先问"这属于World Model哪一层"，不再各域各建一套本地上下文。

## 五、从"用户搜索服务"到"家庭需求驱动资源"——商业模式的根本反转

今天：`家长发现问题 → 搜索 → 自己判断 → 找老师 → 买课程 → 参加活动 → 不知道
有没有效果`。

Family AGI：

```text
Family AGI持续理解家庭 → 识别NEED → 形成GOAL → 设计PLAN
→ 拆成SKILLS/ACTIONS → 判断AI完成/家庭自己完成/需要社会资源
→ Resource Network自动匹配 → 服务履约 → Outcome回流
→ 下一轮资源选择越来越准确
```

社会资源不再是静态"老师商城"，而是**Family Resource Network**：教师、家庭
教育指导师、心理专业人员、教练、学校、营地、运动机构、艺术机构、儿童发展专家、
家庭活动、公益资源、社区资源、在线课程、各类专业AI Agent。此前设计的教师/
机构多租户、B2C/B2B2C、FGCN式角色分工分账（见`family-allocation-platform
-mechanisms`历史资产），在这个更大的理论框架下找到统一归宿：**不是为了建设
教师平台，是在建设Family Resource Network**——FGCN是这个网络在"孩子成长"
纵向场景下的第一个真实实现，不是独立产品线。

**FamilyNeed作为核心业务对象**（补充`FAMILY_NEEDS_PLATFORM_TARGET_MODEL.md`
已有的N0-N8定义，强调"管理需求"而非"卖供给"这个立场）：一句"孩子最近不愿意
去学校"，系统不能立刻卖课，必须先形成结构化的需求对象——表达的需求、可能
原因（学习困难/同伴关系/师生关系/焦虑/家庭压力/睡眠/网络依赖……）、未知项、
风险等级、需要的证据、相关人、拟定目标、计划、干预、资源、结果。

> 传统Marketplace：供给 → 找需求。
> Family：理解需求 → 组织供给 → 对结果负责。

这跟部分对标产品（如Maven的care navigation：帮用户制定目标、组织专家团队、
资源导航）已有相似之处，本平台要做的是把这种能力从单一垂直领域扩展成整个
家庭成长网络的通用能力。

## 六、建设顺序：从孩子切入，而不是永远只做孩子

不同时做所有家庭需求。正确路径：

```text
                  FAMILY AGI KERNEL
                         │
       ┌─────────────────┼─────────────────┐
       ▼                 ▼                 ▼
   Child Growth     Family Relation    Family Life
   （第一阶段）        （第一阶段）        （远期）
```

**第一阶段（当前）**：孩子成长 × 家庭关系——两者天然连在一起，是`FAMILY_NEEDS
_PLATFORM_TARGET_MODEL.md`第6节"建设顺序"已经在做的事（以家庭教育为第一个
需求模板，完成N0-N8单家庭闭环→抽象SolutionBlueprintVersion→接入FGCN→扩展
产品/服务/解决方案目录→建设规模化Cell），本蓝图不改这个顺序，只是明确这个
顺序服务的终局品类比"教育"更大。

**第二阶段**：学习成长、情绪与心理支持、亲子关系、家庭沟通、兴趣发展、体育
健康、社会交往、生涯启蒙、家庭活动、家庭照护——逐个纵向场景复用同一个AGI内核
和Family World Model，不为每个场景重建一套理解/规划/执行逻辑。

**第三阶段（远期，不在V1范围）**：养老、健康管理、家庭消费、家庭保障、家庭
资产。本蓝图明确标注这是方向性预留，不是当前工作项，避免过早铺摊子——跟本轮
会话反复强调的"不做骨架冒充能力"纪律一致。

## 七、飞轮与护城河：Family Outcome Intelligence

```text
100个家庭   → 知道哪些方法可能有效
1万个家庭   → 知道什么类型家庭、在什么条件下、什么intervention更有效
100万个家庭 → 形成Family Outcome Intelligence
1000万个家庭 → 形成非常难复制的Family World Model + Intervention Network
```

例如未来AGI可能发现："对12岁、亲子冲突增强、父母教养策略高度不一致、孩子
自主性较强的家庭，直接安排学习课程的长期效果很差；先进行父母协同和家庭沟通
干预，再进入学习计划，效果明显更好。"这时平台拥有的不是"内容推荐算法"，是
**Family Outcome Model**——这是长期护城河所在，跟已有的`family-ai-moat`历史
判断（Context×Ontology×ResourceNet×ServiceFeedback×Evidence×Trust）一致，
本蓝图把"结果证据规模化"positioning为护城河的最终兑现形式，其余五项是构建
它的必要条件，不是并列的六个独立护城河。

**诚实前提**：这条飞轮需要真实规模的家庭+真实的outcome回读循环才能转起来，
当前系统连Family World Model的最小雏形都未建成（见第十一节），这一节是终局
判断依据，不是近期可兑现的能力声明。

## 八、商业模式：四层收入结构

| 层 | 商业模式 |
|---|---|
| Family AGI | 家庭会员/订阅 |
| Growth Solutions | 成长方案、课程、计划 |
| Resource Network | 专家、老师、机构、服务交易佣金 |
| Institutional Network | 学校、企业福利、保险、政府/社区B2B2C |

长期收入的核心变量不是"一个家庭每年买多少课"，是**一个家庭每年有多少需求
通过Family被理解、组织和履约**。核心指标应逐渐从DAU迁移到：

```text
Active Families / Active Family Needs
Goal Confirmation Rate（需求→目标确认率）
Need → Plan Rate / Plan → Action Rate / Action Completion Rate
Measured Outcome Improvement（真实结果改善，非AI自判）
Resource Match Success（资源匹配成功率，非伪造供给）
Family Retention / Family Trust
```

**与既有商业架构文档的关系**：`family-commerce-architecture`历史资产已经定义
了三层（RESOURCE→SOLUTION→RELATIONSHIP）+六层Catalog+Provider五类+Family
Account/Sponsor分离等具体机制，本节的四层收入结构是这些机制在"新品类定位"下
的战略归纳，不推翻其具体设计，两者是同一套商业架构在不同抽象层的表述。

## 九、与Principal/成长链治理边界的一致性（不重复既有纪律，只做确认）

本蓝图不改变、也不需要改变以下已经冻结的治理边界（详见对应ADR/历史资产，本节
仅确认新定位跟它们完全兼容，不产生冲突）：

- 两阶段Growth Fiduciary（Eligibility Gate FAIL CLOSED + Revenue NOT_A
  _RANKING_SIGNAL）——资源匹配任何时候不能被营收信号污染，`family-commerce
  -architecture`已有判断在这个更大定位下依然成立且更重要（社会资源网络规模
  越大，商业化压力越大，这条红线的价值越高）。
- 硬约束优先级Child > Family > Provider > Platform，禁Child/Family Score
  ——`family-allocation-platform-mechanisms`已有纪律原样适用于Family Resource
  Network。
- AI cognition不能直接创造业务事实（NamedAction/DomainFact边界，ADR-0167）
  ——AGI内核的ACT环节必须经过Human Gate/Policy/Named Action，不因为"现在是
  更大的平台品类"就放松。
- 成人授权→家庭表达→AGI理解与因果假设→可修改方案→Guardian确认→低风险行动
  →结果回读→失败复盘（ADR-0158主线）——本蓝图第三节的AGI内核闭环是这条主线
  的战略层复述，不是替代。

## 十、跟历史文档的关系（避免读者误判哪个是权威）

| 历史文档 | 在新定位下的角色 |
|---|---|
| `docs/00_system/FAMILY_NEEDS_PLATFORM_TARGET_MODEL.md` | 保留为权威——N0-N8需求闭环、五层架构映射、数据架构，是"孩子成长"纵向场景的具体落地规范，本蓝图第五、六节引用，不重写 |
| `governance/ADR/ADR-0167-family-agi-runtime-architecture.md` | 保留为权威——四级Run Taxonomy是本蓝图第三节AGI内核的技术实现层定义，已`Accepted` |
| `governance/ADR/ADR-0158-agi-native-family-growth-platform.md` | 保留为权威——跨AI协作记录+主线闭环定义+质量事故/治理原则的append-only日志，本蓝图不替代其内容，只在第三、九节引用其已冻结的结论 |
| 内存中的`family-platform-v3-blueprint`（三中心+五Engine+HGSLR等） | **降级为历史资产**——2026-08-29仓库重建后，旧蓝图术语已经不是当前代码的权威描述（见`aifamily-repo-rebuilt-2026-08-29`记忆记录），本蓝图是重建后第一份正式的战略定位文档，取代其"品类定位"部分，其HGSLR北极星指标/两阶段Growth Fiduciary等具体机制判断依然有效，已在第七、九节吸收 |
| `family-commerce-architecture`、`family-allocation-platform-mechanisms`、`family-ai-moat`等历史记忆记录 | 保留为具体机制设计依据，本蓝图第七、八、九节做战略归纳，不重新设计 |

## 十二、第一性原理：AGI-native Platform，不是"数字化平台+外挂大模型"

传统数字平台的运行方式：

```text
人设计业务规则 → 人配置流程 → 软件按规则执行 → 人看报表 → 人决定怎么改
→ 开发人员改程序
```

Family AGI应该逐渐变成：

```text
感知家庭与环境 → 理解变化 → 形成假设 → 制定计划 → 调动资源 → 执行动作
→ 观察真实结果 → 反思为什么有效/无效 → 更新认知 → 优化策略
→ 产生新的能力建议 → 通过治理门进入下一版本
```

**平台本身存在学习闭环**——这是区分"AGI原生平台"和"上一代数字平台+AI功能"的
唯一真实标准，不是"有没有聊天机器人"。最大的区别是**谁在决定下一步**：传统
数字平台是`DATA → HUMAN → DECISION → SOFTWARE`；Family AGI是`DATA → WORLD
MODEL → REASONING → PLAN → ACTION → OUTCOME → LEARNING → WORLD MODEL/
POLICY/SKILL`。人在系统里的作用从"每次亲自设计流程"变成"定义目标、价值边界、
安全规则，并监督重要决策"。

Family的新定义据此再升一级：

> **FAMILY是一个以家庭为基本需求单位、以Family AGI为智能内核，能够持续感知、
> 理解、规划、行动、学习和受控进化的家庭智能网络。**

关键是最后四个字：**受控进化**（第十四节展开边界）。未来核心竞争力的判断
标准：**同样运行一年以后，Family是否比一年前更理解家庭、更会制定方案、更会
调用资源、更知道什么方法对什么家庭有效**——这才是AGI平台，不是"功能有多少"。

## 十三、学习的四个层次（不能混成一句"模型越来越聪明"）

**第一层：Family Personal Learning（单个家庭学习）**——最基础的一层。第1个月
系统只知道基础信息；第3个月知道家庭节奏、孩子特点、父母沟通模式；第12个月
知道这个家庭什么方式容易接受/容易失败、什么时间适合行动、什么资源更有效。
沉淀在Family World Model（第四节）的Memory/Outcome/Preference/Relationship
Pattern里，必须遵守授权与数据最小化——不因为"要学习"就放松Consent边界。

**第二层：Family Outcome Intelligence（跨家庭模式学习）**——平台真正产生
网络效应的地方。系统逐渐学到"什么家庭+什么年龄+什么环境+什么问题+什么
intervention+什么执行强度=什么outcome"，这是第七节已经定义的护城河核心，
这里补上它在"四层学习"框架里的确切位置：它是L2群体级学习，不是L1家庭级
适应的简单累加。

**第三层：Skill Evolution（Skill自我优化）**——例如`ParentChildCommunication
Skill V1`跑了十万个IntelligenceRun后发现：A类家庭3步法效果最好，B类家庭
需要先做父母情绪调整，C类家庭应该直接进入专业人工服务。系统不应永远执行
固定Skill，而应形成`Skill V1 → Outcome Analysis → Improvement Candidate
→ Eval → Human/Policy Gate → Skill V1.1`——跟`AI_NATIVE_PRINCIPLES.md`已有
的"能力必须生成式，不是if/else伪能力"这条纪律是同一方向在Skill生命周期上的
延伸：能力不仅要生成式产生，还要生成式地被证据驱动地迭代。

**第四层：Platform Evolution（平台自身能力进化）**——最深的一层。Family
未来应能发现"当前系统没有解决这种家庭问题的能力"，提出Capability Gap→需要
新Skill/Tool/Agent/数据源/专业合作方？→自动生成Capability Proposal/Skill
Draft/Evaluation Plan/Implementation Candidate，再经治理体系批准进入生产。

## 十四、受控进化：Governed Self-Evolution，不是Unbounded Self-Modification

**不允许**的模式：`AGI发现问题 → 自己改代码 → 自己部署生产`——这是不可控的，
在任何情况下都不批准，跟涉及未成年人数据的平台性质完全不相容。

**正确**的模式：

```text
OBSERVE  发现能力缺口
  ↓
REFLECT  提出改进假设
  ↓
DESIGN   生成新Policy/Skill/Prompt/Tool/Code Candidate
  ↓
EVALUATE 仿真、历史回放、A/B、安全测试、回归测试
  ↓
GOVERN   Human Gate / Risk Gate / Release Gate
  ↓
DEPLOY   受控发布
  ↓
OBSERVE AGAIN
```

Family真正需要的是**Governed Self-Evolution**，任何"自进化"能力从设计之初就
必须经过这条链路，没有例外——这条边界跟第九节已冻结的治理边界（Growth
Fiduciary Eligibility Gate FAIL CLOSED、NamedAction/DomainFact必须经
ToolRuntime+Policy+Human Gate、Governed Autonomy五级）是同一条纪律在
"平台自我改进"这个新维度上的延伸，不是新发明一套治理体系。

## 十五、技术架构总图：Learning是第一等公民，不是外围模块

```text
                  FAMILY AGI PLATFORM
                           │
                           ▼
                ┌──────────────────┐
                │ Perception Layer │  感知家庭与环境
                └────────┬─────────┘
                         ▼
                ┌──────────────────┐
                │ Family World     │
                │ Model            │
                └────────┬─────────┘
                         ▼
                ┌──────────────────┐
                │ Reasoning &      │
                │ Planning Kernel  │
                └────────┬─────────┘
                         ▼
             ┌────────────────────────┐
             │ Agent / Skill / Tool   │
             │ Runtime                │
             └───────────┬────────────┘
                         ▼
                ┌──────────────────┐
                │ Real-world       │  真实业务行动
                │ Action           │  (NamedAction/DomainFact)
                └────────┬─────────┘
                         ▼
                ┌──────────────────┐
                │ Outcome          │
                │ Observation      │
                └────────┬─────────┘
                         ▼
                ┌──────────────────┐
                │ Reflection &     │
                │ Learning         │
                └────────┬─────────┘
                         ▼
             ┌────────────────────────┐
             │ Evolution Engine       │  能力进化引擎（第二十二节）
             └───────────┬────────────┘
                         ▼
                ┌──────────────────┐
                │ Evaluation &     │
                │ Governance Gate  │
                └────────┬─────────┘
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
       World Model更新          Skill/Policy/Agent升级
```

**跟ADR-0167四级Run Taxonomy的映射**（不新增第五种runtime ledger，遵守该ADR
已冻结的"封闭集合"纪律）：`Reasoning & Planning Kernel`产生的模型调用是
`GatewayAttempt`；`Agent/Skill/Tool Runtime`的单步执行是`AgentRun`；整条
`Perception→...→Reflection`的认知演化链路是`IntelligenceRun`；`Real-world
Action`必须是`NamedAction/DomainFact`。`Evolution Engine`和`Evaluation &
Governance Gate`是IntelligenceRun之上的新增治理环节，不是第五级Run，是
"IntelligenceRun的产出如何被证据驱动地反馈进World Model/Skill/Policy"这一
问题的答案，本身不产生新的业务事实，只产生"能力改进候选"。

## 十六、三个循环：Loop A（家庭成长）/ Loop B（智能学习）/ Loop C（平台进化）

**Loop A：家庭成长循环**——`Need → Goal → Plan → Action → Outcome →
Reflection → Replan`，作用对象是**一个家庭**。这是第三节AGI内核闭环、也是
ADR-0158主线八段的执行层落地，已有雏形。

**Loop B：智能学习循环**——`Many Outcomes → Pattern Discovery → Hypothesis
→ Evaluation → Better Policy/Skill`，作用对象是**Family的智能能力**。对应
第十三节的第二、三层学习。

**Loop C：平台进化循环**——`Capability Gap → Capability Proposal → Build
→ Eval → Release Gate → New Capability`，作用对象是**Family平台自己**。
对应第十三节的第四层学习、第二十二节的Evolution Engine。

三个循环一起转，Family才真正是AGI-native平台——只转Loop A是"AI辅助的传统
应用"；转到Loop B才开始产生第七节的护城河飞轮；转到Loop C才是完整的
Governed Self-Evolution。三者的建设顺序应该是A先于B先于C（诚实进度见
第二十四节），不能跳级宣称"平台会自我进化"却连Loop A的Outcome回读都没有
真实验证过。

## 十七、Learning Contract必须从Goal/Plan/Action/Skill诞生之日起存在

以前的理解是把Outcome Learning（对应旧R8）放在建设顺序的中后段——按战略
架构重新审视，这个理解需要修正：**Outcome Learning的完整高级能力可以晚建
（R8），但"Learning Contract"必须从更早的阶段（对应旧R3/R4量级的工作）就
进入系统**。任何Goal/Plan/Action/Skill从诞生之日起就必须回答：

```text
我们期待观察什么？多长时间观察？什么叫有效？什么叫无效？
什么情况应该停止？什么情况应该升级？
结果如何回流？哪些结果允许用于跨家庭学习？
```

不这样做的后果：前面几年积累的数据以后根本没法用于AGI学习——这不是可以
后补的技术债，是数据资产从源头就残缺，晚建等于重新积累。这条纪律需要在
`FAMILY_NEEDS_PLATFORM_TARGET_MODEL.md`的N0-N8闭环、以及后续任何新Goal/
Plan/Skill契约设计时前置检查，具体落地时间由总架构师按现有建设节奏排期，
本蓝图只冻结"必须从早期就有"这个原则本身。

## 十八、Learnable Skill：`GrowthSkillSpec`字段升级方向

以后`GrowthSkillSpec`不能只是"输入/步骤/输出"，目标态字段：

```text
problem / goal / applicability / contraindications
intervention / knowledge / actions / tools / human_roles
expected_observations
outcome_metrics
success_criteria / failure_criteria
stop_rules / escalation_rules
learning_signals
version
evidence_level
evaluation_policy
```

这意味着Family的Skill从设计之初就是**Learnable Skill**，不是写死流程——
`contraindications`（禁忌/不适用情形）、`stop_rules`/`escalation_rules`
（何时该停、何时该升级人工）跟本平台"capability_first但唯安全红线不放开"
的既有纪律（`joysoul-capability-before-limits`同类判断在Family语境下的
对应）是同一方向：能力越开放，越需要显式的、可学习的边界条件，不是靠人工
每次临时判断。字段设计的具体落地由后续实施ADR/PR细化，本节只锁定方向。

## 十九、Adaptive Planning与Outcome-based Resource Matching

**Planner的演进方向**：V1阶段是`deterministic rules + LLM reasoning`
——这是当前正确的做法（`ContextDrivenPathDraftPlanner`一类的确定性打分层，
不冒充Planner，见ADR-0167已有判断），不建议现在就跳到自适应。长期方向是
`Planner V1 → Outcome feedback → Planner Evaluation → Policy improvement
→ Planner V2`，最终形成**Adaptive Planning**——例如系统逐渐发现同样是
亲子冲突，某些家庭适合"一周一个小行动"，另一些家庭适合集中式干预，Planner
应该学会区别，但这是Loop B真正跑起来之后的能力，不是V1的工作范围。

**资源网络的演进方向**：不能是静态排行榜（"五星老师推荐给所有人"）。目标态
是`Resource × Family Type × Need Type × Age × Context × Intervention
Stage → Outcome`，让系统知道"老师A不是总体最好，但对某一类10-13岁、学习
动力问题家庭效果特别好"——**Outcome-based Resource Matching**，比传统
Marketplace的评分推荐高一个层次，是第五节Family Resource Network的长期
演进终点，不是V1阶段的资源匹配就要做到这个程度。

## 二十、Family Intelligence Asset：平台真正的资产层

平台最终的核心资产不是传统互联网公司的"用户表/订单表/内容表/推荐模型"，而是：

```text
Family World Models + Outcome Graph + Intervention Knowledge
+ Skill Library + Resource Performance Model + Planner Policy
+ Family Pattern Library
```

这些共同形成**Family Intelligence Asset**——这是对第七节"护城河"判断的
资产化表述，跟已有的`family-ai-moat`历史判断（Context×Ontology×
ResourceNet×ServiceFeedback×Evidence×Trust）指向同一件事，本节给出的是
"这些资产具体长成什么形态"的答案，不是新增一条独立的护城河理论。

## 二十一、代际差异总结与核心指标：Intelligence Improvement Rate

```text
Web 1.0        Information Platform
Web 2.0        Interaction / Transaction Platform
AI Platform    AI-assisted Platform
Family AGI     Learning + Reasoning + Acting + Evolving Platform
```

> **Family不是一个"装了AI的平台"，而是一个自身具备认知、规划、行动、学习与
> 受控进化能力的平台。**

传统软件的版本目标是`Feature ↑`；Family AGI的目标是`Understanding Quality
↑ / Planning Quality ↑ / Outcome Quality ↑ / Resource Match Quality ↑ /
Safety ↑ / Personalization ↑ / Learning Speed ↑`。据此新增一个核心指标，
补充第八节已有的商业指标体系：

**Intelligence Improvement Rate**——例如每季度回答：同一类FamilyNeed相比
90天前，需求识别准确率提高多少？目标接受率提高多少？计划完成率提高多少？
Outcome提高多少？无效干预下降多少？人工升级是否更准确？这个指标比"上线了
多少功能"更接近AGI平台的真正进步，是判断Loop B是否真的在转的直接证据——
指标全部为0或无法测量，就说明Loop B还没有真正跑起来，不能仅凭"设计了这套
架构"就宣称平台在进化。

## 二十二、新增核心子系统：Family Evolution Engine

正式在`World Model / Planner / Agent Runtime / Skill Runtime / Tool
Runtime / Outcome Learning`之外，新增一个子系统：**Family Evolution
Engine**，负责四件事：

```text
1. Detect   发现系统哪里表现不好
2. Explain  分析为什么表现不好
3. Propose  提出Policy/Skill/Agent/Tool改进
4. Evaluate 证明新版本是否更好
```

**它没有直接生产发布权**——最后必须经过`Evaluation Gate → Safety Gate →
Human Governance → Release Gate`，跟第十四节Governed Self-Evolution是
同一条边界的两种表述（第十四节是流程视角，本节是子系统职责视角）。这正好
和既有的`release_gate`思想（G0-G6生产就绪阶段门，ADR-0167引用的ADR-0162）
接起来——Family Evolution Engine产生的是"改进候选"，不是"已批准的新能力"，
批准权始终在既有治理链路里，这个子系统不改变、不绕过既有Gate的权限边界。

## 二十三、四层自进化与终局判断

```text
L1 家庭级适应     这个家庭越用越懂它
L2 群体级学习     家庭越多，系统越知道什么有效
L3 能力级进化     Skill/Planner/Resource Matching越来越强
L4 平台级进化     平台自己发现能力缺口并提出新能力
```

四层一旦真正跑起来，Family就和普通数字平台彻底分开。终局不是"做一个最聪明
的家庭聊天机器人"，而是**建设一个能够与数千万家庭共同成长的智能系统**——
家庭在成长（孩子在长大、关系在变化、需求在变化），平台也在成长（理解能力
在提高、计划能力在提高、服务能力在提高、资源网络在提高）：

> **Families Grow. Family AGI Grows With Them.**

## 二十五、Learning Plane：新增的第三种数据平面

传统架构通常只有`Operational DB`+`Analytics DB`两层。Family目标态需要第三层
**Learning Plane**：

```text
                    Operational Truth
                           │
                           ▼
                       Outcome
                           │
                           ▼
                 Learning Signal Builder
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
   Family Learning   Population Learning  Eval Dataset
          │                │                │
          ▼                ▼                ▼
    World Model       Pattern Model     Evaluation
```

对应第十三节L1/L2学习层在数据架构上的落地：`Family Learning`产出回流World
Model（L1），`Population Learning`产出Pattern Model（L2），两者共同的
`Eval Dataset`是第二十七节Evolution Gate的输入，不是三条互不相干的管道。

**LearningSignal必须是一等对象，不能事后从日志里挖**。每次Action从设计之初
就必须定义：`Expected Outcome / Expected Observation / Measurement Window
/ Success Criteria / Failure Criteria / Stop Criteria / Escalation Criteria
/ Learning Eligibility`。举例：

```text
Action: 今晚进行一次10分钟无评判倾听
ExpectedObservation: 孩子主动表达时长增加
ObservationWindow: 24 hours
Success: 完成并没有升级为争吵
Partial: 完成但沟通中断
Failure: 拒绝执行 / 冲突升级
Escalation: 连续3次冲突升级
```

这是第十七节"Learning Contract必须从Goal/Plan/Action/Skill诞生之日起存在"
的具体字段化实现，两节合起来读——十七节定的是原则（必须早建），本节定的是
`LearningSignal`这个对象长什么样。

## 二十六、Goal/Plan/Skill必须版本化，World Model必须时序化+带置信度

**版本化**：不能只有"当前Plan"，必须`Plan v1 → Outcome → Reflection →
Plan v2`，才能回答"为什么系统改变了计划"。同理`Skill v1 → v1.1 → v2`必须
保留`Evidence / Change Reason / Expected Improvement / Eval Result /
Release Version / Rollback Version`。

**Temporal World Model**：家庭不是静态的，V1的World Model是"系统现在如何
理解这个家庭"，目标态要能看到`State(t0) → State(t1) → State(t2) → ...`，
从而理解趋势/突变/周期性/长期变化（例如"亲子冲突：8周前4.5，4周前3.8，
现在2.1"），而不是简单覆盖旧值。

**World Model Confidence**：任何`FamilyWorldState`都应支持`value /
confidence / evidence_refs / last_updated / source / contradictions`。
例如假设"孩子的学习冲突主要来自自主性需求"，`confidence=0.62`，
`evidence=parent interviews+action outcomes+assessment`，
`contradiction=school feedback suggests peer pressure`——这正是第四节
`Unknowns`层的具体量化实现，不是新增一个独立概念：`confidence`低、
`contradictions`存在，就是`Unknowns`在数据模型上的表现形式。

**反事实学习（Counterfactual Learning）**：V1阶段不做复杂causal model，
但数据模型从第一天就应记录`Candidate Actions / Chosen Action / Reason /
Alternative Rejected / Outcome`，否则未来无法做高质量策略学习——这是最
容易被"先把功能做出来"心态省略、但事后无法补救的一类字段，需要在早期
Goal/Plan/Action契约设计时就前置检查（跟第十七节同一条纪律）。

## 二十七、Family Pattern Library：概率性模式，不是永久标签

平台运行后会形成`Pattern`（例如"高控制+高冲突+高自主儿童"、"低参与父亲+
高压力母亲"、"成绩良好+学习动机下降"）。**Pattern不能成为标签化诊断**，
必须定义为**Probabilistic Pattern**，只用于检索/推理/Planner参考，不能
成为永久家庭身份标签——这条边界跟第四节"Unknowns层承认不确定性"、
`AI_NATIVE_PRINCIPLES.md`既有的"不给家庭贴标签"纪律（`FAMILY_NEEDS
_PLATFORM_TARGET_MODEL.md`N1节已有"不替家庭定义需求，不给家庭贴标签"）
是同一条红线在跨家庭学习场景下的延伸，不是新规则。

## 二十八、Outcome-aware Resource Orchestration：资源网络的Outcome画像

每个Resource不能只有`rating/price/availability`，目标态应拥有
`ResourceOutcomeProfile`——例如"Teacher A：strong=10-13岁学习动力家庭配合
高，weak=高危心理问题，best format=weekly coaching，average outcome
window=4-6周"。这样匹配从"商品推荐"升级为**Outcome-aware Resource
Orchestration**，是第十九节Outcome-based Resource Matching的具体数据结构，
两节合起来读。

## 二十九、Agent分类与Model Gateway可替换原则

**Agent四类**（角色划分，不是立即拆微服务）：`Cognitive Agents`（理解/
推理/规划）、`Execution Agents`（调用工具/服务）、`Learning Agents`（分析
Outcome/发现模式）、`Evolution Agents`（提出系统改进）。**Agent != Authority
**——任何Agent都不能绕过Policy/Human Gate/Release Gate，这是对第九节既有
边界的重申，不是新规则。V1阶段先作为`AgentRuntime Profiles`存在，不建议
一开始全部拆成独立微服务（跟ADR-0167"不新建第四套runtime、扩展现有
`agent_runtime/`"的既有裁决一致）。

**Model Gateway必须可替换**：`AgentRuntime → Model Gateway → Provider`
的既有链路（`backend/intelligence/model_gateway`）继续是唯一路径，不同
任务可选不同模型能力（理解/推理/结构化生成/多模态/实时语音/长上下文/代码
生成）。**关键原则：Learning Asset ≠ Foundation Model**——真正属于Family
的是Family World Model、Outcome Data、Skill Library、Evaluation、Planner
Policy、Resource Network，不是某一个大模型的权重。这条原则跟已有的
`family-ai-moat`历史判断（"护城河=Context×Ontology×ResourceNet×
ServiceFeedback×Evidence×Trust，模型可换"）完全一致，本节是它在"学习资产"
维度上的重新确认。

## 三十、Family Evolution Engine：七个子模块（细化第二十二节）

第二十二节已定义Evolution Engine的四个职责（Detect/Explain/Propose/
Evaluate），本节给出目标态的七子模块拆解，供后续实施ADR细化，本蓝图不
现在就要求实现：

- **E1 Performance Observer**：持续观察Need理解效果/Goal接受率/Plan激活率
  /Action完成率/Outcome改善率/Replan质量/人工升级率/资源匹配效果/安全事件
  /用户纠正率，回答"系统哪里正在变差"——不是普通BI报表，是Evolution Engine
  的输入信号源。
- **E2 Failure Pattern Miner**：识别重复失败模式/高频退出点/无效Skill/
  错误Planner模式/不合适资源匹配/过度人工升级/低价值AI回答，形成`FailureCluster`。
- **E3 Capability Gap Detector**：把`FailureCluster`转化成`CapabilityGap`
  （例如"无法识别父母双方目标冲突"、"缺乏儿童睡眠相关Skill"、"Planner不会
  判断何时停止AI干预"、"缺乏某地区线下资源"）。
- **E4 Improvement Designer**：根据Gap提出`PolicyCandidate/SkillCandidate/
  PromptCandidate/PlannerCandidate/AgentCandidate/ToolCandidate/
  ResourceStrategyCandidate`。
- **E5 Evaluation Factory**：每个改进候选自动生成`Hypothesis/Baseline/
  Dataset/Replay Cases/Success Metric/Guardrail Metric/Failure
  Conditions`——**Eval-by-Default**，没有Eval的候选不进入下一步。
- **E6 Evolution Governance**：判断变化级别（见第三十一节E0-E5授权分级），
  级别越高需要越强治理，不是所有改进走同一条审批流程。
- **E7 Release & Rollback Controller**：负责`Candidate → Sandbox → Shadow
  → Canary → Production`，以及自动监测/自动降级/人工回滚/版本恢复。

E1-E7整体**没有直接生产发布权**——这条边界（第十四、二十二节已定义）在
七子模块拆解下依然成立：只有E7的"Production"环节实际触发生产变更，且必须
先经过E6的Governance判定，不是任何一个子模块可以单独绕过。

## 三十一、Evolution Gate与自进化分级授权

任何能力升级进入生产前，目标态至少经过：`G0静态校验 → G1单元/契约 → G2
历史回放 → G3黄金家庭E2E → G4安全/治理 → G5影子 → G6金丝雀 → G7生产观察`，
高风险变化再加`人工架构评审/专业评审/Guardian Panel`。这是对第十四节
Governed Self-Evolution流程的具体化Gate序列，跟既有的`release_gate`/
G0-G6纪律（ADR-0162横切纪律）同源，不是重新发明一套。

**自进化分级授权表**（正式冻结方向，具体阈值/流程由实施ADR定稿）：

| Level | 改进类型 | 自动化权限 |
|---|---|---|
| E0 | 文案/提示优化 | 可高度自动 |
| E1 | Skill内容参数 | 自动候选，Eval后发布 |
| E2 | Planner策略 | 必须Release Gate |
| E3 | 新Agent/Tool | 架构+安全审批 |
| E4 | 数据权限变化 | 人工强审批 |
| E5 | 未成年人/医疗/重大决策边界 | 禁止自动升级 |

**越接近现实世界权力，治理越严格**——E5明确"禁止自动升级"，不是"需要更多
审批"，是这张表里唯一一条硬红线，跟第九节"AI cognition不能直接创造业务
事实"、Growth Fiduciary FAIL CLOSED是同一类不可协商的边界。

## 三十二、四个新增顶层平台能力，七大技术Plane

V1原有六大能力（Family World Model / Agent Runtime / Planner / Skill
Runtime / Tool Runtime / Outcome Learning）之外，V1.1目标态新增四个：
**Evaluation Platform / Evolution Engine / Learning Plane / AGI
Governance Control Plane**——合计十二个核心子系统，具体拆解和R2-R10任务
映射是下一步单独产出的《FAMILY AGI PLATFORM V1.1 技术总架构》的工作
（见本文档末尾"后续建议"）。

**七大技术Plane**（目标态总体技术框架，供后续技术架构文档细化）：

```text
EXPERIENCE PLANE     Web/Mobile/Principal/Digital Human
        ↓
FAMILY INTELLIGENCE PLANE   Understand/World Model/Goal/Planner/
                             Agent Runtime/Skill Runtime/Reflection
        ↓
ACTION PLANE         Tool Runtime/Human Gate/Named Action
        ↓
DOMAIN PLANE          Family/Assessment/Journey/Service/Resource/
                       Growth/Action/Identity
        ↓
OUTCOME PLANE         Observation/Measurement/Feedback
        ↓
LEARNING PLANE        Pattern/Outcome Intelligence/Eval Data
        ↓
EVOLUTION PLANE       Gap Detection/Candidate/Evaluation
        ↓
GOVERNANCE PLANE      Safety/Consent/Release/Audit/Rollback
```

`DOMAIN PLANE`对应仓库现有的`backend/domains/*`各域；`ACTION PLANE`对应
ADR-0167的`NamedAction/DomainFact`层；`FAMILY INTELLIGENCE PLANE`对应
ADR-0167的`AgentRun/IntelligenceRun`两层；`LEARNING PLANE`是第二十五节
新增数据平面；`EVOLUTION PLANE`对应第三十节Evolution Engine；
`GOVERNANCE PLANE`横切所有Plane，不是流水线上的一环，是常驻的治理层
（跟ADR-0162 G0-G6横切纪律的定位一致）。

## 三十三、数据价值重新定义：Outcome Data，不是行为数据；且绝不走向监控平台

Family AGI的核心数据资产是`Need/Context/Evidence/Goal/Plan/Intervention
/Action/Outcome/Reflection/Resource Performance`——真正有价值的不是"用户
点击了什么"，是"一个家庭采取什么行动以后发生了什么"，即**Outcome Data**。

**但AGI越强，越必须反向限制数据欲望**——这是必须跟前面所有"学习/进化"
内容同时冻结的红线，不是可选的合规附注：坚持`Need-driven data
collection`而不是`Collect everything`；必须坚持`Family controls data /
Consent is revocable / Purpose is explicit / Unknown is acceptable /
Deletion is real`。`Unknown is acceptable`直接对应第四节Family World
Model的`Unknowns`层——系统宁可承认不知道，也不能靠多采集数据来消灭不确定
性，这是本平台区别于"数据饲料场"型AI产品的关键红线。

## 三十四、商业模式与组织/研发模式的配套升级

**商业模式**：Family更长期卖的是**Family Intelligence Service**——家庭
购买的其实是持续理解/持续规划/持续陪伴/持续资源组织/持续改善，不只是
"解锁更多课程"。这是对第八节四层收入结构的战略升级，不是替代：会员应逐渐
理解为`Family Intelligence Membership`，包含家庭模型/成长计划/法咪莉
陪伴/行动跟进/家庭报告/资源导航/智能调整。**Family Resource Network会
形成第二增长曲线**——随着FamilyNeed增长，更多专业资源加入→更多Outcome→
平台更会匹配→更多家庭加入，这不是流量平台，是**Intelligent Demand
Network**，跟第五节"从用户搜索服务到家庭需求驱动资源"的反转是同一个
判断在增长模型上的表述。

**组织模式**：长期应从"测评团队/课程团队/直播团队/专家团队/社区团队"这类
职能烟囱，逐渐转向`Family Need Domains`（Learning Growth Domain/
Relationship Domain/Emotional Growth Domain）+`Platform Intelligence
Teams`（World Model Team/Planner Team/Skill Platform Team/Outcome
Learning Team/Evolution Team/Safety Governance Team）——**这是组织设计
方向，不是本蓝图授权的组织变更决定**，需要总架构师/业务负责人单独决策，
本节只记录"如果按这个技术架构推进，组织会自然长成什么形状"这个判断。

**研发模式**：从`PRD → 开发 → 测试 → 上线`，升级为`Need → Hypothesis →
Capability Candidate → Eval Design → Implementation → Golden E2E →
Release Gate → Outcome Observation → Evolution`——**Evaluation必须前移
到需求阶段**：不是上线以后才问"效果怎么样"，是开发之前就明确"什么结果证明
这个能力比旧版本更好"。这条纪律跟本会话R0.5全过程反复验证的"反证实验先于
下结论"方法论完全一致，是同一种工程纪律从"调试CI失败"场景扩展到"设计新
能力"场景。

## 三十五、两个必须跑通的Golden E2E（学习闭环 + 自进化闭环）

**Golden E2E一：证明系统真的在学习**，不能只测"能不能完成一次家庭计划"：

```text
FamilyNeed → WorldState v1 → Goal → Plan v1 → Action → Bad Outcome
→ Reflection → WorldState v2 → Plan v2 → Different Action → Better Outcome
```

通过标准：**第二次决策必须因为第一次Outcome而改变**——这是对第三节"Outcome
→Reflection→Replan必须真实改变下一次决策"这条纪律的可测试化，是Loop A是否
真实闭环的验收标准，不是Loop B/C的验收标准（后两者需要更大规模数据，见
第二十四节诚实进度）。

**Golden E2E二：证明系统具有受控自进化能力**：

```text
Skill v1 → Repeated Poor Outcomes → Capability Gap detected
→ Skill v1.1 candidate generated → Historical replay → v1.1 beats v1
→ Safety gate PASS → Human approval → Canary → Production
```

这条跑通，才意味着Family真的具有受控自进化能力——**这是Loop C的验收标准，
是本蓝图目标态里最晚才能验证的一条**，明确标注不是近期工作项。

## 三十六、长期护城河重新定义为七层

对第七、二十节护城河判断的最终归纳：

```text
1 Family Relationship      长期家庭关系
2 Family World Models      长期家庭认知
3 Outcome Intelligence     真实结果学习
4 Skill Network            不断进化的能力
5 Resource Network         社会资源网络
6 Evaluation System        知道什么是真的更好
7 Evolution Engine         持续产生下一代能力
```

第6、7层是最难复制的两层，也是本平台跟"普通AI家庭产品"的真正代际分界——
前5层任何有资源的竞争者理论上都能追赶，第6、7层需要真实规模的Outcome数据
+长期的Eval纪律积累，不是靠融资或买流量能跳过的阶段。

## 三十七、最终战略定义（V1.1）

> **FAMILY是一个从孩子成长切入、以家庭为基本需求单位、连接家庭与社会资源，
> 并依托AGI持续感知、理解、规划、行动、学习和受控进化的Family Intelligence
> Platform。**

浓缩：**FAMILY = An Intelligent Platform That Grows With Families.**
中文：**FAMILY——一个与家庭共同成长、并持续自我进化的智能平台。**

五年后的终局不是一个App，而是**Family Intelligence Infrastructure**——
家庭→Family Intelligence→（教育/健康/关系……）→（老师/医生/专家……）→
（学校/社区/服务机构……），Family AGI是中间的智能协调层：理解家庭、组织
资源、改善结果、持续学习。

**最终判断标准**（不是功能数量）：

1. 是否越来越懂每一个家庭？
2. 是否越来越知道什么方法真正有效？
3. 是否越来越善于组织社会资源解决家庭需求？
4. 平台本身是否能够持续、安全地变得更好？

四个答案都是"是"，Family才真正成为**Family AGI Ecosystem**——一个会学习、
会成长、会受控进化的家庭智能生态系统，不再是一家传统家庭教育互联网公司的
产品。

## 三十八、当前诚实进度（对照本蓝图目标态，含V1.1全部新增内容）

按ADR-0167已有的"五级AGI演进"诚实定位（介于AGI-0与AGI-1之间）复核：

- **Family World Model（第四节）**：未建成。仅有`Growth Graph`
  （hypothesis/action事件outbox）雏形，远未到"持续演化的家庭数字模型"，
  `Unknowns`层完全未设计。
- **AGI内核闭环（第三节）**：`VerticalFamilyGrowthRuntime`的`revise()`/
  `reflect()`是Outcome→Reflect→Replan链条的唯一真实雏形，尚未验证"结果
  真实改变下一次决策"这条纪律在生产路径上闭环。
- **FamilyNeed/N0-N8（第五节）**：`FAMILY_NEEDS_PLATFORM_TARGET_MODEL.md`
  是设计规范，代码侧的完整落地程度需要按该文档自己的"建设顺序"单独核实，
  本蓝图不重复评估。
- **Family Resource Network（第五节）**：FGCN雏形已有（P0交付、真实
  PostgreSQL验证），规模化的Distribution/Demand引擎按
  `family-allocation-platform-mechanisms`记录仅建了Distribution雏形。
- **Family Outcome Intelligence飞轮（第七节）**：完全未开始——需要真实
  规模家庭数据，是终局判断，不是近期路线图项。
- **Learning Plane / LearningSignal（第二十五节）**：未建成。当前没有任何
  Action/Skill契约包含`Expected Outcome/Success Criteria/Stop Rules`这类
  字段，Outcome的观察和回读目前是VerticalFamilyGrowthRuntime内部的临时
  逻辑，不是独立、一等的LearningSignal对象。
- **版本化Goal/Plan/Skill、Temporal World Model、Confidence（第二十六节）**：
  未建成。当前数据模型没有对象携带`confidence`/`contradictions`字段，
  没有Plan/Skill的版本链路，World Model是覆盖式而非时序化。
- **Family Pattern Library / Outcome-aware Resource Orchestration
  （第二十七、二十八节）**：未建成，需要L2跨家庭学习先跑起来才有意义，
  是Loop B之后的能力，当前Loop B本身未开始。
- **Family Evolution Engine E1-E7（第三十节）**：完全未建成，包括
  Performance Observer这类最基础的观测子模块——当前没有系统性收集
  Need理解效果/Goal接受率/Plan激活率等指标的机制。
- **Evolution Gate / 自进化分级授权（第三十一节）**：未建成，当前没有任何
  自动生成的改进候选需要走这套Gate，是Loop C的前置条件，Loop C整体未开始。
- **两个Golden E2E（第三十五节）**：均未建成。Golden E2E一（学习闭环）
  依赖的"第二次决策因第一次Outcome改变"这条断言，目前没有对应的可执行
  测试；Golden E2E二（自进化闭环）依赖Evolution Engine，尚不存在。

**这次V1.1修订，诚实地说，绝大多数新增内容都是"未建成的目标态"**——这是
预期之内的，本蓝图的作用是提供长期架构坐标，不是宣称当前系统已经具备这些
能力。跟第三节判断一致：当前系统介于AGI-0与AGI-1之间，Loop A（家庭成长
循环）都还没有在生产路径上完整验证"结果真实改变下一次决策"，遑论Loop B/C。

**下一步建议**（不在本蓝图授权范围内立即执行，供总架构师后续单独排期）：

1. 把"孩子成长×家庭关系"这条第一阶段纵向场景，按本蓝图第三、四节的AGI内核+
   World Model目标态，重新审视`FAMILY_NEEDS_PLATFORM_TARGET_MODEL.md`第6节
   "建设顺序"是否需要insert一步"Family World Model最小雏形"，作为N0-N8之前
   的地基——这是否要做、何时做，需要总架构师单独决策，本蓝图只负责标注这个
   差距的存在，不擅自排入执行计划。
2. 本蓝图末尾提出的"把V1.1拆成七大技术Plane+十二个核心子系统+四十项核心
   能力+R2-R10任务映射，产出《FAMILY AGI PLATFORM V1.1技术总架构》"是一份
   独立的、体量同样很大的后续文档，本蓝图只记录这个意图和拆解方向（第三十二
   节已给出七大Plane/十二子系统的初步清单），不在本次会话内展开写——这份
   技术总架构文档需要总架构师单独确认排期后再启动，因为它将直接约束
   `backend/`代码结构，跟本蓝图"纯战略定位、不即时约束代码"的定位不同，
   混在一起写会让读者分不清"这是愿景"还是"这是马上要改的代码规范"。
