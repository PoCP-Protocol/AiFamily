---
id: GOV-RETENTION-001
title: 留存期限绑定设计（让"每个未成年人数据字段都有明示留存期限"成为可检查的事实）
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

# 留存期限绑定设计

本文件回答：**怎样让"每个存储未成年人数据的字段都有明示的留存期限、到期处理方式和声明过的目的"从一句意图变成 CI 能判定的事实。**

T-07 产出物之一，对应 `COMPLIANCE_HARD_CONSTRAINTS.md` §11 待办第 3 项与 §1 架构含义第 1–3 条。**设计方案，未落地**（`status: draft`, `canonical: false`）。落地需先出 ADR。

## 1. 法定要求与它真正否决的东西

| 法源 | 要求 |
|---|---|
| 《儿童个人信息网络保护规定》第10条 | 采集时须**事前**告知监护人：存储地点、**存储期限**、**到期后的处理方式** |
| 同 第11条 | 不得收集与服务无关的信息 |
| 同 第12条 | 存储期限**不超过实现目的所必需** |
| 同 第14条 | 超出约定目的范围使用须**再次**取得监护人同意 |
| PIPL 第6条 | 最小范围、不得过度收集——**不可由同意豁免** |
| PIPL 第4条 | "存储"属"处理"，故留存期限本身受第28条必要性检验约束 |

这几条组成的闭环，其真正效力在于**它否决了一种设计**，而不只是增加了一项披露义务：

> 用途未定的无限期留存，无法满足第10条的事前披露义务。你无法在采集时告知监护人一个你尚未决定的留存期限。

所以"先全量采集、以后再想用途"的数据湖式设计**在法律上不可实现**，不是"不推荐"。这直接约束 `DATA_ARCHITECTURE.md` 里 Family Context / Family Growth Graph 的建模方式，也直接约束白皮书 Slide 18/19 的三层画像长期沉淀叙事（见 `COMPLIANCE_HARD_CONSTRAINTS.md` §12）。

**推论一（容易漏）**：这个义务作用在**字段**粒度，不是表粒度。同一张表里"孩子昵称"和"情绪状态"的必要留存期限不可能相同。表级 TTL 满足不了第12条。

**推论二（更容易漏）**：它作用在**派生数据**上同样成立。按孩子维度算出的 embedding 仍是可识别儿童个人信息（§6），所以 embedding 字段也要有留存期限，而不是"索引整体重建时顺便清"。

## 2. 方案：字段级元数据 + 反射检查器

核心机制：让留存契约**寄居在字段声明处**，而不是另写一份对照表。

理由很直接：任何"模型在这边、留存表在那边"的方案都会漂移，而漂移的方向永远是新字段忘记登记。字段声明和留存声明写在同一行的正下方，漏写在 code review 里是肉眼可见的，且反射检查器可以直接判定。

### 2.1 声明形态（pydantic）

```python
from pydantic import BaseModel, Field

class ChildEmotionSnapshot(BaseModel):
    subject_person_id: str = Field(
        json_schema_extra={
            "personal_data": True,
            "data_subject": "minor",
            "purpose": "assessment",            # 必须是 ConsentPurpose 取值
            "retention_days": 730,
            "expiry_action": "hard_delete",
            "disclosed_to_guardian": True,      # 第10条事前告知已覆盖此字段
        }
    )
    emotional_state: str = Field(
        json_schema_extra={
            "personal_data": True,
            "data_subject": "minor",
            "purpose": "assessment",
            "retention_days": 365,              # 与上一字段不同 —— 这正是重点
            "expiry_action": "hard_delete",
            "disclosed_to_guardian": True,
        }
    )
    tool_ref: str  # 无 personal_data 标记 = 声明"这不是个人信息"
```

SQLAlchemy 侧用 `mapped_column(info={...})` 承载同一组键；`info` 是 SQLAlchemy 官方的用户元数据通道，读取方式为 `Table.columns[x].info`。两处用同一套键名，检查器一套逻辑覆盖两种模型。

### 2.2 五个键的语义

| 键 | 取值 | 为什么必须 |
|---|---|---|
| `personal_data` | bool | 显式**opt-in**。见第3节，这是整个方案最关键也最脆弱的一点 |
| `data_subject` | `minor` \| `adult` \| `household` | 14岁以下全部信息为敏感信息（PIPL 第28条），严格度按此分流 |
| `purpose` | `ConsentPurpose` 的取值 | 第10/14条：目的必须具体且与同意书同源。禁止 `"ai_personalization_general"` 这类笼统表述 |
| `retention_days` | int > 0，或 `"until_consent_withdrawn"` | 第10/12条。**禁止 `None` / `-1` / `"indefinite"`** |
| `expiry_action` | `hard_delete` \| `anonymise` \| `guardian_choice` | 第10条要求告知"到期处理方式"，所以它是一个必须被选定的值 |
| `disclosed_to_guardian` | bool | 第10条的**事前**告知。为 False 即为不可采集 |

`until_consent_withdrawn` 这个特殊值需要辩护：它看起来像"无限期留存"的后门。它不是——它是一个**有明确终止条件**的期限，可以在采集时如实告知监护人（"我们保留至您撤回同意为止"），且撤回后立即触发 `expiry_action`。真正被禁的是**没有终止条件**的留存。但因为它容易被滥用为默认值，第4节的检查器对它施加额外约束。

## 3. 权衡：三种方案与选择理由

### 方案 A：opt-in（字段自己声明 `personal_data: True`）
- 优点：实现最简单，无误报，不干扰非个人数据字段。
- **致命缺点：漏写等于合规通过。** 新增一个 `child_nickname` 字段却忘记加元数据，检查器完全看不见它。这与 R14 要防的失败模式同构——不是"策略没被执行"，而是"策略看不见违规对象"。

### 方案 B：opt-out（默认所有字段都是个人数据，须显式声明豁免）
- 优点：漏写等于失败，方向正确。
- 缺点：噪音极大。`created_at` / `tool_ref` / `correlation_id` / 每个枚举字段都要写豁免。经验上这种成本会导致开发者批量加豁免装饰器，几个月后所有字段都带豁免标记，方案退化成方案 A 且更难发现。

### 方案 C（采纳）：按模块范围的 opt-out + 全局命名启发式兜底

分两层：

**第一层——范围性 opt-out。** 只在**声明为承载家庭/未成年人数据的模块**内启用严格模式。模块通过一个模块级常量登记自己：

```python
CONTAINS_PERSONAL_DATA = True   # 本模块内每个字段必须显式声明 personal_data 键
```

在这些模块内，任何缺少 `personal_data` 键的字段都是失败。范围有限，噪音可控，而"漏写=失败"在最关键的地方成立。

**第二层——全局命名启发式兜底，防的是"忘记声明整个模块"。** 复用本仓库已验证过的手法：`test_compliance_constraints.py::test_no_scoring_or_ranking_fields_anywhere` 已经在全 backend 反射字段名并按 token 匹配。同一套 AST 反射可以找出**未登记模块里**出现 `child_*` / `guardian_*` / `emotion*` / `family_*` 等主体 token 的字段，报告"这个模块看起来在存个人数据但没声明 `CONTAINS_PERSONAL_DATA`"。

启发式会有误报（`family_id` 是标识符不是画像），所以需要带理由的豁免表——这个模式在现有检查器的 `FIELD_TOKEN_EXEMPTIONS` 里已有先例且工作良好（"an unexplained exemption is how a red line erodes"）。

**方案 C 的诚实缺点**：第二层是启发式，一个叫 `attr_7` 的字段存着孩子的情绪状态，谁都拦不住。这个残余风险不可通过静态检查消除，只能通过 code review 与 DPIA 流程（`DPIA_MECHANISM_DESIGN.md` 第3节 T1/T4）覆盖。**必须如实记录这个缺口，不能声称覆盖率是 100%。**

## 4. 落地时应写的检查器

对 `CONTAINS_PERSONAL_DATA = True` 的模块，逐字段判定：

1. **必须有 `personal_data` 键**（第一层 opt-out 的执行）。
2. `personal_data: True` 的字段**必须**同时有 `data_subject` / `purpose` / `retention_days` / `expiry_action` / `disclosed_to_guardian` 全五键。缺一即失败。
3. `retention_days` 不得为 `None` / `0` / 负数 / `"indefinite"` / `"forever"`。**这条直接执行"数据湖式全量留存不可实现"。**
4. `purpose` 必须属于 `ConsentPurpose` 枚举（跨文件一致性，与 DPIA 共用同一词表）。
5. `expiry_action` 必须属于封闭取值集。
6. `disclosed_to_guardian` 必须为 True——`False` 的字段代表未经事前告知就在采集，是应当在 CI 挡住的状态，不是需要报告的状态。
7. `data_subject: "minor"` 的字段，`retention_days` 上限设一个需要显式豁免才能突破的阈值（建议 1095 天 = 3 年）。理由：第12条"不超过实现目的所必需"无法机械判定，但一个**需要解释才能超过的默认上限**能把举证责任放对位置。豁免必须带理由字符串，与 `FIELD_TOKEN_EXEMPTIONS` 同一模式。
8. `until_consent_withdrawn` 的字段必须能被撤回链路覆盖——落地形态是：该模块必须存在一个引用了 `ConsentGate` 或撤回处理器的路径。否则这个值就是伪装成期限的无限期留存。
9. **派生数据同权**：任何被标记 `personal_data: True` 且名字含 embedding/vector token 的字段，必须满足既有的 `test_vector_storage_supports_subject_scoped_deletion`（§6 级联删除）**并且**满足本节 1–7。两条义务叠加，不可互相顶替。
10. **兜底报告器**：未登记模块里出现主体 token 字段 → 报告。建议先做**报告模式**（不失败 CI），与 T-08 traceability 检查器同样的引入路径，确认信噪比后再转强制。

## 5. 运行时侧：声明与执行的对齐

静态元数据只保证"声明了期限"。让期限**真的发生**需要三件运行时机制，且它们必须从同一份元数据读取，否则又是一次漂移：

1. **到期清理任务**：反射元数据生成清理计划，逐字段（不是逐表）按 `retention_days` 与 `expiry_action` 执行。它必须从元数据反射而来，不能手写一份 SQL 清单——手写清单会和字段声明漂移，而漂移方向永远是新字段没被清理。
2. **采集时的披露对齐**：给监护人看的告知文案由元数据生成，不是产品另写一份。第10条的告知内容与实际留存行为不一致，比不告知更糟（构成虚假陈述）。
3. **目的变更闸门**：修改任何字段的 `purpose` 是第14条的"超出约定目的"，必须触发重新同意 + 新 DPIA。可检验的形态：`purpose` 值的 git diff 触发一条 required review + 要求同 PR 内有 `dpia_ref` 更新。

## 6. 与三年审计留存的冲突及其解法

`DPIA_MECHANISM_DESIGN.md` §5.2 要求审计记录留存 ≥3 年（PIPL 第56条）；本文件要求业务字段留存**不超过必需**（第12条）。方向相反。

解法不是取折中，而是承认它们是**两个不同的处理活动**：
- 业务数据的处理目的是提供服务 → 期限按服务必要性，通常远短于三年。
- 审计记录的处理目的是**合规举证** → 三年就是这个目的的必要期限，第56条已经替我们做了必要性判断。

两者分别登记为独立处理活动、分别做 DPIA、分别设期限。审计记录里因此**只应含举证必需的最小字段**（谁、何时、读了哪些字段名、目的、审批号），**不得含被读取数据的内容值**——否则审计表就变成了绕过业务留存期限的数据副本。这是 T-07 已落地的 `AuditEvent` 里 `accessed_fields` 只记**字段名**而非字段值的原因，这个设计选择在此得到辩护。

## 7. 落地顺序

同 `DPIA_MECHANISM_DESIGN.md` 第8节的判断：当前 AiFamily 没有任何模块存储真实未成年人数据（业务域为 assessment / membership / product_intelligence / loyalty_points）。现在建全套检查器等于让它们检查空集，永远通过。

1. （现在）本设计入仓，`status: draft`。
2. Batch 3 Family Core 首个真实家庭数据模型落地 → 出 ADR 定案键名与取值集，同 PR 建检查器 1–6，并在该模块加 `CONTAINS_PERSONAL_DATA = True`。**必须做咬人验证**（删掉一个字段的 `retention_days` → 测试失败）。
3. 检查器 10（兜底报告器）可先行，因为它对全 backend 生效且不依赖任何新模型；建议报告模式起步。
4. 向量化设计定案时 → 检查器 9，与既有 §6 级联删除检查合并。
5. 清理任务（第5节第1项）与 Family Core 的持久化层同批落地，不得延后——延后会立刻产生一批已过期却仍在库的数据。
