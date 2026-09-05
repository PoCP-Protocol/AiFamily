---
id: PLT-CONSENT-001
title: 平台内核规格 — Consent
type: platform
status: current
version: 1.0
owner: chief-architect
created: 2026-08-29
updated: 2026-08-29
canonical: true
supersedes: null
superseded_by: null
---

# Consent — ConsentGrant / ConsentGate

**代码**：`backend/platform/consent/models.py`、`backend/platform/consent/gate.py`
**测试**：`tests/platform/consent/test_gate.py`、`tests/platform/consent/test_compliance_model.py`
**Registry**：`governance/CAPABILITY_REGISTRY.yaml` → capability `check_consent`（`status: IMPLEMENTED_TESTED`，且该条目自带 `known_gaps`）
**上位约束**：`docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` §5（禁止一次性打包勾选）、§6（删除权覆盖派生数据）

本文件从代码反向记录实际契约。总览见 `PLATFORM_ARCHITECTURE.md`。
**本模块是六项内核里合规缺口最集中的一项** —— §3 必须与 `COMPLIANCE_HARD_CONSTRAINTS.md` 对读。

---

## 1. 实际提供什么

七个导出符号：`ConsentGate` / `ConsentGrant` / `ConsentPurpose` / `ConsentStatus` / `GuardianRelation` / `SubjectAge` / `GUARDIAN_CONSENT_AGE_THRESHOLD`。

### 1.1 `ConsentPurpose`（StrEnum，四值）

```text
SERVICE            = "service"
ASSESSMENT         = "assessment"
AI_PERSONALIZATION = "ai_personalization"
GROWTH_TRACKING    = "growth_tracking"
```

**一次授权只绑定一个 purpose。**"同意一切"在类型上不可表达（`models.py:19-22`）—— 没有 `ALL` 值，也没有 purpose 之间的蕴含关系。测试 `test_grant_for_a_different_purpose_does_not_leak_permission` 锁定这一点：`SERVICE` 的授权对 `AI_PERSONALIZATION` 的查询返回 `False`。

这个 purpose 分离是 `COMPLIANCE_HARD_CONSTRAINTS.md` §5"禁止一次性打包勾选"（PIPL 第29条单独同意）在类型层的落点，方向正确但只是第一步（见 §3）。

### 1.2 `ConsentStatus`（StrEnum，四值）

`GRANTED` / `REFUSED` / `WITHDRAWN` / `EXPIRED`（`REFUSED` 为 T-14 新增）。只有 `GRANTED` 且未过期使 `is_active` 为真。

**`REFUSED` 不是 `WITHDRAWN` 的同义词。** WITHDRAWN = 给过、后来收回；REFUSED = 问过、当场拒绝、从未生效。两者都拒，但是两个不同的事实，且只有后者是"第10条要求的拒绝选项确实被提供过"的证据。区分它们还有一个实际后果：被拒绝过的事项不得当作"尚未回答的开放问题"再次弹窗。

### 1.2.1 `GuardianRelation`（StrEnum，三值，T-14 新增）

`SELF` / `GUARDIAN` / `NONE`。声明 `guardian_person_id` 与 `subject_person_id` 之间是什么关系。**这是声明的关系，不是已核验的关系** —— 核验"某人确实是某 subject 的监护人"需要 Account → TenantMembership → Family 绑定链（`auth_identity` / `family_core`，均未落地）。它消除的是"关系连表述都表述不了、因此任何一层都无法校验"这个状态。

### 1.2.2 `SubjectAge`（frozen dataclass，T-14 新增）

单字段 `years: int`，构造时拒绝负数与 >150。包一层而非用裸 `int`，是为了让"14"不能从某个本意是年份/计数/分数的地方漂进来，静默地决定一个合规判断。

只读属性 `requires_guardian_consent` = `years < GUARDIAN_CONSENT_AGE_THRESHOLD`（即 14，PIPL 第28/31条）。

### 1.3 `ConsentGrant`（frozen dataclass, slots）

| 字段 | 类型 | 约束 |
|---|---|---|
| `consent_id` | `str` | 非空 |
| `subject_person_id` | `str` | 非空 —— 数据**关于谁** |
| `guardian_person_id` | `str` | 非空 —— **谁代为授权** |
| `purpose` | `ConsentPurpose` | 必填 |
| `status` | `ConsentStatus` | 必填 |
| `granted_at` | `datetime` | 必填，**无默认值、无时区强制**（见 §3 缺口 7，仍未闭合） |
| `subject_age` | `SubjectAge` | 必填（T-14 新增） |
| `guardian_relation` | `GuardianRelation` | 必填（T-14 新增） |
| `expires_at` | `datetime \| None` | 默认 `None`（T-14 新增） |

**构造即拒绝表面违法的组合**（`__post_init__`，T-14）：
- subject < 14 时，`guardian_relation` 必须是 `GUARDIAN`（`SELF` 意味着孩子替自己同意，`NONE` 意味着监护关系根本未建立），且 `guardian_person_id != subject_person_id`（孩子不能是自己的监护人）—— PIPL 第31条。
- `guardian_relation is SELF` 时，`guardian_person_id` 必须等于 `subject_person_id`。
- `expires_at` 必须晚于 `granted_at`（授权时刻即已过期的授权从未生效），且与 `granted_at` 的 naive/aware 属性必须一致（混搭无法比较）。

三个属性/方法：`status_at(moment)` / `is_active_at(moment)` / `is_active`（= `is_active_at(now)`）。

**`ConsentStatus.EXPIRED` 由 `status_at` 派生，不存储。** 论点与 §2.1 同源：能过期的东西只有存起来的东西。若靠定时任务改写 status，那么在任务落后的这段时间里，库里会有一条已过留存期却仍显示 GRANTED 的记录。终态（WITHDRAWN / REFUSED）不会被过期覆盖 —— 它们拒绝的原因不是时间流逝，审计链必须持续说得出原因。

`subject` 与 `guardian` 分离是有意的：成年人自我授权时两者相等，但**这个相等由 domain 判定，本模块不强制**（`models.py:42-46` 明说）。

### 1.4 `ConsentGate`

唯一方法，`@staticmethod`：

```python
ConsentGate.check(subject_id: str, purpose: ConsentPurpose,
                  grants: Iterable[ConsentGrant],
                  at: datetime | None = None) -> bool
```

线性扫描 `grants`，返回是否存在 `subject_person_id == subject_id and purpose is purpose and is_active_at(moment)` 的一条。`at` 默认为当下；它**不默认为"忽略过期"** —— 一个跳过留存期的默认值会让第12条因遗漏而不可执行。`at` 的存在也让过期可测、并让需要复盘"当时允许了什么"的调用方有办法问。

## 2. 实际约束

### 2.1 撤回立即生效 —— 由"没有状态"来保证，不是由"及时失效缓存"

这是本模块唯一的不可让步要求（`gate.py:3-9`）。实现方式是**彻底不持有状态**：
- `check` 是 `@staticmethod`，`ConsentGate` 无 `__init__`、无实例字段。
- 不做 I/O，不查库。`grants` 必须由调用方**当次读出来**再传进来。

测试 `test_withdrawal_takes_effect_without_any_cache_across_calls`（`test_gate.py:39`）直接验证："同一 subject/purpose，先传 GRANTED 列表得 True，再传 WITHDRAWN 列表得 False"，中间没有任何失效操作。

设计论点：能过期的东西只有存起来的东西；什么都不存，就没有能返回过期 ALLOW 的代码路径。

### 2.2 三条独立的不泄露

三个测试各锁一条：
- purpose 不匹配不泄露（`test_grant_for_a_different_purpose_does_not_leak_permission`）
- subject 不匹配不泄露（`test_grant_for_a_different_subject_does_not_leak_permission`）
- 空 grants 列表 → `False`（`test_no_grants_at_all_is_denied`）

即：**默认拒绝**，与 `AUTHORIZATION.md` 的 fail-closed 同构。

### 2.3 契约转移给调用方的部分

`gate.py:11-15` 明确把"从数据库读当前 grants"推给"第一个需要它的 domain repository"，并附带要求：必须传**当次刚读的** grants，不得传上一个请求缓存下来的列表。**这条要求没有任何代码或测试强制** —— 它是文档级契约（见 §3 缺口 2）。

## 3. 已知缺口

**前四条直接是法定合规缺口**，与 `COMPLIANCE_HARD_CONSTRAINTS.md` §5 及 `CAPABILITY_REGISTRY.yaml` 的 `check_consent.known_gaps` 一致：

1. ~~**不支持"同意界面同时提供拒绝选项"**（第10条）。`ConsentStatus` 没有 `REFUSED` —— "被明确拒绝过"与"从未问过"在数据上不可区分。~~ **部分已修（T-14）**：`ConsentStatus.REFUSED` 已加入，拒绝可被记录、可与"从未问过"（空 grants 列表）区分、且被 Gate 拒绝。测试见 `test_compliance_model.py` 的 gap 1 段。
   **仍未闭合的部分**：这只是**数据模型**层面可表达了。第10条同时要求"拒绝的后果被告知"，属于同意界面（前端 + 告知文本版本管理）的义务，本模块无从表达，且与缺口 2（无告知文本版本字段）耦合。
2. **不支持目的变更触发重新同意**（第14条 / PIPL 第14条第2款）。`ConsentGrant` 是一条独立记录，没有版本、没有"所依据的告知文本版本"字段。告知事项实质变化后无法判定既有授权是否仍然有效。
3. ~~**不支持留存期限与到期处理**。`ConsentGrant` 有 `granted_at`，**没有 `expires_at`**；`ConsentStatus.EXPIRED` 存在但没有任何代码会产生它。~~ **部分已修（T-14）**：`expires_at` 字段已加，`EXPIRED` 由 `status_at()` 派生（不再是死枚举），Gate 在过期后立即拒绝且不需要任何定时任务。边界为闭区间（恰好到 `expires_at` 即失效）。测试见 gap 3 段。
   **仍未闭合的部分**：`expires_at` 可为 `None`，且**没有任何东西强制它被设置**。第10条要求的是"事前披露"，本模块只能表达期限、无法强制"每条 grant 都必须有期限且该期限在采集时已告知"。到期后的**处理方式**（删除？匿名化？含派生数据？）同样未表达，与缺口 9（无级联删除接线）耦合。
4. ~~**不表达"14岁以下须监护人同意"**。没有年龄字段，也没有任何校验保证 `guardian_person_id` 真的是 subject 的监护人。~~ **部分已修（T-14）**：`SubjectAge` + `GuardianRelation` + `GUARDIAN_CONSENT_AGE_THRESHOLD = 14` 使判定可表达，且 `__post_init__` 拒绝 < 14 却无独立监护人的组合。
   **`COMPLIANCE_HARD_CONSTRAINTS.md` §9 的纠正已被落实且有测试守护**：14 岁线只用于"是否**要求**监护人同意"，本模块**没有任何访问决策以年龄为键**。`test_fourteen_line_is_only_about_requiring_consent` 专门锁定"15 岁 subject 由监护人记录的授权仍然可表达、仍然生效"，即禁止把 14 岁实现成"过了 14 岁监护人就没权限"（《未成年人网络保护条例》第34条并列赋权、无年龄切分）。`GUARDIAN_CONSENT_AGE_THRESHOLD == 14` 亦被单独 pin 住，防止"顺手整理"挪动法定边界。
   **仍未闭合的部分（重要）**：`guardian_relation` 是**声明**而非**核验**。没有任何机制证明该 person 真的是该 subject 的监护人 —— 需要 Account → TenantMembership → Family 绑定链（`auth_identity` / `family_core`，均 NOT_STARTED）。`subject_age` 同理是传入值，无 person 记录可核对。也就是说本模块把"无法表述"升级成了"可表述且可校验其内部一致性"，但**未**升级到"可核验其对应现实"。
5. **`grants` 的新鲜度无强制**。§2.3 那条"必须传当次刚读的 grants"是纯文档约定。调用方完全可以传一个模块级缓存的 list，`ConsentGate` 无从察觉。也就是说"撤回立即生效"的保证**只覆盖 Gate 内部，不覆盖整条链路**。没有检查器能捕获误用。
6. **没有持久化，也没有 repository 接口**。没有 `ConsentRepository` 抽象、没有 SQLAlchemy 模型、没有表。`database/baseline/0005_consent_active_uniqueness.sql` 里有源仓库带来的 consent 相关约束，但与本模块的 Python 值对象**没有任何映射代码**。
7. **`granted_at` 无时区强制**。可以传 naive datetime。对比 `AuditEvent.timestamp` 用 `datetime.now(UTC)` 做默认值，此处不一致。跨时区的"何时同意"在合规举证时是实质问题。
   **T-14 未修此条，且是刻意的**：`service` 与 `membership` 两域的 `utcnow()` 都刻意返回 naive UTC（SQLite 快速测试路径会丢 tzinfo），在此处强制 aware 会改动那两个域的语义，而这超出 T-14 授权。T-14 只做了两件不改语义的加固：(a) 构造时拒绝 `granted_at` 与 `expires_at` 一个 naive 一个 aware 的混搭；(b) `status_at` 用 `_as_comparable` 把比较双方对齐到同一 naive/aware 立场 —— 否则一次漏掉的过期会变成 `TypeError`，而合规闸门上的崩溃就是拒绝服务。真正修此条应与那两域的 `utcnow()` 一并处理。
8. **无真实生产调用方**。全仓 grep `ConsentGate`：只有自身与 `tests/platform/consent/`。
9. **无撤回后的级联删除接线**。`COMPLIANCE_HARD_CONSTRAINTS.md` §6 要求撤回同意触发删除，且删除必须覆盖 embedding 等派生数据。本模块只表达"授权状态是什么"，不触发任何删除，也没有向任何删除机制发事件。
