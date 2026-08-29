---
id: RES-MARKET-001
title: 贝壳 ACN 机制可迁移性研究（主题 3 重跑）
type: research
status: draft
version: 1.0
owner: chief-architect
created: 2026-08-29
updated: 2026-08-29
canonical: false
supersedes: null
superseded_by: null
---

```text
STATUS: RESEARCH_ONLY
NOT_CANONICAL: TRUE
DO_NOT_USE_AS_DESIGN_BASIS: 本文件是证据，不是决定。
晋升路径见 docs/12_governance/DOCUMENT_GOVERNANCE.md §8.2：Research → ADR → Canonical。
未经 ADR，本文任何结论不得写入 docs/01_strategy/ 或任何 canonical 文档。
```

# 贝壳 ACN 机制可迁移性研究

**被检验的对象**：`docs/01_strategy/COMMERCIAL_VALUE_STRATEGY.md` 第 2 节的三层价值网络，其中层 2（人机协作层）声称 "FGCN 机制（一客一案/一案一管家/任务化交付贡献凭证）在这一层的价值最大"，并称其 "解决的是'如何用有限的人力资源，可信、可追溯地承接大量个性化服务需求'这个真实运营问题，不是花架子"。

**上一轮零通过的原因（本轮的方法论修正）**：上一轮只检索了 ACN 的宣传性描述（"十个角色""合作共赢"），拿到的是概念介绍而非可 falsify 的机制细节，因此没有任何声明能通过对抗性核验。本轮改为：**先锁定一手来源（KE Holdings 向 SEC 提交的 20-F 年报原文），再用中文二手来源补充官方文件不披露的操作细节，并明确区分两者的证据强度。**

---

## 0. 本轮实际使用的一手来源

| 来源 | 类型 | 用途 |
|---|---|---|
| KE Holdings Inc. FY2025 Form 20-F（`https://investors.ke.com/system/files-encrypted/nasdaq_kms/assets/2026/04/24/7-27-29/BEKE%202025%2020-F.pdf`，309 页，本轮已本地全文抽取） | **一手**（SEC 年报，法律责任下的陈述） | ACN 机制定义、佣金分账财务规模、风险因素、经纪人/门店口径 |
| KE Holdings F-1 招股书（`https://www.sec.gov/Archives/edgar/data/1809587/000091205720000127/filename1.htm`） | **一手** | ACN 三项 "reinvention" 的原始表述 |
| 界面新闻 2018-12-25 报道贝壳陪审团（`https://www.jiemian.com/article/2743089_qq.html`） | 二手（媒体，含公司发布的具体数字） | 争议裁决机制的规模与流程 |
| Runwise 案例分析（`https://runwise.co/dtc/platform/54017.html`） | 二手（案例整理） | 十角色分账比例区间 |
| 新华网 / 澎湃 / 21 财经 2021-05 系列报道 | 二手（媒体） | 监管关注与 "二选一" 争议 |

**说明**：中国境内 ACN 佣金分配的**官方规则原文（一市一策的具体比例表）不对外公开**，本轮未能获得任何一手来源。所有具体百分比只能标 medium/low 置信度。这一点如实标注，不用推测补齐。

---

## 1. ACN 到底是什么：一手来源的原始定义

### 声明 3.1｜ACN 的核心是"角色切分 + 自动分账"，且分账明确**不由参与者协商决定**
**置信度：high（一手，公司年报原文）**

FY2025 20-F 原文（Business 章节，"Agent Cooperation and Operational Rules"）：

> "We partition a complete existing home transaction, including existing home sales and rentals, into different steps and allow multiple agents cross-brand and cross-store to cooperate in one transaction and share commissions based on their roles, through which the agents can become more specialized in their roles."

以及决定性的一句：

> "Under ACN, commission is allocated automatically based on agents' various roles in a housing transaction, **and is not based on negotiations among agents**."

同一节还说明 ACN 是 "protocols and practices to specify roles in cooperative housing transactions and prescribe agents' rights and obligations through commission allocation mechanism"，并列出三项 "reinventions"：(i) 信息与资源共享打破信息孤岛，(ii) 分配协作角色实现跨店跨品牌协作，(iii) 建立专业网络。

**这条声明为什么可 falsify**：它是一个关于机制设计的硬断言——分账是**规则驱动的自动计算**，不是谈判。如果 ACN 实际靠人工议价，这句在 SEC 年报中的陈述就构成虚假陈述。这也是对 FGCN 最有价值的一条借鉴：**"贡献确认按规则自动结算"是机制成立的核心，不是可选优化项。**

### 声明 3.2｜分账通过平台自有支付系统结算，平台是 principal agent（掌握定价权）
**置信度：high（一手，20-F 会计政策章节）**

20-F "Revenue recognition" 章节原文：

> "For each successful transaction facilitated through the platform, the platform will calculate commissions for each participating agent in accordance with the platform agreements and settle them through the platform's payment system."

以及关于 principal agent 判定：

> "the Group is considered to be the principal agent as it has the right to determine the service price and to define the service performance obligations, it has control over services provided and…"

**含义（对 FGCN 关键）**：ACN 不是一个"记账建议系统"，它是**资金通道 + 定价权的持有者**。分配规则之所以有强制力，是因为钱从平台流出，平台可以单方面执行规则。任何只做"贡献记录"但不控制资金流的类 ACN 设计，其规则不具备同等强制力。

### 声明 3.3｜分账成本规模：2025 年 commission-split = RMB 208.7 亿，占净收入 22.1%
**置信度：high（一手，20-F 财务报表）**

| 年度 | Commission — split（人民币千元） | 占净收入 |
|---|---|---|
| 2023 | 20,419,577 | 26.3% |
| 2024 | 22,766,957 | 24.4% |
| 2025 | 20,873,405（US$2,984,857 千） | 22.1% |

同期另有 "Commission and compensation — internal" 2025 年 17,656,184 千元（18.6%）。2025 年净收入合计 94,580,205 千元。

**含义**：分账不是边缘机制，它是平台第一大成本项（22.1% of revenue）。一个协作分账网络的运行成本是**收入的两成量级**，这是评估 FGCN 经济可行性时必须计入的量级参照，而不是"加一个分配模块"的边际成本。

---

## 2. 十角色与分账比例（证据强度显著较弱）

### 声明 3.4｜角色切分为房源方 5 + 客源方 5，客源成交人拿全佣约三成
**置信度：medium（二手案例整理；一手年报只说 "various roles"，从不列举角色名或比例）**

据 Runwise 案例整理：

- **房源方 5 角色**（合计约四成佣金）：房源录入人、房源维护人、房源实勘人、委托备件人、房源钥匙人
- **客源方 5 角色**（合计约五成多）：客源推荐人、客源成交人（约占客源方的 60%，即**全佣 30% 出头**）、客源合作人、客源首看人、交易/金融顾问

同一来源明确指出：分配比例 **"每个城市都不一样"，"贝壳基本是一市一策"**，比率是长期实践检验得出但 **"并非固定值"**。

**诚实标注**：KE Holdings 的 F-1 与 20-F **均不披露角色名称与分账百分比**。本轮试图从一手文件获取该表格失败——F-1 摘要把细节推到 Business 章节，而 Business 章节的公开文本只给出机制性描述。因此 "十角色 + 具体比例" 这条**不满足一手来源要求**，标 medium，且不应作为 FGCN 参数设计的直接依据。

**对 FGCN 更重要的一条推论**："一市一策、比例非固定" 本身是可 falsify 的设计事实——它说明 **ACN 的分账参数是运营可调的配置项，不是写死的常量**。这与 AiFamily 宪章"生成式优先、硬编码只留护栏"的取向一致；如果 FGCN 把分配比例写进代码常量，就复制了 ACN 明确避开的做法。

### 声明 3.5｜"首看人"角色的存在目的是防撬单，即机制承认内部争抢是真实威胁
**置信度：medium（多个二手来源一致；一手年报以风险因素间接印证，见声明 3.8）**

多个独立中文来源（Runwise、mworkspace、阿里云创新中心）一致描述"客源首看人"角色的设计目的是"保护首看"、预防抢单撬单。

**含义**：ACN 不是"合作氛围好"所以成立，而是**先假定参与者会互相撬单，再用角色确权把撬单的收益归零**。这是对 FGCN 最直接的设计借鉴，也是对 `COMMERCIAL_VALUE_STRATEGY.md` 层 2 表述的一处修正建议：该文档把 FGCN 描述为解决"如何用有限人力可信承接需求"，但 ACN 的证据显示机制的**第一性问题是参与者之间的零和争抢**，"可信承接"是解决争抢之后的副产品。

---

## 3. 争议裁决：贝壳陪审团

### 声明 3.6｜争议裁决由跨品牌陪审团做终局裁定，2018 年底已覆盖 56 城 / 25 品牌 / 1832 名陪审员
**置信度：medium-high（二手媒体，但含公司发布的精确数字与流程描述）**

界面新闻 2018-12-25 报道：

- 规模："全国已有 56 个城市成立了贝壳陪审团，陪审员来自 25 个经纪品牌，陪审员达 1832 人"，并计划 2019 年扩至 100 城
- 遴选："陪审团成员由 ACN 网络内的所有成员自主报名，定期选拔，并进行规则和文化考核"，有培训/考核/淘汰与激励机制
- 审理："遵循**利益规避原则**从陪审员池中选择陪审员，按照严格的投票流程与决议规则进行独立裁定"
- 权限：被描述为 "最终判定部门，拥有最高裁定权"，处理经纪人之间以及经纪人与非业务判定部门/合作公司之间的争议

另据检索到的题库类材料，规则体系含"红线/黄线"分级与积分处罚（例："房源方无正当理由阻碍他人出房为黄线行为，扣 6 分"）。**该积分条目仅有单一低质量来源（题库网页），标 low，仅作为"存在积分制处罚"的弱旁证，不采信具体分值。**

**含义（对 FGCN 关键且 AiFamily 目前完全缺失）**：ACN 的分账规则能被遵守，不只因为规则自动执行，还因为存在一个**跨主体、利益回避、有终局效力的争议裁决机构**。`COMMERCIAL_VALUE_STRATEGY.md` 第 5 节把"争议处理"列为 V1.1 第六章保留内容而未展开；本研究认为这是被低估的一环——**没有裁决机构的分配规则，在第一次边界争议时就会失效**。

---

## 4. 批评性视角与失败教训（上一轮缺失的部分）

### 声明 3.7｜ACN 规则的执行力是公司自认的重大风险，具体风险行为是"绕过平台"
**置信度：high（一手，20-F Risk Factors 原文）**

20-F 风险因素原文：

> "Although we have implemented a comprehensive rules and protocols in ACN, we cannot assure you that all aspects of our ACN rules will be satisfactorily implemented in each housing transaction on our platform. With the increasing number of participating real estate brokerage brands and agents who were not previously familiar with ACN rules, it may be difficult for us to effectively monitor and control these brands and agents… If violations of ACN rules or other inappropriate actions occur, **such as circumventing our platform to facilitate transactions that are required to be partitioned according to ACN rules**, and if we fail to effectively prevent non-compliance or discipline the responsible brands or agents, the effectiveness of our ACN system may be diminished and other agents on our platform may be less willing to follow the rules…"

**这是本轮最有价值的一条负面证据**。它给出了一个具体的、可 falsify 的失效模式：**参与者把本该走平台分账的交易挪到平台外完成（绕单）**，且公司明确承认这会引发"其他人也不愿遵守规则"的连锁崩塌。它同时揭示了机制成立的一个隐含前提：**平台必须能观测到交易是否发生**。

### 声明 3.8｜"活跃"口径本身暴露流失：445,000 活跃经纪人 vs 523,000 在册经纪人（缺口约 15%）
**置信度：high（一手，20-F 口径定义 + 数据）**

20-F 披露（截至 2025-12-31）：

- 活跃门店 约 58,000 家；**活跃经纪人 超过 445,000 人**；覆盖 279 个经纪品牌
- 同一日期：**在册经纪人 约 523,000 人；在册门店 约 61,000 家**
- 链家自营：活跃经纪人超 90,000 人，活跃门店约 4,900 家

而"活跃经纪人"的定义是一个**排除式定义**：

> "excluding the agents who (i) delivered notice to leave but have not yet completed the exit procedures, (ii) have not engaged in any critical steps in housing transactions… during the preceding 30 days, or (iii) have not participated in facilitating any housing transaction during the preceding three months"

**含义**：约 78,000 名在册经纪人（约 15%）不满足活跃门槛——要么已递交离职，要么 30 天内无关键动作，要么 3 个月内未参与任何成交。ACN 的角色分工要求参与者持续在网，而**近六分之一的注册参与者实际处于不活跃状态**。这是对"网络效应自动成立"叙事的一条硬约束反证。

同期 GTV **下降**：从 2024 年 RMB 33,494 亿降至 2025 年 RMB 31,833 亿（20-F 明确列为"历史增长不代表未来"的风险因素）。ACN 机制成熟并不豁免市场周期。

### 声明 3.9｜监管关注真实存在，但 2021 年"反垄断调查"报道被公司否认为假消息
**置信度：medium（二手媒体，且结论是"未证实"）**

2021-05 多家媒体（引 36 氪/路透）报道市场监管总局对贝壳启动反垄断调查，聚焦"二选一"独家协议；公司随后回应称未收到任何调查通知，多家媒体（网易、21 财经）确认为"乌龙事件/假消息"。新华网 2021-04 文章讨论平台变大后"滥用市场支配地位"的一般性担忧，属分析而非事实认定。华西证券材料提及业主称受到签署"VIP 服务协议"独家条款的压力。

**诚实标注**：本轮**未找到任何针对贝壳 ACN 的已生效行政处罚或正式立案的一手证据**。因此"ACN 招致监管处罚"这一命题**未获证据支持**，不采信。但 20-F 确实披露公司受多项法律（含反垄断法、2025-10-15 生效的修订版反不正当竞争法）约束，且修订版新法要求平台经营者"在服务协议和交易规则中明确公平竞争规则，建立不正当竞争举报、投诉、争议解决机制"——**这一条反向印证了声明 3.6 的争议裁决机构在中国法下已是平台的合规义务，不是可选项**。

### 声明 3.10｜佣金费率受政策指导下调，且已在部分城市执行
**置信度：high（一手，20-F）**

20-F 原文提及监管"propose to guide both sellers and buyers of transactions to share the brokerage service fee"，并给出具体执行：

> "in September 2023, we reduced commission rate for existing home transactions in Beijing and the fee is split equally between sellers and buyers."

**含义**：分账机制的**分母（总佣金池）是外部可压缩的**。一个把参与者激励完全建立在"从固定比例佣金池中切分"之上的机制，对费率下调没有缓冲。

---

## 5. 核心问题：ACN 的成立前提，在"家庭教育长期服务"场景是否具备？

这是 T-09 任务卡指定的关键问题。本轮从一手来源提炼出 ACN 成立的前提，逐条对照家庭教育长期服务场景。

### 声明 3.11｜公司自述的第一前提是"真房源"，即**可独立验真的标的物**
**置信度：high（一手，20-F "Authentic Property Listings" 原文）**

> "We believe that **authentic property listing is the foundation of agent cooperation** as effective collaboration among agents require valid and reliable listing information."

验真手段是具体的："We monitor and verify the authenticity of property listings on our platform and timely update or delete unqualified listings through **customer callback, physical visits and AI**." 底层还有 "Housing Dictionary"（F-1 时点覆盖 2.15 亿套房屋）作为标准化标的物字典。

### 前提对照表

| ACN 成立前提（来源） | 房产交易是否具备 | 家庭教育长期服务是否具备 | 判定 |
|---|---|---|---|
| **A. 标的物可独立验真**（声明 3.11，一手） | 具备。房子客观存在，可实地核验、可建字典 | **不具备**。"这个家庭的成长需要"无法实地核验，没有客观标的物字典。AiFamily 的对象是家庭状态与关系，本质上是解释性的（宪章 R9 明令 Perspective≠Fact） | **缺失，且不可通过工程手段补齐** |
| **B. 交易可被平台观测（否则绕单）**（声明 3.7，一手） | 具备。过户与资金监管使成交事件可观测 | **部分具备**。线上任务/预约可观测；但"顾问私下继续辅导这个家庭"完全不可观测，绕单成本极低 | **弱** |
| **C. 步骤可切分为可验收动作**（声明 3.1，一手） | 具备。录入/实勘/带看/签约都有离散完成信号 | **部分具备**。ServiceTask VERIFIED 是离散信号；但"陪伴""关系改善"没有离散完成时点 | **部分** |
| **D. 平台掌握资金通道与定价权**（声明 3.2，一手） | 具备。平台为 principal agent | **当前不具备**。`COMMERCIAL_VALUE_STRATEGY.md` 第 2 节层 3 已核实：商城链路被 `requireDevSyntheticTestLoop()` 限定在 DEV/TEST，`fixture_only=true`，价格是前端派生文案，不接真实支付 | **缺失（当前）** |
| **E. 单笔标的额足以支撑多角色分账**（声明 3.4 推论） | 具备。单笔佣金可养 10 个角色的分成 | **不具备/存疑**。21 天体验营/单次咨询的客单价能否切成 10 份仍有经济意义，本轮**无证据**。这是需要 AiFamily 自己用真实定价数据回答的问题 | **未获证据支持** |
| **F. 存在跨主体终局争议裁决**（声明 3.6，二手；且为中国法下平台义务，声明 3.9） | 具备（陪审团 1832 人规模） | **不具备**。AiFamily 无任何争议裁决设计；`governance/ADR/` 为空 | **缺失，但可建** |
| **G. 参与者规模足够形成网络**（二手，Runwise "规模效应"） | 具备（44.5 万活跃经纪人/279 品牌） | **不具备**。当前无真实服务者网络 | **缺失（阶段性）** |
| **H. 结果不用于个人扣罚**（AiFamily 自有原则，非 ACN 前提） | 不适用 | 具备。战略原则 4 明确"成长结果用于改进方案，不直接作为个人扣罚或分佣依据" | **AiFamily 更严，构成额外约束** |

### 声明 3.12｜结论：ACN 的前提在家庭教育长期服务场景**不完整具备**，其中前提 A 结构性不可补齐
**置信度：medium-high（推论，但每一步都锚定上表的一手证据）**

**最关键的一条**：ACN 的公司自述第一前提是"真房源是协作的基础"。家庭教育服务不存在等价的可验真标的物——而且这不是 AiFamily 还没做，是**宪章 R9 主动禁止的方向**（不做总分、不做排名、AI 输出不直写 canonical 事实、Perspective≠Fact）。这意味着 FGCN 不能靠"给家庭状态验真/打分"来复刻 ACN 的地基。

**但这不等于 FGCN 无效**。上表显示可迁移的是 C（任务可验收切分）、D（资金通道，待建）、F（争议裁决，可建）、B 的线上部分，而 `COMMERCIAL_VALUE_STRATEGY.md` 第 4 节战略原则 3 已经写的"服务分工按任务配置，收入分配按**已验收贡献**确认"恰好就是把地基从"标的物验真"换成了"**动作验收**"——这是一个正确的替换方向，本研究支持它。

**对现有战略表述的一处修正建议（需走 ADR）**：`COMMERCIAL_VALUE_STRATEGY.md` 第 2 节称 FGCN 在层 2 "价值最大"且"不是花架子"。基于本轮证据，更准确的表述应是：FGCN 的**贡献确认与自动分账**部分有强外部证据支撑（声明 3.1/3.2/3.3），但其成立还依赖两项当前完全缺失的前提——**平台资金通道（D）与争议裁决机构（F）**——在这两项落地前，FGCN 只是记账约定，不具备 ACN 那种规则强制力。

---

## 6. 未获证据支持的问题（如实列出，不填推测）

1. **ACN 官方分账比例表**：一手来源不披露，中国境内亦无公开规则原文。声明 3.4 只能标 medium。
2. **贝壳经纪人收入争议的量化证据**：未找到可信的一手数据（如公开的收入分布、劳动仲裁统计）证明 ACN 导致经纪人收入下降或纠纷增加。检索到的相关内容均为观点性讨论。**"ACN 引发经纪人收入争议"这一命题本轮未获证据支持。**
3. **陪审团裁决量与推翻率**：仅有 2018 年的规模数字（1832 人/56 城），**没有任何年度受理案件数、裁决结果分布或被推翻比例的数据**。因此无法评估该机构的实际有效性，只能确认其存在。
4. **家庭教育场景的分账经济性（前提 E）**：单笔服务客单价能否支撑多角色分账，本轮完全无外部证据。这是 AiFamily 必须用自己的真实定价与成本数据回答的问题，不能从 ACN 类推。
5. **ACN 相关的已生效行政处罚**：未找到。2021 年反垄断调查报道已被公司否认且媒体确认为假消息。

---

## 7. 建议走 ADR 的结论（本文件不做决定）

| 建议进入 ADR 的结论 | 依据声明 | 影响的 canonical 文档 |
|---|---|---|
| 贡献分账必须**规则自动结算、禁止参与者协商**，且分配参数为运营可配置项而非代码常量 | 3.1、3.4 | `docs/01_strategy/COMMERCIAL_VALUE_STRATEGY.md` §2/§5 |
| FGCN 的强制力依赖**平台资金通道 + 争议裁决机构**；两者落地前 FGCN 只是记账约定，战略表述应据此下调 | 3.2、3.6、3.9、3.12 | 同上 |
| FGCN 地基应显式声明为"**动作验收**"而非"标的物验真"，并写明为何不能复刻 ACN 的验真路径（R9 冲突） | 3.11、3.12 | 同上 + `docs/05_ai/AI_NATIVE_PRINCIPLES.md` 交叉引用 |
| 必须为 FGCN 设计**绕单可观测性**与相应处置，否则复刻 ACN 自认的首要失效模式 | 3.7 | 同上；可能需 `docs/04_domains/` 的 Service 域不变量 |
| 分账机制的成本量级参照为**收入两成级**，须在商业模型中显式计入 | 3.3 | `docs/02_business/` |

---

## 8. 声明汇总（含置信度与来源类型）

| # | 声明 | 置信度 | 来源类型 |
|---|---|---|---|
| 3.1 | 角色切分 + 自动分账，明确不由参与者协商 | high | 一手 20-F |
| 3.2 | 平台自有支付系统结算，平台为 principal agent 掌握定价权 | high | 一手 20-F |
| 3.3 | 2025 分账成本 RMB 208.7 亿 = 净收入 22.1% | high | 一手 20-F |
| 3.4 | 房源方 5 + 客源方 5 角色；成交人约占全佣 30%+；一市一策非固定 | medium | 二手 |
| 3.5 | "首看人"角色为防撬单而设 | medium | 二手（多源一致） |
| 3.6 | 跨品牌陪审团终局裁决，2018 年 56 城/25 品牌/1832 人，利益回避 | medium-high | 二手（含公司数字） |
| 3.7 | 规则执行力为自认重大风险；具体失效模式是绕过平台 | high | 一手 20-F |
| 3.8 | 445,000 活跃 vs 523,000 在册（约 15% 缺口）；2025 GTV 下降 | high | 一手 20-F |
| 3.9 | 监管关注存在；2021 反垄断调查报道被否认；新反不正当竞争法要求平台建争议解决机制 | medium | 二手 + 一手 20-F（法规部分） |
| 3.10 | 佣金费率受政策指导下调，2023-09 北京已执行 | high | 一手 20-F |
| 3.11 | 公司自述第一前提是"真房源是协作的基础"，验真靠回访/实地/AI | high | 一手 20-F |
| 3.12 | ACN 前提在家庭教育场景不完整具备，前提 A 结构性不可补齐 | medium-high | 推论（锚定上述一手证据） |
