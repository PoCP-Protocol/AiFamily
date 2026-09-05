---
id: AI-GENERATIVE-ARCH-001
title: AiFamily 生成式系统架构 —— 生成什么、不生成什么、以及必须删掉什么
type: specification
status: draft
version: 0.1
owner: chief-architect
created: 2026-08-29
updated: 2026-08-29
canonical: false
supersedes: null
superseded_by: null
---

# 生成式系统架构

```text
DOC_KIND = SPECIFICATION / TARGET_STATE
canonical: false —— 本文件描述"应该建成什么"。现状在 docs/00_system/CURRENT_*.md。

本文件的依据是**一手材料**，不是二手摘要：
  docs/01_strategy/source_materials/ 三份（白皮书 546 行 / 宣发 PPT 398 行 / 合作方案 108 行）
  docs/99_archive/2026/strategy/Family家庭教育成长平台实施方案_V1.1.txt（382 行，ARCHIVED，
    按 R13 作为**原始设计意图的证据**使用，不作为当前真相）
  frontend/mobile/app/ui/UI-02..34 + app/(tabs)/index.tsx（34 屏，最具体的产品规格）
  contracts/openapi/UI_API_ENDPOINT_INVENTORY.md / DEV_SYNTHETIC_FIELD_ANALYSIS.md
```

## 0. 三个必须先纠正的前提（一手材料实证）

这三条推翻了此前若干设计文档的依据，先写在最前面。

### 0.1 「主要矛盾」没有一手来源

四份一手材料全文检索：**"主要矛盾" 零命中，"干预" 零命中，"成长问题建模" 零命中。**

而 `backend/domains/product_intelligence/domain/entities.py` 有 `ContradictionModel`，
ADR-0015 把 `Problem → Hypothesis → Contradiction → Value Architecture → Strategy`
确立为主链条。**这条链的中间环节不是业务方给的，是二手摘要引入的。**

一手材料里最接近的表述是**问题分类**而非矛盾分析：
- 白皮书第 38-46 行：「学习焦虑 / 关系焦虑 / 陪伴缺口」三类需求
- 白皮书第 192-193 行：「高频痛点——亲子沟通、学习习惯、手机管理、自驱力不足」
- 白皮书第 64 行（Word V1.1）：「AI 诊断画像：形成**可解释的家庭画像、优先级和不确定性说明**」

**注意最后一条的用词**：原始设计要的是「优先级 + 不确定性说明」，**不是「主要矛盾」**。
这两者的工程含义差别很大：
- 「优先级排序 + 不确定性」= 对多个假设排序并诚实标注置信度 → **可实现、可评估、可回退**
- 「识别主要矛盾」= 断言存在唯一核心机制并找到它 → 隐含一个未经检验的理论主张

**裁决建议**：按一手材料的用词实现 —— `hypotheses[]` 带 `priority_rank` +
`uncertainty` 字段，**不新建 `PrimaryContradiction` 一等实体**。
这与 `AI_ARCHITECTURE.md` §3.3 已有的「增量优先于新建对象」纪律一致，
也与 ADR-0015 补记的施工约束一致。若要保留「主要矛盾」概念，须先向业务方确认它是
团队既有共识还是转述引入，**并出 ADR 说明其来源**。

### 0.2 FGCN 只存在于一份已归档文件，且零代码

「FGCN」「ACN」「一客一案」在**三份 PPT 中零命中**。
它只存在于 Word V1.1（`STATUS: ARCHIVED` / `DO_NOT_USE_FOR_IMPLEMENTATION: TRUE`），
但在那里设计得极完整（第 75-102、227-310 行）：

```text
ServiceBlueprintVersion → ServiceCase → ServiceTask → TaskAssignment
  → ServiceContribution → AllocationStatement
+ 100 单位案件级影子分配（幂等、行合计严格 100）
+ 资源槽位 / 准入硬门槛 / 质量池 HELD→RELEASED
+ 一客一案、一案一管家、一次交付一凭证
```

**全仓库对 `ServiceCase` / `ServiceTask` / `TaskAssignment` / `ServiceContribution` /
`AllocationStatement` / `CaseAccessGrant` 检索：零命中。**
而现有 `backend/domains/service` 实现的是另一套心智模型
（`ServiceProvider → ServiceOffering → AvailabilitySlot → BookingRequest → ServiceRecord`，
即"挂牌—预约—履约"）。

**这是两套不同的心智模型，不是一套的不同完成度。** 融合或替换需要 ADR，
不能当作"扩展现有 service 域"来做。本文件不裁决它，只记录这个事实必须被显式处理。

### 0.3 红线在原始设计里就有，但产品已经违反了它

Word V1.1 自己写下了红线（原话）：
- 第 351 行：「**不得以孩子单一分数代替结果**」
- 第 213 行：「不承诺不可控结果、**不过度依赖孩子评分**」
- 第 128 行：「质量**不是一个满意度分数**，而是一组可以运营的证据」
- 第 33 行：「成长结果用于改进方案，**不直接作为个人扣罚或分佣依据**」

所以 R9 不是治理层发明的，是**原始设计意图**。这一点应当被明确记录，因为它使 R9
从"工程洁癖"变成"业务方原本的要求"。

**但 UI 已经违反它**：

| 位置 | 内容 |
|---|---|
| `UI-03.tsx:23` | `overall_score: number` |
| `UI-03.tsx:18` | `peer_reference: number` —— 同伴基准 |
| `UI-03.tsx:333` | 雷达图用橙色多边形画出 `peer_reference`，与家庭自身数据**并排对比** |
| `UI-03.tsx:259, 343` | 大字号渲染 `overall_score`，标签「参考分」 |
| `UI-06.tsx:55`、`UI-10.tsx:47`、`UI-18.tsx:87` | `Lv.3` 等级徽章，**纯前端写死，从不连后端** |
| `UI-29` | 「成长成果」标题 + 三指标 + 环形进度 |

`score_boundary: "SUPPORT_ORIENTATION_SCORE_NOT_CHILD_DIAGNOSIS_OR_RANKING"`
是一个**字符串标签，不是结构性阻止**。

**这是「事后加免责声明」而非「从架构上消除歧义」。**
并且它暴露了现有护栏的盲区：`tests/architecture/test_r9_value_layer_boundary.py`
的类名维度判据也拦不住它 —— 字段叫 `score`，而承载它的类不叫 `Family*`。
**护栏装在了想得到的地方，没装在真正会被违反的地方。**

## 1. 生成式的定义：这个系统里"生成"指什么

「生成式优先，硬编码只留护栏」若不落到具体判据，会变成口号。本文件的判据：

```text
生成的产物必须是**结构化领域对象**，不是"给某个屏幕的一段文案"。

  ✅ 生成 GrowthHypothesis{statement, evidence_refs[], priority_rank, uncertainty}
  ❌ 生成 "UI-03 第二段的那句话"
```

理由有三，第三条最实际：
1. 结构化产物可校验（`model_gateway` 已强制 `output_schema` 必填 —— 不能校验的网关无法 fail-closed）。
2. 结构化产物可携带 provenance，因此可解释（PIPL 第 24 条）与可归因（飞轮的前提）。
3. **面向屏幕生成会把 UI 布局烧进模型契约**。34 屏会改，模型契约不该跟着改。

## 2. 三个桶：生成 / 保留写死 / 必须删除

这一节是本文件最可执行的部分。34 屏的审计给出了完整清单，
而关键在于**它不是两个桶而是三个** —— 第三个桶此前没人命名。

### 2.1 桶 A：应当生成（现在是硬编码，每一条都是一个本该发生生成的位置）

| 位置 | 现状 | 应生成为 |
|---|---|---|
| `UI-04.tsx:38-50` | 90 天计划四周标题写死（「关系破冰」「行为训练」…） | `JourneyPlan.phases[]`，由该家庭的 Context 生成 |
| `UI-04.tsx:219-224` | `planIsActive` 时硬编码「3」「12」「36h」 | 从真实任务与记录派生（**派生不是生成**，见 §7） |
| `UI-09.tsx:104-107` | 今日任务第 2/3 条固定（「记录一次家庭互动」…） | `DailyAction`，按家庭当前阶段与上次结果生成 |
| `UI-10.tsx:15-20` | 儿童端四张活动卡固定文案 | `ChildActionPrompt`，且**须过未成年人安全策略** |
| `UI-10` 的 `shared_action` | 来自 `GROWTH_FOCUS_CONTENT` 静态字典模板拼接 | 同上。这是 `AI_NATIVE_PRINCIPLES.md` §4 反面清单第 1 条的活标本 |
| `UI-01.tsx:22-34` | `QUICK_ENTRIES` / `RECOMMENDATIONS` 默认文案 | `Recommendation`，带 `why_this` 与 `limitations`（UI-01 的远端契约已经这么设计了，只是没数据） |
| `UI-01.tsx:130-134` | `syntheticTasks` 三条硬编码任务 | 同 `DailyAction` |
| `UI-14.tsx:22-28` | 课程大纲三周内容完全写死 | `ProductComponent` / `ContentVersion`（属产品侧配置，非家庭侧生成） |
| `UI-03.tsx:76-94` | `PREVIEW_SCORECARD` 整个假 scorecard | **不生成 —— 见桶 C** |

### 2.2 桶 B：保留写死（这些是护栏与标签，不是智能）

- 一切**边界声明文案**：`fact_boundary` / `score_boundary` / `ASSESSMENT_BOUNDARY_TEXT` /
  「这不是儿童诊断结论」。这类文案**必须写死**，因为它们是法律与产品承诺，
  不能由模型即兴生成（生成的免责声明不构成免责）。
- `UI-07` 整屏静态介绍页（测评前的说明）。它是营销说明，不是个性化内容，
  写死是正确的，**不要把它当成待生成项**。
- 枚举、状态机、允许动作清单（`allowed_actions`）、路由名、字段名。
- 安全触发词与升级路径（`human_triggers` / `expert_triggers`，Word V1.1 第 378-379 行）。

### 2.3 桶 C：必须删除，**不是待生成**（此前无人命名的一类）

这是本节最重要的发现。以下内容既不该硬编码，**也不该生成** ——
生成它们比硬编码更糟，因为规模化的虚构比一次性的虚构危害更大：

| 位置 | 内容 | 为什么必须删而非生成 |
|---|---|---|
| `UI-05.tsx:153-163` | 两条「家长打卡动态」：**虚构的用户与发言**（「慧慧妈妈」「乐乐爸爸」） | 伪造他人证言。生成式版本会**批量伪造社会证明**，这是欺骗而非功能。`DEV_SYNTHETIC_FIELD_ANALYSIS.md` R9-03 已点名 |
| `UI-16.tsx:71-72` | 团长名「乐乐妈妈」、倒计时「23:45:12」硬编码 | 伪造紧迫感与社会证明 |
| `UI-16.tsx:60` | `targetCount = [3,4,2,3][index % 4]` | 伪造拼团进度 |
| `UI-03` 的 `overall_score` / `peer_reference` / 雷达图同伴对比 | 打分 + 同伴基准 | **R9 红线 + 原始设计第 351 行明文禁止。** 不是"生成得更准"的问题 |
| `UI-06/10/18` 的 `Lv.3` | 家庭/儿童等级徽章 | 等级即排名的另一种形态。**注意区分**：会员权益等级（付费档位）合法，**成长等级**不合法 |
| `UI-15.tsx:57-58` | 邀请进度「1/3」写死 | 伪造进度 |
| `UI-18.tsx:88-90` | 会员进度条 58% + 「距下一步还有 720 积分」写死 | 伪造进度 |
| `journey_route: 'growth-ranking'` | 路由名 | 与 R9 直接冲突（`DEV_SYNTHETIC_FIELD_ANALYSIS.md` R9-01） |

**桶 C 的判据**：如果一段内容在**真实数据下也不该存在**，那它既不是硬编码问题也不是生成问题，
它是**产品问题**。生成式改造不得把桶 C 的内容"升级"为生成 —— 那会把一个静态谎言
变成一台谎言生产机。

## 3. 生成的对象与它们的契约（对象 + 属性树）

生成产物一律经 `model_gateway`，返回 `ModelDraft`（`status` 只有 `DRAFT`）。
每类产物的必备属性：

```text
GrowthHypothesis          statement / evidence_refs[]（非空）/ priority_rank / uncertainty
                          / limitations[] / provenance
                          ★ 无 score、无 peer_reference、无 band（§0.3）

JourneyPlan(Draft)        phases[]{intent, small_actions[]} / rationale
                          / requires_human_confirmation=true / provenance

DailyAction               assignment_text / why_now / expected_signal
                          / allowed_actions[]（枚举，写死）/ provenance
                          ★ 完成状态是 Fact，由家庭动作产生，不由生成产生

Recommendation            candidates[]{offer_ref, why_this, limitations[]} / why_now
                          ★ 排序不得由商业分成决定（Word V1.1 第 59 行明文）

Explanation               针对任一 Draft 的可解释性输出，引用 evidence_refs

ChildActionPrompt         面向未成年人 —— 额外强制 safety_policy 与
                          data_class=MINOR_PERSONAL_DATA
```

**共同强制**：`evidence_refs` 非空。无证据的生成物不得存在 ——
这是白皮书第 318-319 行「数据资产不是口号，必须从第一天设计采集结构」
与 Word V1.1 第 122 行「原始事实、用户陈述、服务者判断和 AI 推断**分别标记来源与置信度**」
的工程落地。

## 4. 上下文：三层画像（这一层有一手依据）

白皮书第 322-330 行给出了完整字段，**这是一手材料里颗粒度最细的数据设计**，
应当直接作为 Family Context 的初始 schema：

```text
父母画像   教育方式 / 沟通风格 / 焦虑点 / 参与度              —— 理解决策者
孩子画像   习惯 / 兴趣 / 动力 / 行为变化 / 情绪状态           —— 理解成长对象
家庭画像   互动频率 / 冲突类型 / 任务完成 / 改善路径          —— 理解关系系统
```

**建模约束（沿用 ADR-0015 §2）**：这些**不是主体上的列**，是
`StateObservation{subject, dimension, observed_value, evidence_refs, provenance,
observed_at, expires_at, retention_policy}` 的追加式观察。
`expires_at` 是「非永久人格标签」的执行机制。

**「情绪状态」是全平台合规风险最高的一个字段**（孩子画像里就有它）。
它必须：`data_class = MINOR_PERSONAL_DATA`、有明示留存期、可按主体级联删除、
且**不得触发任何自动动作**（R9：`legacy_alert.risk_score` → 非阈值非自动动作）。

## 5. 飞轮：「越用越准」的具体载体

白皮书第 313-314 行是这个系统的立论原话：

> 「真正的护城河是家庭成长数据库…当系统持续记录父母、孩子、家庭互动和改变路径，
> AI 才会越用越懂家庭，产品才会越用越准。」

它要求的最小记录链是：

```text
Context 快照 ──▶ 生成 Draft ──▶ 家庭决策（采纳/驳回/改写）──▶ 行动 ──▶ 结果
     │              │                    │                              │
     └── evidence ──┴─ prompt_version ───┴──── 谁在何时决定 ────────────┘
                                                                    ↓
                                              下一次生成的输入（更准的依据）
```

**四个此刻就必须存在、事后无法重建的字段**：

1. `evidence_refs` —— 这次生成基于哪些证据（缺它则无法解释也无法归因）
2. `causation_id` —— 事件因果链。`outbox_events` 现有 `correlation_id`
   但**无 `causation_id`**，因此跨月的因果链无法重建（T-20）
3. `human_assist` —— 人是否塑造了这次输入（ADR-0016）。缺它则证据库混有
   AI 判断与人的判断且不可区分，「越用越准」度量到的是那批辅助者
4. 家庭决策的**驳回**记录 —— 被驳回的建议是最有价值的负样本，
   而多数系统只记录采纳

**这四条都是"今天近乎零成本、将来永远补不回来"。**

## 6. 生成式在八层里的位置

```text
第 3 层 Family Growth Intelligence   生成的**语义**在这里定义（生成什么对象、约束是什么）
第 6 层 AI Runtime                    生成的**执行**在这里（gateway / prompt / schema / eval）
第 8 层 Model Layer                   可替换件
```

**关键**：生成的**语义归业务层，执行归 AI Runtime**。
一个 `GrowthHypothesis` 该有哪些字段、`evidence_refs` 能否为空 —— 这是领域决定，
不是模型决定。这使供应商更替不影响领域契约。

## 7. 明确不生成的（确定性区）

按 ADR-0005 §2，把 AI 塞进支撑域是具体危害而非仅是浪费。以下一律确定性：

```text
权限判定       PolicyEngine，fail-closed。让模型判断"这个 actor 能否读这个家庭"
               等于把 fail-closed 换成概率
同意判定       ConsentGate，无缓存
支付与订单     金额、状态机、幂等
状态机迁移     允许的迁移集是枚举，不是生成
审计写入       结构固定
派生量         完成率、覆盖度、次数 —— 这些是**计算**不是生成。
               `UI-02-result` 的 coveragePercent 就该是计算，它现在也是。
               ★ 但派生量不得跨家庭比较（否则就成了排名）
```

**「派生 ≠ 生成」这条边界很实用**：现在 34 屏里有大量百分比，其中一部分
（覆盖度、完成率）是合法的**计算**，另一部分（`width:"42%"`、`width:"58%"`）
是硬编码的**假计算**。前者保留，后者进桶 C。

## 8. 与既有 ADR 的关系（需要修正的地方）

| ADR | 需要的修正 |
|---|---|
| ADR-0015 | §Decision 4 的链条含 `Contradiction`。按 §0.1，应改为一手材料的用词：`priority_rank + uncertainty`。**其「护城河在领域建模与证据积累」的中心命题有一手依据**（白皮书 313-314），这部分不动 |
| ADR-0015 | 「家庭侧永不出现分数」的裁决**被一手材料支持**（Word V1.1 第 351 行），应把该引用补进 References —— 它把这条从"治理要求"提升为"业务方原始要求" |
| ADR-0010 | FGCN 相关的投影设计需注意 §0.2：FGCN 主链零代码且与现有 service 域是两套心智模型 |
| ADR-0014 / R9 护栏 | §0.3 暴露的盲区：`score` 字段在非 `Family*` 类上不被拦。需扩展判据 |
| 全部 | 一手材料**零技术选型**（无模型名、无技术栈、无数据库）。技术选型完全是架构师的空白，不存在"业务方已定"的东西 |

## 9. 执行状态（R14）

| 本文件的规则 | 执行者 | 状态 |
|---|---|---|
| 生成产物必须带 `output_schema` | `model_gateway` 已强制 | **有效** |
| `evidence_refs` 非空 | — | **无执行者**。可补：生成物类型的 `__post_init__` 校验 |
| 桶 C 内容不得存在 | — | **无执行者**。可补：断言 `score` / `peer_reference` / `Lv\.` 不出现在 UI 与 API 响应模型中（**注意 `frontend/` 当前在 ruff exclude 内，需单独的检查器**） |
| `Lv.` 等级徽章 | — | **无执行者** |
| 派生量不得跨家庭比较 | — | **不可机械检验**（"这个百分比是否用于比较"是语义判断） |
| 「主要矛盾」不建一等实体 | — | 靠 ADR 与 review |

**最该优先补的一条**：桶 C 的检查器。因为桶 C 里有 R9 红线的**实际违规**
（不是风险，是已经在 UI 里的代码），而现有护栏证明拦不住它。

## References

一手材料（引用均带行号，见正文）：
- `docs/01_strategy/source_materials/法咪莉教育战略白皮书_30页演讲汇报版.txt`
  （第 255、283-310、313-314、318-330 行 —— AI 位置、5 Agent、护城河、三层画像）
- `docs/01_strategy/source_materials/法咪莉教育新商业模式对外宣发PPT.txt`
  （第 63、312-325 行 —— 21 天 / 90 天；**注意白皮书无天数刻度，两者不一致**）
- `docs/01_strategy/source_materials/家庭教育大模型平台科技公司项目合作方案.txt`
  （第 43-48 行 —— 「复用成熟教培 SaaS，自建 AI 与知识库」，这是一手材料里唯一的技术路径表态）
- `docs/99_archive/2026/strategy/Family家庭教育成长平台实施方案_V1.1.txt`
  （ARCHIVED；第 33、59、64、115、122、128、213、304-310、351、378-379 行）
- `frontend/mobile/app/ui/UI-*.tsx` + `app/(tabs)/index.tsx`（34 屏，逐条引用见 §2）
- `contracts/openapi/UI_API_ENDPOINT_INVENTORY.md`（46 端点 / 11 已实现）
- `contracts/openapi/DEV_SYNTHETIC_FIELD_ANALYSIS.md`（R9-01/02/03 三项未决裁决）

治理与设计：
- `governance/REPOSITORY_CONSTITUTION.md` R5 / R7 / R9 / R10 / R14
- `docs/05_ai/AI_NATIVE_PRINCIPLES.md` §1 判据 3（生成式优先）、§4 反面清单
- `docs/05_ai/AI_ARCHITECTURE.md` §3.3（增量优先于新建对象）、§6-§10（运行时规格）
- ADR-0005 / ADR-0010 / ADR-0014 / ADR-0015 / ADR-0016 / ADR-0017
