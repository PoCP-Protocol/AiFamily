---
id: DOMAIN-ARCH-001
title: AiFamily 领域架构 —— 边界、归属与跨域契约
type: specification
status: current
version: 1.0
owner: chief-architect
created: 2026-08-29
updated: 2026-08-29
canonical: true
supersedes: null
superseded_by: null
---

# 领域架构：边界、归属与跨域契约

```text
本文件回答三个问题，且只回答这三个：
  1. 业务真相被切成哪些域，每个域拥有什么、明确不拥有什么
  2. 七个引擎（ADR-0015）落在哪些代码位置 —— 引擎是职责划分，不是目录
  3. 跨域只允许四种通信，它们各自的**契约形状**是什么

不回答「现在实现到什么程度」—— 那是 docs/00_system/CURRENT_DOMAIN_MAP.md。
本文件与它冲突时，**现状以它为准**。
```

## 0. 为什么需要这份文件

`docs/10_engineering/ENGINEERING_ARCHITECTURE.md` 已声明跨域通信只允许
**Command / Query / Event / Port** 四种，并在其 §6 把「跨域 Port 契约细节未定义」
列为待人类架构师处理的技术债。**四种模式被点了名字，但没有一种被定义形状。**

后果不是抽象的。当前磁盘上已有的两种越界都源于此：

1. **`/auth/*` 四个端点寄居 `backend/domains/assessment/api.py:68-154`**，
   token 存在 `AssessmentApiState.tokens` 这个进程内 dict（`api.py:40`）——
   身份能力住在 assessment 域内。
2. **`backend/domains/product_intelligence/application/ports.py` 顶部
   从 `..domain.entities` import 了 19 个业务实体**——一个名为「port」的文件
   携带了整张实体图，于是任何 import 它的模块都获得了整个域。

两者都不是有人故意违规，是**没有契约形状可依循时的自然结果**。R14 的立场同样适用于此：
一个只有名字的通信模式，等于没有通信模式。

## 1. 域清单与三类归属

分类依据 ADR-0005 §2（核心域必须 AI 原生 / 优势域应当 / 支撑域不要求）。
**AI 原生要求作用于核心域；把 AI 塞进支撑域是另一种错误**（R7/R9 正是防这个）。

| 类型 | 域 | AI 原生 | 说明 |
|---|---|---|---|
| **核心域** | `assessment` `growth` `journey` `action` `outcome` | **必须** | 测评解读、成长诊断、干预决策、方案生成。关掉 AI 即失去核心价值 |
| **优势域** | `service` `teacher` `institution` `community` | 应当 | FGCN 协作网络所在；匹配与推荐是 AI 侧，权威状态是域侧 |
| **支撑域** | `identity` `tenancy` `consent` `commerce` `membership` `loyalty_points` | **不要求** | 登录鉴权、同意判定、支付回调必须是确定性、可复现、可审计的。让 LLM 参与「这个 actor 是否有权读这个家庭的数据」等于把 fail-closed 换成概率判断 |
| **内部工具域** | `product_intelligence` | 应当 | 面向**一类家庭**（产品该造什么），不面向单个家庭。与核心域的区别见 §2.3 |
| **已裁决退役** | `growth_plan` `market_intelligence` `product_strategy` | — | 见 ADR-0012 与 registry 的 `RETIRED_CANONICAL_CONFLICT` |

**真实成熟度不在本表**（`CURRENT_DOMAIN_MAP.md` 才是）。本表回答「该有哪些域、各属哪类」。

## 2. 归属规则：Owns / Does Not Own

### 2.1 三条不可协商的归属规则

**规则 1 —— 一个聚合只有一个域拥有写入权。**
其它域只能通过 Query Port 读，或通过 Command 请求那个域去写。R2 的直接推论。

**规则 2 —— 派生视图不拥有真相。**
Family Growth Graph、决策来源图、任何投影都是视图，**不登记为域**
（登记为域即造出第二个成长真相，直接违 R2）。见 ADR-0010。

**规则 3 —— AI 侧永不拥有任何聚合。**
`backend/intelligence/` 下没有任何域，`may_mutate_business_state = false`。
它产出 `Perspective` / `Recommendation` / `Draft`，跨越为 Fact 只能经拥有该聚合的域的
Named Action + 人类 actor（R9 + ADR-0014）。

### 2.2 关键边界（写明「不拥有什么」，因为歧义都在这里）

| 域 | Owns | **Does Not Own**（歧义高发处） |
|---|---|---|
| `identity` | `Account` / `IdentitySession` / `OtpChallenge` / `GuardianRelation`、4 个 `/auth/*` 端点 | **不拥有** `ActorContext` / `TenantContext`——那是平台原语（ADR-0011）。不拥有家庭结构（属 `family`） |
| `tenancy` | `Tenant` / `TenantFamilyBinding` / `TenantAccountMembership` 与绑定链判定 | 不拥有 `TenantContext` 值对象（平台层）。不拥有套餐权益的计费（属 `commerce`） |
| `family` | `Family` / `Person` / `Relationship` / 家庭结构 | **不得从 `Relationship` 推断 `consent`，不得从 `birthdate` 推断 lifestage**——这是源仓库 `family-core-integration.e2e-spec.ts` 留下的否定推断守卫，作为 `TEST_ORACLE` 继承 |
| `consent` | `Consent` 记录、按目的的授权状态 | **不拥有判定逻辑的调用时机**。`ConsentGate` 是平台原语且无缓存（`consent/gate.py`：「no code path here can return a stale ALLOW」） |
| `assessment` | `AssessmentSession` / `AssessmentTool` / `AssessmentResponse` / `GrowthHypothesis` | **不拥有 `/auth/*`**（当前寄居，属 ADR-0011 §4 待迁出的越界）。不拥有 `GrowthIntent` 之后的计划（属 `journey`） |
| `journey` | `GrowthIntent` / `GrowthPlan` / 21-90 天节奏 / 阶段复盘 | 不拥有单次动作的完成事实（属 `action`）。**「计划」不是独立域**（ADR-0012） |
| `action` | `GrowthAction` 及其状态机（开始/暂停/继续/取消/完成） | **打卡 ≠ `GrowthActionCompletionFact` ≠ Outcome**（R9 FELS 表 M014）。不拥有效果判断（属 `outcome`） |
| `outcome` | `Outcome` / 成长证据 | **不拥有任何分数或等级**。R9：`legacy_assessment_score.score` → HISTORICAL_EVIDENCE / 非 GrowthState |
| `service` | `ServiceBlueprintVersion`（DRAFT→REVIEWED→PUBLISHED→RETIRED，发布后冻结）/ `ServiceCase` / `ServiceTask` / `TaskAssignment` / `ServiceRecord` | **不拥有「哪个资源最适合这个任务」的判断**——那是 AI 侧的 Recommendation，最终分派须过 Human Gate（R8） |
| `commerce` | 订单 / 支付 / 权益兑换 | **FREEZE-001 冻结中**。且**绝对禁止**向未成年人做自动化决策商业营销（《未成年人网络保护条例》第 24 条第 3 款，无年龄例外） |
| `loyalty_points` | `PointsEntry` 账本 | **不拥有 `balance` 字段**——余额永远是 `policies.compute_balance(entries)`。**不提供任何跨家庭查询方法**（无 `rank_families`）：*那个方法的缺席就是 R9 的执行机制*。这是全仓最好的一处设计，其它域应照此办理 |
| `product_intelligence` | `MarketSignal` / `Opportunity` / 三区评估 / `ProductConcept` | 面向**一类家庭**。**不拥有任何单个家庭的状态**——跨到单家庭即越界进核心域 |

### 2.3 「面向一个家庭」与「面向一类家庭」的分界

这是 ADR-0015 定调里最容易做错的一处，单独立规：

```text
Growth Intelligence   面向一个家庭   输入=该家庭的 Context/State   输出=该家庭的 Strategy
Product Intelligence  面向一类家庭   输入=聚合后的群体信号         输出=该造什么产品
```

**分界的执行意义**：Value Score 等度量只允许存在于 Product Intelligence 侧的**队列级**统计，
**永不写回家庭对象、永不用于家庭间比较**（ADR-0015 §1(c)）。
`tests/architecture/test_r9_value_layer_boundary.py` 的判据正是这条线：
主体形状的类不得有分数，产品/群体形状的类可以。

## 3. 七个引擎 ↔ 代码位置（ADR-0015 §Enforcement 指定的映射表）

**引擎是职责划分与归位依据，不是目录。** 建七个目录会制造
`CURRENT_AI_MAP.md` §6 自己命名的「第六类：目录名冒充能力」。

| 引擎 | 权威状态归 | 推理/查询归 | 磁盘现状 |
|---|---|---|---|
| Family Context Engine | 各业务域自己的聚合 | `backend/intelligence/context_engine`（尚不存在） | `ABSENT` |
| Emotional Intelligence Engine | `StateObservation` 观察记录（归 `family` 或新域，PR-003 定） | `backend/intelligence/`（尚不存在） | `ABSENT`，本方向由 ADR-0015 首次引入 |
| Growth Intelligence Engine | `assessment` 的 `GrowthHypothesis` / `journey` 的 `GrowthIntent` | `backend/intelligence/`（尚不存在） | 雏形：`hypotheses` / `action_candidates` 存在，**缺 `primary_contradiction` 排序层** |
| Intervention Engine | 干预落地为 `action` / `service` 的聚合 | `backend/intelligence/`（尚不存在） | `ABSENT` |
| Product Intelligence Engine | `backend/domains/product_intelligence` | 同域内 | **唯一有真代码 + 测试的引擎** |
| Service Intelligence Engine | `backend/domains/service` | 匹配能力在 `backend/intelligence/` | `ABSENT` |
| Learning & Value Engine | `outcome` 的成长证据 + `graph_projection.*` 投影 | `backend/intelligence/evaluation`（尚不存在） | `ABSENT` |

**读法**：每一行的「权威状态归」都落在业务域，「推理/查询归」都落在 `intelligence/`。
这不是额外规则，是**规则 3 在七个引擎上的逐行投影**。

## 4. 跨域通信的四种模式及其契约形状

**没有第五种。** 禁止跨域直接 import repository；禁止跨域共享 SQLAlchemy session；
禁止用数据库视图跨 schema（`docs/07_data/DATA_ARCHITECTURE.md` 已决定）。

### 4.1 Command —— 请另一个域改它自己的状态

```text
契约形状（必备五项，缺一不成立）
  actor          : ActorContext        必填。不得是 str —— assessment 域用 actor_id: str
                                       的教训见 ADR-0014 §Context 2：is_ai 密封缝因此失效，
                                       且骗过了护栏的参数名启发式
  idempotency_key: IdempotencyKey      必填。所有 mutation 端点均要求（现有 assessment
                                       路由已按此实现，`api.py` 的 mutation_key）
  intent         : 具名动作             不是 CRUD 动词。"assessment.confirm_hypothesis"
                                       而非 "update_hypothesis"
  payload        : 该域自己的输入类型     不得是另一个域的实体
  returns        : 该域自己的输出类型 | 领域错误
```

**硬规则**：Command 的处理必须产生 `AuditEvent`（R6），
且**若该 Command 会把某物变成 Fact，必须先过 `PolicyEngine.check()` 且规则注册
`human_only=True`**（ADR-0014 §3）。`PolicyEngine` 是真 fail-closed：
未注册即 DENY，`human_only` 检查位于任何 allow 逻辑之前，且**不存在注册 DENY 规则的接口**。

### 4.2 Query Port —— 读另一个域的投影，不读它的实体

```text
契约形状
  定义位置  : **调用方**的 application 层，不是被调方
  返回类型  : 调用方自己定义的只读 DTO，**不得是被调方的域实体**
  实现位置  : 被调方的 infrastructure 层（它知道自己的表）
  禁止      : 返回类型的字段引用被调方实体；Port 文件 import 被调方的 domain.entities
```

**这条是从一处实测越界反推出来的**：`product_intelligence/application/ports.py`
顶部 import 了 19 个业务实体。一个 Port 若携带实体图，import 它的模块就获得了整个域，
隔离名存实亡。**Port 的价值在于它比实体窄**；不窄的 Port 是伪装成契约的耦合。

### 4.3 Event —— 通知已经发生的事实

```text
契约形状
  语义      : 过去时。"HypothesisConfirmed" 而非 "ConfirmHypothesis"
  发布      : 与状态变更**同事务**写 outbox（不得先提交再发，否则事实与事件可能分叉）
  载荷      : 自包含的不可变快照 + provenance，**不得只放一个 id 让订阅方回查**
              （回查即再次跨域读，且读到的是之后的状态而非事件当时的状态）
  订阅      : 订阅方不得假设投递顺序，必须幂等
```

**当前状态：`DomainEvent` 与 outbox 在全仓 grep 为 0 命中**（`CURRENT_SYSTEM_BASELINE.md` §4.8）。
ADR-0010 的整条投影链依赖它，且该 ADR 明确规定
**在 outbox 存在之前，投影层一行代码都不该写**。

### 4.4 Port（能力端口）—— 域向外声明它需要什么，而非它有什么

```text
契约形状
  声明方向  : 由**需要能力的域**声明 Protocol，由提供方实现
  典型用例  : assessment 需要「把测评响应变成一个假设草案」这个能力
              → assessment 定义 HypothesisDraftPort，import model_gateway 的 ModelDraft
              → model_gateway **不知道 assessment 存在**
```

**依赖方向必须反转**，这是 R7 与 R10 的共同要求：
`domain → intelligence` 合法（域主动依赖 AI 能力），`intelligence → domain` 违规。
`tests/architecture/test_ai_runtime_isolation.py` 执行这条。

### 4.5 四种模式的选择判据

| 我想…… | 用 | 不要用 |
|---|---|---|
| 让另一个域改状态 | Command | 直接拿它的 repository 改 |
| 读另一个域的数据 | Query Port（窄 DTO） | 直接 import 它的实体 |
| 让别人知道我改了 | Event（同事务 outbox） | 直接调用下游 Command（会造成隐式编排与循环依赖） |
| 我需要一个我没有的能力 | Port（我声明，别人实现） | 去 import 提供方的实现 |

## 5. 分层约定：platform 与 domains 刻意不同

| | `backend/platform/*` | `backend/domains/*` | `backend/intelligence/*` |
|---|---|---|---|
| 分层 | **不分层**（技术原语） | `api/ application/ domain/ infrastructure/` | 按组件划分，不四层 |
| 可含业务生命周期 | **否**（ADR-0011 判据：不得有状态机、不得有 repository） | 是 | 否（不拥有聚合） |
| 可 import `domains` | **否**（否则每次授权检查都拖进一个业务域） | 仅经四种模式 | **否**（运行时；见测试对 TYPE_CHECKING 的取舍） |
| 规格文档 | `docs/06_platform/`（7 份，已完成） | 本文件 + `CURRENT_DOMAIN_MAP.md` | `docs/05_ai/AI_ARCHITECTURE.md` |

## 6. 执行状态（R14：未被检查覆盖的规则只是意图）

| 本文件的规则 | 执行者 | 状态 |
|---|---|---|
| §2 规则 3 / §4.4 依赖方向 | `tests/architecture/test_ai_runtime_isolation.py` | **有效** |
| §5 platform 不 import domains、不四层分层 | 同上（第二、三组用例） | **有效** |
| §2.3 主体形状的类不得有分数 | `tests/architecture/test_r9_value_layer_boundary.py` | **有效** |
| §2 规则 1（一聚合一域） | `test_domain_registry.py`（R2） | 部分——它查 capability↔path 唯一性，**不查语义重叠**（语义重叠原理上不可机械检验，靠 ADR） |
| §4.1 Command 必带 `ActorContext` 而非 `str` | — | **无执行者。** 可补：扫 `domains/*/application` 的命令函数签名，要求 actor 参数注解为 `ActorContext`。**这条应优先补**——现存的 assessment 越界正是它没有 |
| §4.2 Port 不得返回被调方实体 | — | **无执行者。** 可补：`domains/*/application/ports.py` 不得 import 本域之外的 `domain.entities`（注意现存 `product_intelligence/ports.py` 会立刻违规，需带理由的豁免 + 修复卡） |
| §4.3 Event 同事务 outbox | — | 无执行者，且 Event 机制本身不存在 |
| §2.2 各域的 Does Not Own | — | **不可机械检验。** 「这个字段该归哪个域」是语义判断，靠 review + 本文件 |

**补齐路径**：上表两条「应优先补」的检查，建议合并为一张任务卡
（台账下一个可用编号见 `TASK_BACKLOG.md` 末尾）。在它们落地之前，
§4.1 与 §4.2 只是意图——**而现存的两处越界正是这两条缺执行者的直接产物**。

## 7. References

- `governance/REPOSITORY_CONSTITUTION.md` R2 / R6 / R7 / R9 / R10 / R14
- ADR-0005 §2（核心/优势/支撑域划分）、ADR-0010（投影不拥有真相）、
  ADR-0011（platform 与业务身份边界）、ADR-0012（`growth_plan` 退役）、
  ADR-0014（Draft→Fact 边界与 `PolicyEngine` 的位置）、ADR-0015（七引擎与价值层边界）
- `docs/10_engineering/ENGINEERING_ARCHITECTURE.md`（四种通信模式的命名来源、§6 技术债）
- `docs/00_system/TARGET_ARCHITECTURE.md`（进程拓扑）、`CURRENT_DOMAIN_MAP.md`（**现状以它为准**）
- `docs/07_data/DATA_ARCHITECTURE.md`（分域 schema；跨 schema 只经应用层 Query Port）
- `docs/06_platform/*`（6 项内核的实际契约）
- `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` §3（未成年人营销绝对禁止）
- 实测越界证据：`backend/domains/assessment/api.py:40, 68-154`（`/auth/*` 寄居）、
  `backend/domains/product_intelligence/application/ports.py`（Port 携带 19 个实体）
- 正面范例：`backend/domains/loyalty_points/`（无 `balance` 字段、无 `rank_families` 方法
  —— 用能力的缺席代替禁令）
