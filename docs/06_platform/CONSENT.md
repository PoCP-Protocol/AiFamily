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

**代码**：`backend/platform/consent/models.py`（66 行）、`backend/platform/consent/gate.py`（49 行）
**测试**：`tests/platform/consent/test_gate.py`（6 个测试）
**Registry**：`governance/CAPABILITY_REGISTRY.yaml` → capability `check_consent`（`status: IMPLEMENTED_TESTED`，且该条目自带 `known_gaps`）
**上位约束**：`docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` §5（禁止一次性打包勾选）、§6（删除权覆盖派生数据）

本文件从代码反向记录实际契约。总览见 `PLATFORM_ARCHITECTURE.md`。
**本模块是六项内核里合规缺口最集中的一项** —— §3 必须与 `COMPLIANCE_HARD_CONSTRAINTS.md` 对读。

---

## 1. 实际提供什么

四个导出符号：`ConsentGate` / `ConsentGrant` / `ConsentPurpose` / `ConsentStatus`。

### 1.1 `ConsentPurpose`（StrEnum，四值）

```text
SERVICE            = "service"
ASSESSMENT         = "assessment"
AI_PERSONALIZATION = "ai_personalization"
GROWTH_TRACKING    = "growth_tracking"
```

**一次授权只绑定一个 purpose。**"同意一切"在类型上不可表达（`models.py:19-22`）—— 没有 `ALL` 值，也没有 purpose 之间的蕴含关系。测试 `test_grant_for_a_different_purpose_does_not_leak_permission` 锁定这一点：`SERVICE` 的授权对 `AI_PERSONALIZATION` 的查询返回 `False`。

这个 purpose 分离是 `COMPLIANCE_HARD_CONSTRAINTS.md` §5"禁止一次性打包勾选"（PIPL 第29条单独同意）在类型层的落点，方向正确但只是第一步（见 §3）。

### 1.2 `ConsentStatus`（StrEnum，三值）

`GRANTED` / `WITHDRAWN` / `EXPIRED`。只有 `GRANTED` 使 `is_active` 为真。

### 1.3 `ConsentGrant`（frozen dataclass, slots）

| 字段 | 类型 | 约束 |
|---|---|---|
| `consent_id` | `str` | 非空 |
| `subject_person_id` | `str` | 非空 —— 数据**关于谁** |
| `guardian_person_id` | `str` | 非空 —— **谁代为授权** |
| `purpose` | `ConsentPurpose` | 必填 |
| `status` | `ConsentStatus` | 必填 |
| `granted_at` | `datetime` | 必填，**无默认值、无时区强制** |

一个属性 `is_active`。

`subject` 与 `guardian` 分离是有意的：成年人自我授权时两者相等，但**这个相等由 domain 判定，本模块不强制**（`models.py:42-46` 明说）。

### 1.4 `ConsentGate`

唯一方法，`@staticmethod`：

```python
ConsentGate.check(subject_id: str, purpose: ConsentPurpose,
                  grants: Iterable[ConsentGrant]) -> bool
```

线性扫描 `grants`，返回是否存在 `subject_person_id == subject_id and purpose is purpose and is_active` 的一条。

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

1. **不支持"同意界面同时提供拒绝选项"**（《儿童个人信息网络保护规定》第10条）。当前模型里 `ConsentStatus` 没有 `REFUSED` —— "被明确拒绝过"与"从未问过"在数据上不可区分，而第10条要求拒绝是一个被提供、且其后果被告知的选项。
2. **不支持目的变更触发重新同意**（第14条 / PIPL 第14条第2款）。`ConsentGrant` 是一条独立记录，没有版本、没有"所依据的告知文本版本"字段。告知事项实质变化后无法判定既有授权是否仍然有效。
3. **不支持留存期限与到期处理**（第10条要求**事前**披露存储期限与到期处理方式；第12条要求不超过必要期限）。`ConsentGrant` 有 `granted_at`，**没有 `expires_at`**。`ConsentStatus.EXPIRED` 存在但**没有任何代码会把一条 grant 变成 EXPIRED** —— 无过期计算、无定时任务。这个枚举值目前只能靠调用方手工传入。
4. **不表达"14岁以下须监护人同意"**。`guardian_person_id` 是必填字段，但没有任何校验保证它真的是 subject 的监护人，也没有年龄字段。`COMPLIANCE_HARD_CONSTRAINTS.md` §1（PIPL 第28/31条）与 §9（14岁线的正确适用范围）要求的判定在此处**完全无支撑**，只能靠 domain。
5. **`grants` 的新鲜度无强制**。§2.3 那条"必须传当次刚读的 grants"是纯文档约定。调用方完全可以传一个模块级缓存的 list，`ConsentGate` 无从察觉。也就是说"撤回立即生效"的保证**只覆盖 Gate 内部，不覆盖整条链路**。没有检查器能捕获误用。
6. **没有持久化，也没有 repository 接口**。没有 `ConsentRepository` 抽象、没有 SQLAlchemy 模型、没有表。`database/baseline/0005_consent_active_uniqueness.sql` 里有源仓库带来的 consent 相关约束，但与本模块的 Python 值对象**没有任何映射代码**。
7. **`granted_at` 无时区强制**。可以传 naive datetime。对比 `AuditEvent.timestamp` 用 `datetime.now(UTC)` 做默认值，此处不一致。跨时区的"何时同意"在合规举证时是实质问题。
8. **无真实生产调用方**。全仓 grep `ConsentGate`：只有自身与 `tests/platform/consent/`。
9. **无撤回后的级联删除接线**。`COMPLIANCE_HARD_CONSTRAINTS.md` §6 要求撤回同意触发删除，且删除必须覆盖 embedding 等派生数据。本模块只表达"授权状态是什么"，不触发任何删除，也没有向任何删除机制发事件。
