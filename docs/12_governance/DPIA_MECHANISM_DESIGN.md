---
id: GOV-DPIA-001
title: DPIA 机制设计（个人信息保护影响评估的可执行形态）
type: governance
status: draft
version: 0.1
owner: chief-architect
created: 2026-08-29
updated: 2026-08-29
canonical: false
supersedes: null
superseded_by: null
---

# DPIA 机制设计

本文件回答一个具体问题：**PIPL 第55/56条要求的事前个人信息保护影响评估（DPIA），在 AiFamily 里以什么形态存在，才能不是"写过一份文档"。**

它是 T-07 的产出物之一，对应 `COMPLIANCE_HARD_CONSTRAINTS.md` §11 待办第 2 项。**本文件是设计方案，不是已落地能力**（`status: draft`, `canonical: false`）。落地需先出 ADR。

## 1. 法定要求的精确边界

| 法源 | 要求 | 对工程的含义 |
|---|---|---|
| PIPL 第55条 | 处理敏感个人信息 **或** 利用个人信息进行自动化决策，须**事前**进行影响评估 | 两项**分别独立**触发。AiFamily 两项同时成立（14岁以下全部信息为敏感信息；AI 评估输出按保守解读构成自动化决策） |
| PIPL 第56条 | 评估内容须含：处理目的/方式是否合法正当必要、对个人权益的影响与安全风险、保护措施是否有效且与风险程度相适应 | 评估是**结构化的四问**，不是自由作文 |
| PIPL 第56条 | 报告与处理记录**至少留存三年** | 需要不可篡改、可检索、有到期日的存储 |

关键词是**"事前"**。事后补一份文档不满足第55条。这决定了机制的形态：DPIA 必须是**发布前的闸门**，不是发布后的归档动作。

## 2. 核心设计判断：DPIA 绑定"处理活动"，不绑定"代码提交"

这是整个设计里唯一真正的决策点，先说清楚为什么。

两种可能的绑定粒度：

**方案 A：绑定代码变更。** 每个触碰敏感字段的 PR 要求一份 DPIA。
- 优点：闸门天然落在 CI 上，无需新概念。
- 致命缺点：法定评估对象是**处理活动**（目的+方式+范围），不是代码行。同一处理活动会被十几个 PR 反复触碰，每次都产一份"评估"会把评估贬值为形式勾选；反之，一次不改代码的**用途变更**（例如把已采集的情绪数据从"assessment"扩展用于"ai_personalization"）根本不产生 PR，却是第55条最典型的触发场景，方案 A 会完全漏掉。

**方案 B（采纳）：绑定处理活动（Processing Activity）。** 一个处理活动 = (数据类别集合, 处理目的, 处理方式, 数据主体类别, 接收方)。DPIA 评估一个处理活动；代码只需证明自己所属的处理活动已有有效 DPIA。
- 这与 `ConsentPurpose` 的粒度天然对齐——同意按目的授权，DPIA 按目的评估，两者共用一套 purpose 词表，不会漂移出两种"目的"概念。
- 用途扩展 = 新处理活动 = 新 DPIA + 重新同意（正好也是《儿童个人信息网络保护规定》第14条要求的），两条义务用同一个触发器。

**代价**：需要引入"处理活动登记簿"这个新的一等概念，并保证代码能声明自己属于哪个活动。这是本方案的主要实现成本，也是它唯一的弱点——若登记簿与代码脱节，机制会退化成方案 A 都不如的空壳。第 5 节的检查器就是为了防这一点。

## 3. 触发条件：哪个代码路径产生一次 DPIA 义务

按第55条两个独立触发器展开，每条给出可判定的代码信号：

| # | 触发器 | 可判定的代码信号 | 触发时机 |
|---|---|---|---|
| T1 | 新增一个处理**敏感个人信息**的处理活动 | `governance/PROCESSING_ACTIVITY_REGISTRY.yaml` 新增一条 `data_subject_category: minor_under_14` 或 `sensitive: true` 的条目 | 登记条目创建时（PR 内） |
| T2 | 新增一个**自动化决策**用例 | `governance/AI_USE_CASE_REGISTRY.yaml` 新增 AIUC 条目，且其输出会被展示给用户或影响推荐 | AIUC 登记时 |
| T3 | 已有处理活动的**目的扩展** | 登记条目的 `purposes` 列表新增值 | 修改登记条目时 |
| T4 | 已有处理活动的**数据类别扩展** | 登记条目的 `data_categories` 列表新增值 | 同上 |
| T5 | 新增或更换**受托第三方**（LLM/向量服务供应商） | Model Gateway 的 provider 注册表新增条目 | provider 准入时。注意这同时触发《儿童个人信息网络保护规定》第16条的安全评估，两者是不同评估，不可互相顶替 |
| T6 | 首次向**未成年人主体**扩大既有活动的适用范围 | 登记条目 `data_subject_category` 从 adult 变为含 minor | 修改时 |

**明确不触发**：纯技术重构（同一活动、同一目的、同一类别、同一接收方）、性能优化、UI 文案。这个否定清单和触发清单同样重要——一个什么都触发的机制会被绕过。

**T2 的边界诚实说明**：第73条定义要求"分析、评估…**并进行决策**"。纯描述性报告是否构成决策属事实判断。按 `COMPLIANCE_HARD_CONSTRAINTS.md` §2 的保守解读，本设计**假定构成**，即所有面向用户的 AI 评估输出都走 T2。这可能过度覆盖，但过度覆盖的成本是多写几份评估，覆盖不足的成本是第一档即可适用的"责令暂停服务"。

## 4. 评估什么：第56条的四问模板

DPIA 记录是结构化数据，不是散文。字段直接对应第56条三项 + 留存管理：

```yaml
dpia_id: DPIA-0001                      # 稳定标识
processing_activity_id: PA-0003         # 被评估的处理活动
trigger: T1                             # 第3节的触发器编号
assessed_at: 2026-09-01                 # 事前 —— 必须早于活动上线日
assessed_by: dpo                        # 谁负责（见第6节）
# 第56条 第一项:目的/方式的合法性、正当性、必要性
legality:
  purposes: [assessment]                # 必须是 ConsentPurpose 的取值
  legal_basis: guardian_consent         # PIPL 第13条的哪一项
  necessity_argument: <文本>            # 为什么不能用更少的数据达成目的
  minimisation_evidence: <文本>         # 已排除哪些字段、为什么
# 第56条 第二项:对个人权益的影响与安全风险
impact:
  affected_rights: [privacy, ...]
  risk_scenarios:                       # 每条含 likelihood / severity
    - {scenario: <文本>, likelihood: low|medium|high, severity: low|medium|high}
# 第56条 第三项:保护措施及其与风险的相适应性
safeguards:
  measures: [encryption_at_rest, purpose_bound_retention, read_access_audit, ...]
  proportionality_argument: <文本>       # 措施为何与风险程度相适应
# 自动化决策专属(T2)——PIPL 第24条
automated_decision:                      # T2 时必填,否则为 null
  explainability: <如何回答"为什么得出这个判断">
  human_review_path: <人工复核入口>
  opt_out_path: <可拒绝的方式>
# 留存管理(第56条 ≥3年)
retention:
  retain_until: 2029-09-01              # assessed_at + 3 年,自动推导
  outcome: approved|approved_with_conditions|rejected
  conditions: [...]                     # approved_with_conditions 时必填
```

三处刻意的设计：

1. **`purposes` 必须取自 `ConsentPurpose`**。DPIA 的"目的"和同意的"目的"是同一个词表，否则会出现"DPIA 评估了 A 目的、同意书写的是 B 目的"这种最难发现的漂移。
2. **`automated_decision` 在 T2 时必填**。这把 PIPL 第24条的可解释/可拒绝/人工复核三件事钉进评估记录，而不是散落在产品文档里。
3. **`retain_until` 从 `assessed_at` 推导而非手填**。手填的日期会被填错，且第56条的三年是硬数字。

## 5. 记录存哪里 + 如何保证留存三年

**分两层，因为"评估文档"和"处理记录"是第56条里两个不同的东西。**

### 5.1 评估报告（DPIA 本体）→ 仓库内 YAML，git 提供不可篡改性

`governance/DPIA/DPIA-NNNN-<kebab-slug>.yaml`，与 `governance/ADR/` 同构。

选这个位置而不是数据库的理由：
- **git 历史即留存证明**。三年留存要求的实质是"不能悄悄改、不能悄悄删"，git 的哈希链天然满足，且无需自建 WORM 存储。删除一份 DPIA 会在 diff 里显形。
- **评估是人写的、要评审的**。它走 PR 评审流程是对的；塞进数据库就没人 review 了。
- **代价**：DPIA 内容会包含处理活动描述，不含任何个人信息（这是必须遵守的约束——DPIA 文件里出现真实家庭数据本身就是违规）。需要一条检查器守这一点。

### 5.2 处理记录（谁在什么时候实际处理了什么）→ 数据库审计表

这部分**不进仓库**，因为它含个人信息且体量大。它就是 `backend/platform/audit/` 的durable 表：T-07 已扩展的 `AuditEvent`（含 `action_kind=READ` 的读取留痕）正是第56条"处理记录"的载体。

留存三年的实现：审计表**只允许 INSERT**，配 `retain_until = timestamp + 3 years` 列，清理任务只删除 `retain_until < now()` 的行。注意这里的三年是**下限**——若某条记录同时受《儿童个人信息网络保护规定》第12条"不超过实现目的所必需"约束，取两者中更严格的（见 `DATA_RETENTION_BINDING_DESIGN.md`）。三年留存与最小必要留存在方向上冲突，冲突解法是：**审计记录的留存目的就是合规举证，三年是其必要期限**，与业务数据的最小化留存是两个不同的处理活动，分别登记。

## 6. 谁负责

| 角色 | 职责 | 落到本仓库 |
|---|---|---|
| 个人信息保护负责人（DPO） | 签署 DPIA、批准/拒绝处理活动上线 | `assessed_by` 字段；PR 的 required reviewer |
| 总架构师 | 判定某变更是否命中第3节触发器；维护处理活动登记簿 | CODEOWNERS 覆盖 `governance/DPIA/` 与登记簿 |
| 开发者 | 在 PR 中声明所属处理活动；不得自评自批 | 检查器强制（第7节） |
| 法务/外部机构 | 第7条"不得转委托"的供应商分包评估（T5）；第37条年度审计 | 本仓库外，但结论回写为 DPIA 条目 |

《儿童个人信息网络保护规定》第8条要求"专门规则+专人负责"，DPO 这个角色不是可选的组织装饰。**当前状态诚实说明：本仓库尚未指定 DPO 实名**，这是落地前必须由 owner 决定的事项，不是架构可以自行填的。

## 7. 可机械检验的部分与不可检验的部分

这一节存在的意义：`REPOSITORY_CONSTITUTION.md` R14 的伤疤是"策略写成常量却无人执行"。所以必须明确划线。

**可检验（落地时应写成 `tests/architecture/` 检查器）**：
1. 每条 `PROCESSING_ACTIVITY_REGISTRY.yaml` 条目若 `sensitive: true` 或主体含未成年人，必须有 `dpia_ref` 指向存在的 DPIA 文件。
2. 每个 AIUC 条目必须有 `dpia_ref`（T2）。
3. 每份 DPIA 的 `purposes` 取值必须全部属于 `ConsentPurpose` 枚举（跨文件一致性）。
4. 每份 DPIA 的 `retain_until` == `assessed_at` + 3 年，且 `assessed_at` 必须早于对应处理活动的 `activated_at`（**这条直接检验"事前"**）。
5. T2 类 DPIA 的 `automated_decision` 三字段非空。
6. DPIA 文件不含个人信息（正则扫手机号/身份证/真实姓名字段模式）。
7. 每个声明处理敏感数据的代码模块能解析出 `processing_activity_id`（防第2节说的"登记簿与代码脱节"）。

**不可检验，且不应假装检验**：
- 必要性论证是否**真的**站得住脚。这是法律判断，检查器只能验证字段非空，验证不了内容质量。写一个"检查 necessity_argument 长度 > 50 字符"的测试是自欺。
- 风险评级是否恰当。
- 保护措施是否**实际有效**（措施列了 `encryption_at_rest` 不等于真加密了——那需要另一条独立的检查器去验证存储层，属于不同的义务）。
- 第37条年度审计是否真的每年做了。可以检查"是否存在一份 `assessed_at` 在过去12个月内的年度审计记录"，这是**日历检查**而非实质检查，且会在无人维护时变成 CI 红灯噪音。建议做成报告模式（对齐 T-08 的做法）而非硬失败。

## 8. 落地顺序建议

DPIA 机制的前置依赖是**处理活动登记簿**，而登记簿的前置依赖是**真实存在需要登记的处理活动**。当前 AiFamily 尚无任何路径处理真实未成年人数据（业务域为 assessment / membership / product_intelligence / loyalty_points，均无儿童主体读写路径）。

因此建议顺序：
1. （现在）本设计入仓，`status: draft`。
2. Batch 3 Family Core 落地、首次出现真实家庭数据模型时 → 出 ADR 定案，同时建 `PROCESSING_ACTIVITY_REGISTRY.yaml` + 第7节检查器 1/3/4。
3. Model Gateway（T-06）接入首个真实 provider 时 → 建 T5 通道与第16条安全评估。
4. 首个 AI 评估用例上线前 → 第7节检查器 2/5。

**不建议现在就建空登记簿**：一个零条目的登记簿加一套永远通过的检查器，正是 R14 要防的东西。
